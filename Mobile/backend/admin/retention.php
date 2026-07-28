<?php
declare(strict_types=1);

require dirname(__DIR__) . '/lib.php';

if (PHP_SAPI !== 'cli') {
    http_response_code(404);
    exit;
}

const OPPW_EVENT_RETENTION_DAYS = 180;
const OPPW_EQUITY_RETENTION_DAYS = 400;
const OPPW_RETENTION_BATCH_SIZE = 2000;
const OPPW_RETENTION_MAX_BATCHES = 100;
const OPPW_RETENTION_LOCK = 'oppw_data_retention';

function retention_integer_option(array $options, string $name, int $default, int $minimum, int $maximum): int
{
    if (!array_key_exists($name, $options)) return $default;
    $raw = (string)$options[$name];
    if (!preg_match('/^[0-9]+$/', $raw)) {
        throw new InvalidArgumentException("--$name must be an integer");
    }
    $value = (int)$raw;
    if ($value < $minimum || $value > $maximum) {
        throw new InvalidArgumentException("--$name must be between $minimum and $maximum");
    }
    return $value;
}

function retention_path_is_inside(string $candidate, string $parent): bool
{
    $normalize = static fn(string $path): string => rtrim(strtolower(str_replace('\\', '/', $path)), '/');
    $candidate = $normalize($candidate);
    $parent = $normalize($parent);
    return $candidate === $parent || str_starts_with($candidate, $parent . '/');
}

function retention_archive_directory(array $options): string
{
    $configured = trim((string)(config()['retention_archive_dir'] ?? ''));
    $requested = trim((string)($options['archive-dir'] ?? $configured));
    if ($requested === '') {
        throw new RuntimeException('--archive-dir or config retention_archive_dir is required with --apply');
    }
    if (!is_dir($requested) && !mkdir($requested, 0700, true) && !is_dir($requested)) {
        throw new RuntimeException('Unable to create retention archive directory');
    }
    $resolved = realpath($requested);
    $backendRoot = realpath(dirname(__DIR__));
    if ($resolved === false || $backendRoot === false) {
        throw new RuntimeException('Unable to resolve retention archive directory');
    }
    if (retention_path_is_inside($resolved, $backendRoot)) {
        throw new RuntimeException('Retention archives must be outside the backend web root');
    }
    $probe = $resolved . DIRECTORY_SEPARATOR . '.oppw-write-' . bin2hex(random_bytes(8));
    $handle = @fopen($probe, 'x+b');
    if ($handle === false) throw new RuntimeException('Retention archive directory is not writable');
    fclose($handle);
    unlink($probe);
    return $resolved;
}

function retention_source_key(string $dataset, array $row): string
{
    if ($dataset === 'strategy_events') return (string)$row['id'];
    return (string)$row['strategy_key'] . '|' . (string)$row['captured_minute'];
}

function retention_write_archive(
    string $directory,
    string $dataset,
    string $cutoff,
    array $rows,
    DateTimeImmutable $startedAt
): array {
    if (!$rows) throw new InvalidArgumentException('Cannot archive an empty retention batch');
    if (!function_exists('gzopen')) throw new RuntimeException('PHP zlib support is required for retention archives');

    $runId = bin2hex(random_bytes(16));
    $safeCutoff = str_replace([' ', ':', '.'], ['T', '', ''], $cutoff);
    $archiveName = $dataset . '-' . $safeCutoff . '-' . $runId . '.ndjson.gz';
    $archivePath = $directory . DIRECTORY_SEPARATOR . $archiveName;
    if (file_exists($archivePath)) throw new RuntimeException('Retention archive name collision');

    $firstKey = retention_source_key($dataset, $rows[0]);
    $lastKey = retention_source_key($dataset, $rows[count($rows) - 1]);
    $manifest = [
        'format' => 'oppw-retention-ndjson-v1',
        'dataset' => $dataset,
        'cutoffAt' => $cutoff,
        'createdAt' => atom_datetime($startedAt),
        'rowCount' => count($rows),
        'firstSourceKey' => $firstKey,
        'lastSourceKey' => $lastKey,
    ];

    $handle = @gzopen($archivePath, 'wb9');
    if ($handle === false) throw new RuntimeException('Unable to create retention archive');
    try {
        $lines = [['manifest' => $manifest]];
        foreach ($rows as $row) $lines[] = ['row' => $row];
        foreach ($lines as $line) {
            $encoded = json_encode($line, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE | JSON_THROW_ON_ERROR) . "\n";
            if (gzwrite($handle, $encoded) !== strlen($encoded)) {
                throw new RuntimeException('Incomplete retention archive write');
            }
        }
    } catch (Throwable $error) {
        gzclose($handle);
        @unlink($archivePath);
        throw $error;
    }
    if (!gzclose($handle)) {
        @unlink($archivePath);
        throw new RuntimeException('Unable to close retention archive');
    }

    $sha256 = hash_file('sha256', $archivePath);
    if (!is_string($sha256) || !preg_match('/^[a-f0-9]{64}$/', $sha256)) {
        throw new RuntimeException('Unable to hash retention archive');
    }
    $verification = @gzopen($archivePath, 'rb');
    if ($verification === false) throw new RuntimeException('Unable to reopen retention archive for verification');
    $verifiedRows = 0;
    $verifiedManifest = null;
    try {
        while (!gzeof($verification)) {
            $line = gzgets($verification);
            if ($line === false || trim($line) === '') continue;
            $decoded = json_decode($line, true, 64, JSON_THROW_ON_ERROR);
            if ($verifiedManifest === null) {
                $verifiedManifest = $decoded['manifest'] ?? null;
                continue;
            }
            if (!is_array($decoded['row'] ?? null)) throw new RuntimeException('Invalid retention archive row');
            $verifiedRows++;
        }
    } finally {
        gzclose($verification);
    }
    if (!is_array($verifiedManifest)
        || ($verifiedManifest['format'] ?? '') !== 'oppw-retention-ndjson-v1'
        || ($verifiedManifest['dataset'] ?? '') !== $dataset
        || (int)($verifiedManifest['rowCount'] ?? -1) !== count($rows)
        || ($verifiedManifest['firstSourceKey'] ?? '') !== $firstKey
        || ($verifiedManifest['lastSourceKey'] ?? '') !== $lastKey
        || $verifiedRows !== count($rows)
        || !hash_equals($sha256, (string)hash_file('sha256', $archivePath))) {
        throw new RuntimeException('Retention archive verification failed');
    }

    return [
        'runId' => $runId,
        'archiveName' => $archiveName,
        'archivePath' => $archivePath,
        'sha256' => $sha256,
        'firstSourceKey' => $firstKey,
        'lastSourceKey' => $lastKey,
        'rowCount' => count($rows),
    ];
}

function retention_start_run(PDO $db, string $dataset, string $cutoff, array $archive, DateTimeImmutable $startedAt): void
{
    $statement = $db->prepare(
        'INSERT INTO strategy_retention_runs('
        . 'run_id,dataset_name,cutoff_at,first_source_key,last_source_key,row_count,'
        . 'archive_name,archive_sha256,status,started_at'
        . ") VALUES (?,?,?,?,?,?,?,?, 'STARTED', ?)"
    );
    $statement->execute([
        $archive['runId'], $dataset, $cutoff, $archive['firstSourceKey'], $archive['lastSourceKey'],
        $archive['rowCount'], $archive['archiveName'], $archive['sha256'], mysql_datetime($startedAt),
    ]);
}

function retention_fail_run(PDO $db, string $runId, Throwable $error): void
{
    try {
        $statement = $db->prepare(
            "UPDATE strategy_retention_runs SET status='FAILED', completed_at=UTC_TIMESTAMP(3), error_text=? WHERE run_id=?"
        );
        $statement->execute([substr($error->getMessage(), 0, 1000), $runId]);
    } catch (Throwable) {
    }
}

function retention_event_batch(PDO $db, string $cutoff, int $batchSize): array
{
    $statement = $db->prepare(
        "SELECT id,strategy_key,event_time,level,name,result,message,details,event_hash
          FROM strategy_events
          WHERE event_time < ? AND name <> 'EXECUTION_STAGE'
          ORDER BY event_time, id
          LIMIT $batchSize"
    );
    $statement->execute([$cutoff]);
    return $statement->fetchAll();
}

function retention_apply_event_batch(PDO $db, string $cutoff, array $rows, array $archive): void
{
    $db->beginTransaction();
    try {
        $lock = $db->prepare(
            'SELECT id,strategy_key,event_time,level,name,result,message,details,event_hash '
            . 'FROM strategy_events WHERE id=? FOR UPDATE'
        );
        foreach ($rows as $row) {
            $lock->execute([(int)$row['id']]);
            if ($lock->fetch() !== $row) {
                throw new RuntimeException('Event retention source rows changed during archival');
            }
        }
        $delete = $db->prepare(
            "DELETE FROM strategy_events WHERE id=? AND event_time < ? AND name <> 'EXECUTION_STAGE'"
        );
        $deleted = 0;
        foreach ($rows as $row) {
            $delete->execute([(int)$row['id'], $cutoff]);
            $deleted += $delete->rowCount();
        }
        if ($deleted !== count($rows)) throw new RuntimeException('Event retention source rows changed during archival');
        $complete = $db->prepare(
            "UPDATE strategy_retention_runs SET status='COMPLETED', completed_at=UTC_TIMESTAMP(3) WHERE run_id=? AND status='STARTED'"
        );
        $complete->execute([$archive['runId']]);
        if ($complete->rowCount() !== 1) throw new RuntimeException('Unable to complete event retention run');
        $db->commit();
    } catch (Throwable $error) {
        if ($db->inTransaction()) $db->rollBack();
        throw $error;
    }
}

function retention_equity_batch(PDO $db, string $cutoff, int $batchSize): array
{
    $oldest = $db->prepare(
        'SELECT strategy_key, DATE(captured_minute) AS equity_day
           FROM strategy_equity_points
          WHERE captured_minute < ?
          ORDER BY captured_minute, strategy_key
          LIMIT 1'
    );
    $oldest->execute([$cutoff]);
    $group = $oldest->fetch();
    if (!$group) return [];

    $limit = $batchSize + 1;
    $statement = $db->prepare(
        "SELECT strategy_key,captured_minute,balance,equity,deposit,current_profit,position_ticket
           FROM strategy_equity_points
          WHERE strategy_key=? AND captured_minute>=? AND captured_minute<? AND captured_minute < ?
          ORDER BY captured_minute
          LIMIT $limit"
    );
    $dayStart = (string)$group['equity_day'] . ' 00:00:00';
    $dayEnd = (new DateTimeImmutable($dayStart, new DateTimeZone('UTC')))->modify('+1 day')->format('Y-m-d H:i:s');
    $statement->execute([(string)$group['strategy_key'], $dayStart, $dayEnd, $cutoff]);
    $rows = $statement->fetchAll();
    if (count($rows) > $batchSize) {
        throw new RuntimeException("Equity account-day exceeds --batch-size=$batchSize");
    }
    return $rows;
}

function retention_apply_equity_batch(PDO $db, string $cutoff, array $rows, array $archive): void
{
    if (!$rows) throw new InvalidArgumentException('Equity retention batch is empty');
    $first = $rows[0];
    $last = $rows[count($rows) - 1];
    $day = substr((string)$first['captured_minute'], 0, 10);

    $db->beginTransaction();
    try {
        $lock = $db->prepare(
            'SELECT strategy_key,captured_minute,balance,equity,deposit,current_profit,position_ticket '
            . 'FROM strategy_equity_points WHERE strategy_key=? AND captured_minute=? FOR UPDATE'
        );
        foreach ($rows as $row) {
            $lock->execute([(string)$row['strategy_key'], (string)$row['captured_minute']]);
            if ($lock->fetch() !== $row) {
                throw new RuntimeException('Equity retention source rows changed during archival');
            }
        }
        $aggregate = $db->prepare(
            'SELECT MIN(equity),MAX(equity),COUNT(*) FROM strategy_equity_points '
            . 'WHERE strategy_key=? AND captured_minute>=? AND captured_minute<? AND captured_minute < ?'
        );
        $dayStart = $day . ' 00:00:00';
        $dayEnd = (new DateTimeImmutable($dayStart, new DateTimeZone('UTC')))->modify('+1 day')->format('Y-m-d H:i:s');
        $aggregate->execute([(string)$first['strategy_key'], $dayStart, $dayEnd, $cutoff]);
        $aggregateValues = $aggregate->fetch(PDO::FETCH_NUM);
        if (!is_array($aggregateValues) || (int)$aggregateValues[2] !== count($rows)) {
            throw new RuntimeException('Equity account-day changed during archival');
        }
        $rollup = $db->prepare(
            'INSERT INTO strategy_equity_daily('
            . 'strategy_key,equity_day,first_captured_at,last_captured_at,open_balance,open_equity,'
            . 'close_balance,close_equity,minimum_equity,maximum_equity,sample_count'
            . ') VALUES (?,?,?,?,?,?,?,?,?,?,?) '
            . 'ON DUPLICATE KEY UPDATE '
            . 'open_balance=IF(VALUES(first_captured_at)<first_captured_at,VALUES(open_balance),open_balance),'
            . 'open_equity=IF(VALUES(first_captured_at)<first_captured_at,VALUES(open_equity),open_equity),'
            . 'close_balance=IF(VALUES(last_captured_at)>last_captured_at,VALUES(close_balance),close_balance),'
            . 'close_equity=IF(VALUES(last_captured_at)>last_captured_at,VALUES(close_equity),close_equity),'
            . 'first_captured_at=LEAST(first_captured_at,VALUES(first_captured_at)),'
            . 'last_captured_at=GREATEST(last_captured_at,VALUES(last_captured_at)),'
            . 'minimum_equity=LEAST(minimum_equity,VALUES(minimum_equity)),'
            . 'maximum_equity=GREATEST(maximum_equity,VALUES(maximum_equity)),'
            . 'sample_count=sample_count+VALUES(sample_count)'
        );
        $rollup->execute([
            (string)$first['strategy_key'], $day, (string)$first['captured_minute'], (string)$last['captured_minute'],
            (string)$first['balance'], (string)$first['equity'], (string)$last['balance'], (string)$last['equity'],
            (string)$aggregateValues[0], (string)$aggregateValues[1], count($rows),
        ]);

        $delete = $db->prepare(
            'DELETE FROM strategy_equity_points WHERE strategy_key=? AND captured_minute=? AND captured_minute < ?'
        );
        $deleted = 0;
        foreach ($rows as $row) {
            $delete->execute([(string)$row['strategy_key'], (string)$row['captured_minute'], $cutoff]);
            $deleted += $delete->rowCount();
        }
        if ($deleted !== count($rows)) throw new RuntimeException('Equity retention source rows changed during archival');
        $complete = $db->prepare(
            "UPDATE strategy_retention_runs SET status='COMPLETED', completed_at=UTC_TIMESTAMP(3) WHERE run_id=? AND status='STARTED'"
        );
        $complete->execute([$archive['runId']]);
        if ($complete->rowCount() !== 1) throw new RuntimeException('Unable to complete equity retention run');
        $db->commit();
    } catch (Throwable $error) {
        if ($db->inTransaction()) $db->rollBack();
        throw $error;
    }
}

function retention_count(PDO $db, string $sql, array $parameters): int
{
    $statement = $db->prepare($sql);
    $statement->execute($parameters);
    return (int)$statement->fetchColumn();
}

try {
    $remainingIndex = null;
    $options = getopt('', [
        'apply', 'archive-dir:', 'events-days:', 'equity-days:', 'batch-size:', 'max-batches:',
    ], $remainingIndex);
    if ($options === false || ($remainingIndex !== null && $remainingIndex < $argc)) {
        throw new InvalidArgumentException('Unknown or incomplete retention option');
    }
    $apply = array_key_exists('apply', $options);
    $eventDays = retention_integer_option(
        $options, 'events-days', OPPW_EVENT_RETENTION_DAYS, OPPW_EVENT_RETENTION_DAYS, 3650
    );
    $equityDays = retention_integer_option(
        $options, 'equity-days', OPPW_EQUITY_RETENTION_DAYS, OPPW_EQUITY_RETENTION_DAYS, 3650
    );
    $batchSize = retention_integer_option($options, 'batch-size', OPPW_RETENTION_BATCH_SIZE, 1440, 10000);
    $maxBatches = retention_integer_option($options, 'max-batches', OPPW_RETENTION_MAX_BATCHES, 1, 1000);
    $utc = new DateTimeZone('UTC');
    $today = new DateTimeImmutable('today', $utc);
    $eventCutoff = mysql_datetime($today->modify("-$eventDays days"));
    $equityCutoff = mysql_datetime($today->modify("-$equityDays days"));
    $archiveDirectory = $apply ? retention_archive_directory($options) : null;
    $db = pdo();

    $lock = $db->query("SELECT GET_LOCK('" . OPPW_RETENTION_LOCK . "', 0)")->fetchColumn();
    if ((int)$lock !== 1) throw new RuntimeException('Another retention run owns the database lock');
    try {
        $eligibleEvents = retention_count(
            $db, "SELECT COUNT(*) FROM strategy_events WHERE event_time < ? AND name <> 'EXECUTION_STAGE'", [$eventCutoff]
        );
        $eligibleEquity = retention_count(
            $db, 'SELECT COUNT(*) FROM strategy_equity_points WHERE captured_minute < ?', [$equityCutoff]
        );
        $result = [
            'ok' => true,
            'mode' => $apply ? 'apply' : 'dry-run',
            'generatedAt' => atom_datetime(utc_now()),
            'policy' => [
                'ordinaryEventDays' => $eventDays,
                'equityMinuteDays' => $equityDays,
                'marketMinuteOhlc' => 'indefinite-online',
                'executionStageEvents' => 'indefinite-online',
                'serviceControlAudit' => 'indefinite-online',
                'authoritativeRecords' => 'indefinite-online',
            ],
            'datasets' => [
                'strategy_events' => ['cutoffAt' => $eventCutoff, 'eligibleRows' => $eligibleEvents, 'archivedRows' => 0, 'batches' => 0, 'archives' => []],
                'strategy_equity_points' => ['cutoffAt' => $equityCutoff, 'eligibleRows' => $eligibleEquity, 'archivedRows' => 0, 'batches' => 0, 'archives' => []],
            ],
        ];

        if ($apply) {
            foreach ([
                ['dataset' => 'strategy_events', 'cutoff' => $eventCutoff, 'fetch' => 'retention_event_batch', 'apply' => 'retention_apply_event_batch'],
                ['dataset' => 'strategy_equity_points', 'cutoff' => $equityCutoff, 'fetch' => 'retention_equity_batch', 'apply' => 'retention_apply_equity_batch'],
            ] as $job) {
                for ($batch = 0; $batch < $maxBatches; $batch++) {
                    $rows = $job['fetch']($db, $job['cutoff'], $batchSize);
                    if (!$rows) break;
                    $startedAt = utc_now();
                    $archive = retention_write_archive(
                        (string)$archiveDirectory, $job['dataset'], $job['cutoff'], $rows, $startedAt
                    );
                    retention_start_run($db, $job['dataset'], $job['cutoff'], $archive, $startedAt);
                    try {
                        $job['apply']($db, $job['cutoff'], $rows, $archive);
                    } catch (Throwable $error) {
                        retention_fail_run($db, $archive['runId'], $error);
                        throw $error;
                    }
                    $result['datasets'][$job['dataset']]['archivedRows'] += count($rows);
                    $result['datasets'][$job['dataset']]['batches']++;
                    $result['datasets'][$job['dataset']]['archives'][] = [
                        'name' => $archive['archiveName'], 'sha256' => $archive['sha256'], 'rows' => count($rows),
                    ];
                }
                $remaining = retention_count(
                    $db,
                    $job['dataset'] === 'strategy_events'
                        ? "SELECT COUNT(*) FROM strategy_events WHERE event_time < ? AND name <> 'EXECUTION_STAGE'"
                        : 'SELECT COUNT(*) FROM strategy_equity_points WHERE captured_minute < ?',
                    [$job['cutoff']]
                );
                $result['datasets'][$job['dataset']]['remainingEligibleRows'] = $remaining;
                $result['datasets'][$job['dataset']]['batchLimitReached'] = $remaining > 0;
            }
        }
        echo json_encode($result, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE | JSON_THROW_ON_ERROR) . PHP_EOL;
    } finally {
        $db->query("SELECT RELEASE_LOCK('" . OPPW_RETENTION_LOCK . "')");
    }
} catch (Throwable $error) {
    fwrite(STDERR, json_encode([
        'ok' => false,
        'error' => $error->getMessage(),
    ], JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE) . PHP_EOL);
    exit(1);
}
