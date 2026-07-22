<?php
declare(strict_types=1);

require __DIR__ . '/lib.php';
require_method('POST');
require_write_token();

$data = request_json(65536);
$db = pdo();
$action = trim((string)($data['action'] ?? ''));
$accountKey = strtoupper(trim((string)($data['accountKey'] ?? '')));
$role = strtoupper(trim((string)($data['role'] ?? '')));
$ownerId = strtolower(trim((string)($data['ownerId'] ?? '')));
$hostname = substr(trim((string)($data['hostname'] ?? '')), 0, 120);
$pid = (int)($data['pid'] ?? 0);
$build = substr(trim((string)($data['build'] ?? '')), 0, 160);

if ($accountKey === '' || !preg_match('/^[A-Z0-9_:-]{1,64}$/', $accountKey)) {
    json_response(['ok' => false, 'error' => 'valid accountKey required'], 400);
}
if (!preg_match('/^[a-f0-9]{32}$/', $ownerId)) {
    json_response(['ok' => false, 'error' => 'valid ownerId required'], 400);
}
if (!in_array($role, ['EXECUTOR', 'PUBLISHER'], true)) {
    json_response(['ok' => false, 'error' => 'valid role required'], 400);
}

$accountStmt = $db->prepare(
    'SELECT 1 FROM monitor_accounts WHERE account_key = ? AND enabled = TRUE LIMIT 1'
);
$accountStmt->execute([$accountKey]);
if (!$accountStmt->fetchColumn()) {
    json_response(['ok' => false, 'error' => 'Unknown or disabled account'], 400);
}

$clampTtl = static function (mixed $value, int $minimum, int $maximum, int $fallback): int {
    $ttl = is_numeric($value) ? (int)ceil((float)$value) : $fallback;
    return max($minimum, min($maximum, $ttl));
};
$parseDbTime = static fn(string $value): DateTimeImmutable =>
    new DateTimeImmutable($value, new DateTimeZone('UTC'));
$dbNow = static function (PDO $db) use ($parseDbTime): DateTimeImmutable {
    $value = (string)$db->query('SELECT UTC_TIMESTAMP(3)')->fetchColumn();
    return $parseDbTime($value);
};
$leaseForUpdate = static function (PDO $db, string $account, string $name): array|false {
    $stmt = $db->prepare(
        'SELECT strategy_key, lease_name, owner_id, fencing_token, hostname,
                process_id, build_id, operation_id, operation_kind,
                acquired_at, heartbeat_at, expires_at, released_at
           FROM strategy_runtime_leases
          WHERE strategy_key = ? AND lease_name = ?
          FOR UPDATE'
    );
    $stmt->execute([$account, $name]);
    return $stmt->fetch();
};
$holderPayload = static function (array $row): array {
    return [
        'ownerId' => (string)$row['owner_id'],
        'fencingToken' => (int)$row['fencing_token'],
        'hostname' => (string)$row['hostname'],
        'pid' => (int)$row['process_id'],
        'build' => (string)$row['build_id'],
        'operationId' => (string)$row['operation_id'],
        'operationKind' => (string)$row['operation_kind'],
        'acquiredAt' => (string)$row['acquired_at'],
        'heartbeatAt' => (string)$row['heartbeat_at'],
        'expiresAt' => (string)$row['expires_at'],
    ];
};
$isActive = static function (array $row, DateTimeImmutable $now) use ($parseDbTime): bool {
    return $parseDbTime((string)$row['expires_at']) > $now;
};
$requireExecutor = static function (
    PDO $db,
    string $account,
    string $owner,
    int $token,
    DateTimeImmutable $now,
    bool $forUpdate = false
) use ($isActive): array {
    $sql = 'SELECT * FROM strategy_runtime_leases
             WHERE strategy_key = ? AND lease_name = "EXECUTOR"'
        . ($forUpdate ? ' FOR UPDATE' : '');
    $stmt = $db->prepare($sql);
    $stmt->execute([$account]);
    $row = $stmt->fetch();
    if (!is_array($row)
        || !$isActive($row, $now)
        || !hash_equals((string)$row['owner_id'], $owner)
        || (int)$row['fencing_token'] !== $token) {
        throw new RuntimeException('stale or invalid executor fencing token');
    }
    return $row;
};
$requireGate = static function (
    PDO $db,
    string $account,
    string $owner,
    int $gateToken,
    string $operationId,
    DateTimeImmutable $now,
    bool $forUpdate = false
) use ($isActive): array {
    $sql = 'SELECT * FROM strategy_runtime_leases
             WHERE strategy_key = ? AND lease_name = "TRADE_EXECUTION"'
        . ($forUpdate ? ' FOR UPDATE' : '');
    $stmt = $db->prepare($sql);
    $stmt->execute([$account]);
    $row = $stmt->fetch();
    if (!is_array($row)
        || !$isActive($row, $now)
        || !hash_equals((string)$row['owner_id'], $owner)
        || (int)$row['fencing_token'] !== $gateToken
        || !hash_equals((string)$row['operation_id'], $operationId)) {
        throw new RuntimeException('stale or invalid trade-execution gate');
    }
    return $row;
};

try {
    if ($action === 'acquireLease') {
        $leaseName = strtoupper(trim((string)($data['leaseName'] ?? '')));
        if (!in_array($leaseName, ['EXECUTOR', 'PUBLISHER'], true) || $leaseName !== $role) {
            json_response(['ok' => false, 'error' => 'role leaseName mismatch'], 400);
        }
        $ttl = $clampTtl($data['ttlSeconds'] ?? null, 5, 120, 15);
        $db->beginTransaction();
        $now = $dbNow($db);
        $expires = $now->modify('+' . $ttl . ' seconds');
        $row = $leaseForUpdate($db, $accountKey, $leaseName);
        if ($row === false) {
            $token = 1;
            $insert = $db->prepare(
                'INSERT INTO strategy_runtime_leases(
                    strategy_key, lease_name, owner_id, fencing_token, hostname,
                    process_id, build_id, acquired_at, heartbeat_at, expires_at
                 ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)'
            );
            $insert->execute([
                $accountKey, $leaseName, $ownerId, $token, $hostname, $pid, $build,
                mysql_datetime($now), mysql_datetime($now), mysql_datetime($expires),
            ]);
            $acquired = true;
        } else {
            $active = $isActive($row, $now);
            $sameOwner = hash_equals((string)$row['owner_id'], $ownerId);
            if ($active && !$sameOwner) {
                $db->commit();
                json_response([
                    'ok' => true,
                    'acquired' => false,
                    'holder' => $holderPayload($row),
                    'serverTime' => atom_datetime($now),
                ]);
            }
            $token = $sameOwner && $active
                ? (int)$row['fencing_token']
                : (int)$row['fencing_token'] + 1;
            $acquiredAt = $sameOwner && $active
                ? (string)$row['acquired_at']
                : mysql_datetime($now);
            $update = $db->prepare(
                'UPDATE strategy_runtime_leases
                    SET owner_id=?, fencing_token=?, hostname=?, process_id=?, build_id=?,
                        operation_id="", operation_kind="", acquired_at=?, heartbeat_at=?,
                        expires_at=?, released_at=NULL, metadata=NULL
                  WHERE strategy_key=? AND lease_name=?'
            );
            $update->execute([
                $ownerId, $token, $hostname, $pid, $build, $acquiredAt,
                mysql_datetime($now), mysql_datetime($expires), $accountKey, $leaseName,
            ]);
            $acquired = true;
        }
        $db->commit();
        json_response([
            'ok' => true,
            'acquired' => $acquired,
            'fencingToken' => $token,
            'ttlSeconds' => $ttl,
            'expiresAt' => atom_datetime($expires),
            'serverTime' => atom_datetime($now),
        ]);
    }

    if ($action === 'renewLease') {
        $leaseName = strtoupper(trim((string)($data['leaseName'] ?? '')));
        $token = (int)($data['fencingToken'] ?? 0);
        $ttl = $clampTtl($data['ttlSeconds'] ?? null, 5, 120, 15);
        if (!in_array($leaseName, ['EXECUTOR', 'PUBLISHER'], true) || $leaseName !== $role || $token <= 0) {
            json_response(['ok' => false, 'error' => 'invalid renewal request'], 400);
        }
        $now = $dbNow($db);
        $expires = $now->modify('+' . $ttl . ' seconds');
        $stmt = $db->prepare(
            'UPDATE strategy_runtime_leases
                SET heartbeat_at=?, expires_at=?, hostname=?, process_id=?, build_id=?, released_at=NULL
              WHERE strategy_key=? AND lease_name=? AND owner_id=? AND fencing_token=?
                AND expires_at > ?'
        );
        $stmt->execute([
            mysql_datetime($now), mysql_datetime($expires), $hostname, $pid, $build,
            $accountKey, $leaseName, $ownerId, $token, mysql_datetime($now),
        ]);
        json_response([
            'ok' => true,
            'renewed' => $stmt->rowCount() === 1,
            'fencingToken' => $token,
            'ttlSeconds' => $ttl,
            'expiresAt' => atom_datetime($expires),
        ]);
    }

    if ($action === 'releaseLease') {
        $leaseName = strtoupper(trim((string)($data['leaseName'] ?? '')));
        $token = (int)($data['fencingToken'] ?? 0);
        if (!in_array($leaseName, ['EXECUTOR', 'PUBLISHER'], true)
            || $leaseName !== $role
            || $token <= 0) {
            json_response(['ok' => false, 'error' => 'invalid release request'], 400);
        }
        $now = $dbNow($db);
        $stmt = $db->prepare(
            'UPDATE strategy_runtime_leases
                SET expires_at=?, released_at=?, heartbeat_at=?
              WHERE strategy_key=? AND lease_name=? AND owner_id=? AND fencing_token=?'
        );
        $stmt->execute([
            mysql_datetime($now), mysql_datetime($now), mysql_datetime($now),
            $accountKey, $leaseName, $ownerId, $token,
        ]);
        json_response(['ok' => true, 'released' => $stmt->rowCount() === 1]);
    }

    if ($action === 'leaseStatus') {
        $leaseName = strtoupper(trim((string)($data['leaseName'] ?? '')));
        if (!in_array($leaseName, ['EXECUTOR', 'PUBLISHER', 'TRADE_EXECUTION'], true)) {
            json_response(['ok' => false, 'error' => 'invalid leaseName'], 400);
        }
        $now = $dbNow($db);
        $stmt = $db->prepare(
            'SELECT * FROM strategy_runtime_leases
              WHERE strategy_key=? AND lease_name=? LIMIT 1'
        );
        $stmt->execute([$accountKey, $leaseName]);
        $row = $stmt->fetch();
        json_response([
            'ok' => true,
            'active' => is_array($row) && $isActive($row, $now),
            'holder' => is_array($row) ? $holderPayload($row) : null,
            'serverTime' => atom_datetime($now),
        ]);
    }

    if ($action === 'acquireTradeGate') {
        $executorToken = (int)($data['executorFencingToken'] ?? 0);
        $operationId = substr(trim((string)($data['operationId'] ?? '')), 0, 96);
        $operationKind = substr(strtoupper(trim((string)($data['operationKind'] ?? ''))), 0, 64);
        $ttl = $clampTtl($data['ttlSeconds'] ?? null, 2, 30, 10);
        if ($role !== 'EXECUTOR' || $executorToken <= 0 || $operationId === '' || $operationKind === '') {
            json_response(['ok' => false, 'error' => 'invalid trade-gate request'], 400);
        }
        $db->beginTransaction();
        $now = $dbNow($db);
        $requireExecutor($db, $accountKey, $ownerId, $executorToken, $now, true);
        $expires = $now->modify('+' . $ttl . ' seconds');
        $row = $leaseForUpdate($db, $accountKey, 'TRADE_EXECUTION');
        if ($row !== false && $isActive($row, $now)) {
            $sameOperation = hash_equals((string)$row['owner_id'], $ownerId)
                && hash_equals((string)$row['operation_id'], $operationId);
            if (!$sameOperation) {
                $db->commit();
                json_response([
                    'ok' => true,
                    'acquired' => false,
                    'holder' => $holderPayload($row),
                    'serverTime' => atom_datetime($now),
                ]);
            }
            $gateToken = (int)$row['fencing_token'];
        } elseif ($row === false) {
            $gateToken = 1;
            $insert = $db->prepare(
                'INSERT INTO strategy_runtime_leases(
                    strategy_key, lease_name, owner_id, fencing_token, hostname,
                    process_id, build_id, operation_id, operation_kind,
                    acquired_at, heartbeat_at, expires_at
                 ) VALUES (?, "TRADE_EXECUTION", ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)'
            );
            $insert->execute([
                $accountKey, $ownerId, $gateToken, $hostname, $pid, $build,
                $operationId, $operationKind, mysql_datetime($now),
                mysql_datetime($now), mysql_datetime($expires),
            ]);
        } else {
            $gateToken = (int)$row['fencing_token'] + 1;
        }
        if ($row !== false) {
            $update = $db->prepare(
                'UPDATE strategy_runtime_leases
                    SET owner_id=?, fencing_token=?, hostname=?, process_id=?, build_id=?,
                        operation_id=?, operation_kind=?, acquired_at=?, heartbeat_at=?,
                        expires_at=?, released_at=NULL
                  WHERE strategy_key=? AND lease_name="TRADE_EXECUTION"'
            );
            $update->execute([
                $ownerId, $gateToken, $hostname, $pid, $build, $operationId,
                $operationKind, mysql_datetime($now), mysql_datetime($now),
                mysql_datetime($expires), $accountKey,
            ]);
        }
        $db->commit();
        json_response([
            'ok' => true,
            'acquired' => true,
            'fencingToken' => $gateToken,
            'ttlSeconds' => $ttl,
            'expiresAt' => atom_datetime($expires),
        ]);
    }

    if ($action === 'validateTradeGate') {
        $executorToken = (int)($data['executorFencingToken'] ?? 0);
        $gateToken = (int)($data['gateFencingToken'] ?? 0);
        $operationId = substr(trim((string)($data['operationId'] ?? '')), 0, 96);
        $operationKind = substr(strtoupper(trim((string)($data['operationKind'] ?? ''))), 0, 64);
        $now = $dbNow($db);
        $requireExecutor($db, $accountKey, $ownerId, $executorToken, $now);
        $gate = $requireGate($db, $accountKey, $ownerId, $gateToken, $operationId, $now);
        $valid = hash_equals((string)$gate['operation_kind'], $operationKind);
        json_response([
            'ok' => true,
            'valid' => $valid,
            'executorFencingToken' => $executorToken,
            'gateFencingToken' => $gateToken,
        ]);
    }

    if ($action === 'releaseTradeGate') {
        $executorToken = (int)($data['executorFencingToken'] ?? 0);
        $gateToken = (int)($data['gateFencingToken'] ?? 0);
        $operationId = substr(trim((string)($data['operationId'] ?? '')), 0, 96);
        $now = $dbNow($db);
        $requireExecutor($db, $accountKey, $ownerId, $executorToken, $now);
        $stmt = $db->prepare(
            'UPDATE strategy_runtime_leases
                SET expires_at=?, released_at=?, heartbeat_at=?
              WHERE strategy_key=? AND lease_name="TRADE_EXECUTION"
                AND owner_id=? AND fencing_token=? AND operation_id=?'
        );
        $stmt->execute([
            mysql_datetime($now), mysql_datetime($now), mysql_datetime($now),
            $accountKey, $ownerId, $gateToken, $operationId,
        ]);
        json_response(['ok' => true, 'released' => $stmt->rowCount() === 1]);
    }

    if ($action === 'claimWeeklyEntry') {
        $executorToken = (int)($data['executorFencingToken'] ?? 0);
        $gateToken = (int)($data['gateFencingToken'] ?? 0);
        $gateOperationId = substr(trim((string)($data['gateOperationId'] ?? '')), 0, 96);
        $weekKey = strtoupper(substr(trim((string)($data['weekKey'] ?? '')), 0, 10));
        $executionId = substr(trim((string)($data['executionId'] ?? '')), 0, 96);
        $decisionId = substr(trim((string)($data['decisionId'] ?? '')), 0, 64);
        if (!preg_match('/^\d{4}-W\d{2}$/', $weekKey) || $executionId === '') {
            json_response(['ok' => false, 'error' => 'invalid weekly-entry claim'], 400);
        }
        $db->beginTransaction();
        $now = $dbNow($db);
        $requireExecutor($db, $accountKey, $ownerId, $executorToken, $now, true);
        $requireGate($db, $accountKey, $ownerId, $gateToken, $gateOperationId, $now, true);
        $stmt = $db->prepare(
            'SELECT * FROM strategy_weekly_entries
              WHERE strategy_key=? AND week_key=? FOR UPDATE'
        );
        $stmt->execute([$accountKey, $weekKey]);
        $entry = $stmt->fetch();
        $claimed = false;
        if ($entry === false) {
            $insert = $db->prepare(
                'INSERT INTO strategy_weekly_entries(
                    strategy_key, week_key, execution_id, decision_id, owner_id,
                    executor_fencing_token, gate_fencing_token, status, attempt_count,
                    claimed_at, updated_at
                 ) VALUES (?, ?, ?, ?, ?, ?, ?, "CLAIMED", 1, ?, ?)'
            );
            $insert->execute([
                $accountKey, $weekKey, $executionId, $decisionId, $ownerId,
                $executorToken, $gateToken, mysql_datetime($now), mysql_datetime($now),
            ]);
            $claimed = true;
        } elseif ((string)$entry['status'] === 'REJECTED') {
            $update = $db->prepare(
                'UPDATE strategy_weekly_entries
                    SET execution_id=?, decision_id=?, owner_id=?,
                        executor_fencing_token=?, gate_fencing_token=?,
                        status="CLAIMED", attempt_count=attempt_count+1,
                        claimed_at=?, completed_at=NULL, order_ticket=0, deal_ticket=0,
                        retcode=-1, error_text="", updated_at=?
                  WHERE strategy_key=? AND week_key=?'
            );
            $update->execute([
                $executionId, $decisionId, $ownerId, $executorToken, $gateToken,
                mysql_datetime($now), mysql_datetime($now), $accountKey, $weekKey,
            ]);
            $claimed = true;
        } elseif (
            (string)$entry['status'] === 'CLAIMED'
            && hash_equals((string)$entry['execution_id'], $executionId)
            && (int)$entry['gate_fencing_token'] === $gateToken
        ) {
            $claimed = true;
        }
        $viewStmt = $db->prepare(
            'SELECT week_key, execution_id, decision_id, status, attempt_count,
                    order_ticket, deal_ticket, retcode, claimed_at, completed_at
               FROM strategy_weekly_entries
              WHERE strategy_key=? AND week_key=?'
        );
        $viewStmt->execute([$accountKey, $weekKey]);
        $view = $viewStmt->fetch();
        $db->commit();
        json_response([
            'ok' => true,
            'claimed' => $claimed,
            'entry' => is_array($view) ? [
                'weekKey' => (string)$view['week_key'],
                'executionId' => (string)$view['execution_id'],
                'decisionId' => (string)$view['decision_id'],
                'status' => (string)$view['status'],
                'attemptCount' => (int)$view['attempt_count'],
                'orderTicket' => (int)$view['order_ticket'],
                'dealTicket' => (int)$view['deal_ticket'],
                'retcode' => (int)$view['retcode'],
                'claimedAt' => (string)$view['claimed_at'],
                'completedAt' => $view['completed_at'],
            ] : null,
        ]);
    }

    if ($action === 'completeWeeklyEntry') {
        $executorToken = (int)($data['executorFencingToken'] ?? 0);
        $weekKey = strtoupper(substr(trim((string)($data['weekKey'] ?? '')), 0, 10));
        $executionId = substr(trim((string)($data['executionId'] ?? '')), 0, 96);
        $status = strtoupper(trim((string)($data['status'] ?? 'UNKNOWN')));
        if (!in_array($status, ['ACCEPTED', 'REJECTED', 'UNKNOWN'], true)) {
            json_response(['ok' => false, 'error' => 'invalid weekly-entry completion status'], 400);
        }
        $now = $dbNow($db);
        $requireExecutor($db, $accountKey, $ownerId, $executorToken, $now);
        $stmt = $db->prepare(
            'UPDATE strategy_weekly_entries
                SET status=?, completed_at=?, order_ticket=?, deal_ticket=?,
                    retcode=?, error_text=?, updated_at=?
              WHERE strategy_key=? AND week_key=? AND execution_id=?
                AND status="CLAIMED"'
        );
        $stmt->execute([
            $status, mysql_datetime($now), max(0, (int)($data['orderTicket'] ?? 0)),
            max(0, (int)($data['dealTicket'] ?? 0)), (int)($data['retcode'] ?? -1),
            substr((string)($data['error'] ?? ''), 0, 500), mysql_datetime($now),
            $accountKey, $weekKey, $executionId,
        ]);
        json_response(['ok' => true, 'updated' => $stmt->rowCount() === 1]);
    }

    json_response(['ok' => false, 'error' => 'Unknown coordination action'], 400);
} catch (Throwable $e) {
    if ($db->inTransaction()) {
        $db->rollBack();
    }
    error_log('OPPW coordination failed: ' . $e->getMessage());
    json_response(['ok' => false, 'error' => $e->getMessage()], 409);
}
