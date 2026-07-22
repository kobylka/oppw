<?php
declare(strict_types=1);

require __DIR__ . '/lib.php';

$method = strtoupper((string)($_SERVER['REQUEST_METHOD'] ?? 'GET'));
$db = pdo();
$staleSeconds = max(10, min(120, (int)(config()['service_supervisor_stale_seconds'] ?? 20)));

$validAccount = static function (string $value): string {
    $account = strtoupper(trim($value));
    if ($account === '' || !preg_match('/^[A-Z0-9_:-]{1,64}$/', $account)) {
        json_response(['ok' => false, 'error' => 'valid accountKey required'], 400);
    }
    return $account;
};
$validRole = static function (string $value): string {
    $role = strtoupper(trim($value));
    if (!in_array($role, ['EXECUTOR', 'PUBLISHER'], true)) {
        json_response(['ok' => false, 'error' => 'valid role required'], 400);
    }
    return $role;
};
$processView = static function (?array $node, string $account, string $role): array {
    if (!is_array($node)) return ['running' => false, 'pid' => 0, 'startedAt' => '', 'restartCount' => 0, 'lastExitCode' => null];
    try {
        $items = json_decode((string)$node['process_status'], true, 64, JSON_THROW_ON_ERROR);
    } catch (Throwable) {
        $items = [];
    }
    foreach (is_array($items) ? $items : [] as $item) {
        if (is_array($item)
            && strtoupper((string)($item['account'] ?? '')) === $account
            && strtoupper((string)($item['role'] ?? '')) === $role) {
            return [
                'running' => (bool)($item['running'] ?? false),
                'pid' => (int)($item['pid'] ?? 0),
                'startedAt' => substr((string)($item['startedAt'] ?? ''), 0, 40),
                'restartCount' => (int)($item['restartCount'] ?? 0),
                'lastExitCode' => isset($item['lastExitCode']) ? (int)$item['lastExitCode'] : null,
            ];
        }
    }
    return ['running' => false, 'pid' => 0, 'startedAt' => '', 'restartCount' => 0, 'lastExitCode' => null];
};
$nodePayload = static function (?array $row, bool $online) use ($processView): array {
    if (!is_array($row)) return ['configured' => false, 'online' => false, 'nodeId' => '', 'hostname' => '', 'build' => '', 'lastSeenAt' => ''];
    return [
        'configured' => true,
        'online' => $online,
        'nodeId' => (string)$row['node_id'],
        'hostname' => (string)$row['hostname'],
        'build' => (string)$row['build_id'],
        'lastSeenAt' => (string)$row['last_seen_at'],
    ];
};

if ($method === 'GET') {
    $account = $validAccount((string)($_GET['account'] ?? ''));
    $session = require_mobile_session($account);
    $permission = $db->prepare(
        'SELECT can_control_service FROM monitor_device_accounts WHERE device_id=? AND account_key=?'
    );
    $permission->execute([$session['device_id'], $account]);
    $canControl = (bool)$permission->fetchColumn();

    $nowRaw = (string)$db->query('SELECT UTC_TIMESTAMP(3)')->fetchColumn();
    $now = new DateTimeImmutable($nowRaw, new DateTimeZone('UTC'));
    $threshold = $now->modify('-' . $staleSeconds . ' seconds');
    $nodesStmt = $db->query('SELECT * FROM strategy_supervisor_nodes');
    $nodes = [];
    foreach ($nodesStmt->fetchAll() as $row) $nodes[(string)$row['node_role']] = $row;
    $online = static fn(?array $row): bool => is_array($row)
        && new DateTimeImmutable((string)$row['last_seen_at'], new DateTimeZone('UTC')) > $threshold;
    $master = $nodes['MASTER'] ?? null;
    $backup = $nodes['BACKUP'] ?? null;
    $masterOnline = $online($master);
    $backupOnline = $online($backup);

    $desired = $db->prepare(
        'SELECT role_name, desired_running, revision, changed_at
           FROM strategy_service_desired_state
          WHERE strategy_key=? ORDER BY role_name'
    );
    $desired->execute([$account]);
    $desiredByRole = [];
    foreach ($desired->fetchAll() as $row) $desiredByRole[(string)$row['role_name']] = $row;
    $roles = [];
    foreach (['EXECUTOR', 'PUBLISHER'] as $role) {
        $row = $desiredByRole[$role] ?? ['desired_running' => 1, 'revision' => 1, 'changed_at' => ''];
        $activeNodeRole = $masterOnline ? 'MASTER' : ($backupOnline ? 'BACKUP' : '');
        $activeNode = $activeNodeRole === 'MASTER' ? $master : ($activeNodeRole === 'BACKUP' ? $backup : null);
        $roles[] = [
            'role' => $role,
            'desiredRunning' => (bool)$row['desired_running'],
            'revision' => (int)$row['revision'],
            'changedAt' => (string)$row['changed_at'],
            'activeNodeRole' => $activeNodeRole,
            'process' => $processView($activeNode, $account, $role),
            'masterProcess' => $processView($master, $account, $role),
            'backupProcess' => $processView($backup, $account, $role),
        ];
    }
    json_response([
        'ok' => true,
        'generatedAt' => atom_datetime($now),
        'accountKey' => $account,
        'canControl' => $canControl,
        'staleAfterSeconds' => $staleSeconds,
        'master' => $nodePayload($master, $masterOnline),
        'backup' => $nodePayload($backup, $backupOnline),
        'roles' => $roles,
    ]);
}

if ($method !== 'POST') {
    header('Allow: GET, POST');
    json_response(['ok' => false, 'error' => 'Method not allowed'], 405);
}

$data = request_json(65536);
$action = trim((string)($data['action'] ?? ''));

if ($action === 'heartbeat') {
    require_write_token();
    $nodeId = strtolower(trim((string)($data['nodeId'] ?? '')));
    $nodeRole = strtoupper(trim((string)($data['nodeRole'] ?? '')));
    if (!preg_match('/^[a-f0-9]{32}$/', $nodeId) || !in_array($nodeRole, ['MASTER', 'BACKUP'], true)) {
        json_response(['ok' => false, 'error' => 'valid nodeId and nodeRole required'], 400);
    }
    $hostname = substr(trim((string)($data['hostname'] ?? '')), 0, 120);
    $pid = (int)($data['pid'] ?? 0);
    $build = substr(trim((string)($data['build'] ?? '')), 0, 160);
    $startedAt = normalize_datetime((string)($data['startedAt'] ?? ''));
    $rawProcesses = $data['processes'] ?? [];
    if (!is_array($rawProcesses) || count($rawProcesses) > 8) {
        json_response(['ok' => false, 'error' => 'invalid processes payload'], 400);
    }
    $processes = [];
    foreach ($rawProcesses as $item) {
        if (!is_array($item)) continue;
        $processes[] = [
            'account' => $validAccount((string)($item['account'] ?? '')),
            'role' => $validRole((string)($item['role'] ?? '')),
            'running' => (bool)($item['running'] ?? false),
            'pid' => (int)($item['pid'] ?? 0),
            'startedAt' => substr((string)($item['startedAt'] ?? ''), 0, 40),
            'restartCount' => max(0, (int)($item['restartCount'] ?? 0)),
            'lastExitCode' => isset($item['lastExitCode']) ? (int)$item['lastExitCode'] : null,
        ];
    }

    $db->beginTransaction();
    try {
        $nowRaw = (string)$db->query('SELECT UTC_TIMESTAMP(3)')->fetchColumn();
        $now = new DateTimeImmutable($nowRaw, new DateTimeZone('UTC'));
        $threshold = $now->modify('-' . $staleSeconds . ' seconds');
        $lockedNodes = [];
        foreach ($db->query('SELECT * FROM strategy_supervisor_nodes ORDER BY node_role FOR UPDATE')->fetchAll() as $row) {
            $lockedNodes[(string)$row['node_role']] = $row;
        }
        $existing = $lockedNodes[$nodeRole] ?? false;
        if (is_array($existing)
            && !hash_equals((string)$existing['node_id'], $nodeId)
            && new DateTimeImmutable((string)$existing['last_seen_at'], new DateTimeZone('UTC')) > $threshold) {
            $db->rollBack();
            json_response(['ok' => false, 'error' => $nodeRole . ' supervisor role is already online on another node'], 409);
        }
        $otherRole = $nodeRole === 'MASTER' ? 'BACKUP' : 'MASTER';
        $other = $lockedNodes[$otherRole] ?? false;
        if ($hostname !== '' && is_array($other)
            && strcasecmp((string)$other['hostname'], $hostname) === 0
            && new DateTimeImmutable((string)$other['last_seen_at'], new DateTimeZone('UTC')) > $threshold) {
            $db->rollBack();
            json_response(['ok' => false, 'error' => 'MASTER and BACKUP must run on different machines'], 409);
        }
        $statusJson = json_encode($processes, JSON_UNESCAPED_SLASHES | JSON_THROW_ON_ERROR);
        $upsert = $db->prepare(
            'INSERT INTO strategy_supervisor_nodes(node_role,node_id,hostname,process_id,build_id,started_at,last_seen_at,process_status)
             VALUES (?,?,?,?,?,?,?,?)
             ON DUPLICATE KEY UPDATE node_id=VALUES(node_id),hostname=VALUES(hostname),process_id=VALUES(process_id),
                 build_id=VALUES(build_id),started_at=VALUES(started_at),last_seen_at=VALUES(last_seen_at),process_status=VALUES(process_status)'
        );
        $upsert->execute([$nodeRole, $nodeId, $hostname, $pid, $build, $startedAt, mysql_datetime($now), $statusJson]);
        $desiredInsert = $db->prepare(
            "INSERT INTO strategy_service_desired_state(strategy_key,role_name,desired_running)
             SELECT account_key, ?, TRUE FROM monitor_accounts WHERE enabled=TRUE
             ON DUPLICATE KEY UPDATE strategy_key=VALUES(strategy_key)"
        );
        foreach (['EXECUTOR', 'PUBLISHER'] as $role) $desiredInsert->execute([$role]);
        $masterStmt = $db->query("SELECT last_seen_at FROM strategy_supervisor_nodes WHERE node_role='MASTER' FOR UPDATE");
        $masterSeen = $masterStmt->fetchColumn();
        $masterOnline = $masterSeen !== false
            && new DateTimeImmutable((string)$masterSeen, new DateTimeZone('UTC')) > $threshold;
        $states = $db->query(
            'SELECT d.strategy_key, d.role_name, d.desired_running, d.revision
               FROM strategy_service_desired_state d
               JOIN monitor_accounts a ON a.account_key=d.strategy_key AND a.enabled=TRUE
              ORDER BY d.strategy_key,d.role_name'
        )->fetchAll();
        $assignments = array_map(static function (array $row) use ($nodeRole, $masterOnline): array {
            $desired = (bool)$row['desired_running'];
            $assigned = $desired && ($nodeRole === 'MASTER' || !$masterOnline);
            return [
                'account' => (string)$row['strategy_key'],
                'role' => (string)$row['role_name'],
                'desiredRunning' => $desired,
                'assigned' => $assigned,
                'revision' => (int)$row['revision'],
                'reason' => !$desired ? 'MOBILE_STOPPED' : ($assigned ? $nodeRole . '_ACTIVE' : 'MASTER_ONLINE'),
            ];
        }, $states);
        $db->commit();
    } catch (Throwable $e) {
        if ($db->inTransaction()) $db->rollBack();
        error_log('OPPW supervisor heartbeat failed: ' . $e->getMessage());
        json_response(['ok' => false, 'error' => 'Supervisor coordination failed'], 503);
    }
    json_response([
        'ok' => true,
        'serverTime' => atom_datetime($now),
        'pollSeconds' => 3,
        'masterOnline' => $masterOnline,
        'assignments' => $assignments,
    ]);
}

if ($action === 'setDesiredState') {
    $account = $validAccount((string)($data['accountKey'] ?? ''));
    $role = $validRole((string)($data['role'] ?? ''));
    $session = require_mobile_session($account);
    $requestId = strtolower(trim((string)($data['requestId'] ?? '')));
    if (!preg_match('/^[a-f0-9]{32}$/', $requestId)
        || !array_key_exists('desiredRunning', $data)
        || !is_bool($data['desiredRunning'])) {
        json_response(['ok' => false, 'error' => 'requestId and desiredRunning required'], 400);
    }
    $permission = $db->prepare(
        'SELECT can_control_service FROM monitor_device_accounts WHERE device_id=? AND account_key=?'
    );
    $permission->execute([$session['device_id'], $account]);
    if (!(bool)$permission->fetchColumn()) {
        json_response(['ok' => false, 'error' => 'This device is not permitted to control supervised services'], 403);
    }
    $desiredRunning = (bool)$data['desiredRunning'];
    $db->beginTransaction();
    try {
        $nowRaw = (string)$db->query('SELECT UTC_TIMESTAMP(3)')->fetchColumn();
        $now = new DateTimeImmutable($nowRaw, new DateTimeZone('UTC'));
        $event = $db->prepare(
            'INSERT IGNORE INTO strategy_service_control_events(request_id,strategy_key,role_name,desired_running,device_id,requested_at)
             VALUES (?,?,?,?,?,?)'
        );
        $event->execute([$requestId, $account, $role, $desiredRunning ? 1 : 0, $session['device_id'], mysql_datetime($now)]);
        $newRequest = $event->rowCount() === 1;
        if (!$newRequest) {
            $existingEvent = $db->prepare(
                'SELECT strategy_key,role_name,desired_running,device_id FROM strategy_service_control_events WHERE request_id=? FOR UPDATE'
            );
            $existingEvent->execute([$requestId]);
            $recorded = $existingEvent->fetch();
            if (!is_array($recorded)
                || !hash_equals((string)$recorded['strategy_key'], $account)
                || !hash_equals((string)$recorded['role_name'], $role)
                || (bool)$recorded['desired_running'] !== $desiredRunning
                || !hash_equals((string)$recorded['device_id'], (string)$session['device_id'])) {
                $db->rollBack();
                json_response(['ok' => false, 'error' => 'requestId was already used for different service-control content'], 409);
            }
        }
        if ($newRequest) {
            $state = $db->prepare(
                'INSERT INTO strategy_service_desired_state(strategy_key,role_name,desired_running,revision,changed_by_device_id,changed_at)
                 VALUES (?,?,?,1,?,?)
                 ON DUPLICATE KEY UPDATE desired_running=VALUES(desired_running),revision=revision+1,
                    changed_by_device_id=VALUES(changed_by_device_id),changed_at=VALUES(changed_at)'
            );
            $state->execute([$account, $role, $desiredRunning ? 1 : 0, $session['device_id'], mysql_datetime($now)]);
        }
        $view = $db->prepare(
            'SELECT desired_running,revision,changed_at FROM strategy_service_desired_state WHERE strategy_key=? AND role_name=?'
        );
        $view->execute([$account, $role]);
        $current = $view->fetch();
        $db->commit();
    } catch (Throwable $e) {
        if ($db->inTransaction()) $db->rollBack();
        error_log('OPPW service control failed: ' . $e->getMessage());
        json_response(['ok' => false, 'error' => 'Service control failed'], 503);
    }
    json_response([
        'ok' => true,
        'requestId' => $requestId,
        'accountKey' => $account,
        'role' => $role,
        'desiredRunning' => (bool)$current['desired_running'],
        'revision' => (int)$current['revision'],
        'changedAt' => (string)$current['changed_at'],
    ]);
}

json_response(['ok' => false, 'error' => 'Unknown action'], 400);
