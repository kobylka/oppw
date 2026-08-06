<?php
declare(strict_types=1);

const OPPW_ANALYTICS_CACHE_FORMAT = 'OPPW_ANALYTICS_CACHE_V1';
const OPPW_ANALYTICS_CACHE_MAX_BYTES = 33554432;
const OPPW_ANALYTICS_SEGMENT_FORMAT = 'OPPW_ANALYTICS_SEGMENT_V1';
const OPPW_ANALYTICS_SEGMENT_MAX_BYTES = 33554432;

final class OppwAnalyticsSegmentLimitException extends RuntimeException
{
}

function oppw_analytics_cache_ttl_seconds(array $cfg): int
{
    $value = filter_var(
        $cfg['analytics_cache_ttl_seconds'] ?? 30,
        FILTER_VALIDATE_INT,
        ['options' => ['min_range' => 1, 'max_range' => 120]]
    );
    return $value === false ? 30 : (int)$value;
}

function oppw_analytics_segment_ttl_seconds(array $cfg): int
{
    $value = filter_var(
        $cfg['analytics_segment_cache_ttl_seconds'] ?? 86400,
        FILTER_VALIDATE_INT,
        ['options' => ['min_range' => 300, 'max_range' => 2592000]]
    );
    return $value === false ? 86400 : (int)$value;
}

function oppw_analytics_cache_normalize(mixed $value): mixed
{
    if (!is_array($value)) return $value;
    if (array_is_list($value)) {
        return array_map('oppw_analytics_cache_normalize', $value);
    }

    $keys = array_keys($value);
    sort($keys, SORT_STRING);
    $normalized = [];
    foreach ($keys as $key) {
        $normalized[(string)$key] = oppw_analytics_cache_normalize($value[$key]);
    }
    return $normalized;
}

function oppw_analytics_cache_identifiers(array $requestContext, string $dataWatermark): array
{
    $canonical = json_encode(
        oppw_analytics_cache_normalize($requestContext),
        JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE | JSON_THROW_ON_ERROR
    );
    $slot = hash('sha256', OPPW_ANALYTICS_CACHE_FORMAT . "\0" . $canonical);
    $key = hash('sha256', OPPW_ANALYTICS_CACHE_FORMAT . "\0" . $canonical . "\0" . $dataWatermark);
    return ['slot' => $slot, 'key' => $key];
}

function oppw_analytics_cache_directory(array $cfg): ?string
{
    $configured = trim((string)($cfg['analytics_cache_dir'] ?? ''));
    if ($configured !== '' && !preg_match('/^(?:[A-Za-z]:[\\\\\/]|\\\\\\\\|\/)/', $configured)) return null;
    $namespace = substr(hash_hmac(
        'sha256',
        (string)($cfg['dsn'] ?? 'default'),
        (string)($cfg['rate_limit_hmac_secret'] ?? 'analytics-cache-local')
    ), 0, 16);
    $directory = $configured !== ''
        ? rtrim($configured, "\\/")
        : rtrim(sys_get_temp_dir(), "\\/") . DIRECTORY_SEPARATOR . 'oppw-analytics-cache-' . $namespace;
    if ($directory === '' || str_contains($directory, "\0")) return null;
    if (is_link($directory)) return null;
    if (!is_dir($directory) && !@mkdir($directory, 0700, true) && !is_dir($directory)) return null;
    $resolvedDirectory = realpath($directory);
    $resolvedWebRoot = realpath(__DIR__);
    if ($resolvedDirectory === false || $resolvedWebRoot === false) return null;
    $pathCase = DIRECTORY_SEPARATOR === '\\' ? 'strtolower' : static fn(string $path): string => $path;
    $normalizedDirectory = rtrim(str_replace('\\', '/', $pathCase($resolvedDirectory)), '/');
    $normalizedWebRoot = rtrim(str_replace('\\', '/', $pathCase($resolvedWebRoot)), '/');
    if ($normalizedDirectory === $normalizedWebRoot
        || str_starts_with($normalizedDirectory . '/', $normalizedWebRoot . '/')) {
        return null;
    }
    @chmod($directory, 0700);
    return is_writable($directory) ? $directory : null;
}

function oppw_analytics_cache_entry_path(array $cfg, string $slot): ?string
{
    if (!preg_match('/^[a-f0-9]{64}$/', $slot)) return null;
    $directory = oppw_analytics_cache_directory($cfg);
    if ($directory === null) return null;
    return $directory . DIRECTORY_SEPARATOR . 'analytics-v1-' . $slot . '.cache';
}

function oppw_analytics_cache_read(array $cfg, string $slot, string $expectedKey): ?string
{
    if (!preg_match('/^[a-f0-9]{64}$/', $expectedKey)) return null;
    $path = oppw_analytics_cache_entry_path($cfg, $slot);
    if ($path === null || is_link($path) || !is_file($path)) return null;

    $handle = @fopen($path, 'rb');
    if ($handle === false) return null;
    $stale = false;
    try {
        if (!flock($handle, LOCK_SH)) return null;
        $stat = fstat($handle);
        $modifiedAt = is_array($stat) ? (int)($stat['mtime'] ?? 0) : 0;
        if ($modifiedAt <= 0 || time() - $modifiedAt > oppw_analytics_cache_ttl_seconds($cfg)) {
            $stale = true;
            return null;
        }

        $format = rtrim((string)fgets($handle, 128), "\r\n");
        $storedKey = rtrim((string)fgets($handle, 128), "\r\n");
        $storedDigest = rtrim((string)fgets($handle, 128), "\r\n");
        if ($format !== OPPW_ANALYTICS_CACHE_FORMAT || !hash_equals($expectedKey, $storedKey)) return null;
        if (!preg_match('/^[a-f0-9]{64}$/', $storedDigest)) return null;

        $payload = stream_get_contents($handle, OPPW_ANALYTICS_CACHE_MAX_BYTES + 1);
        if ($payload === false || $payload === '' || strlen($payload) > OPPW_ANALYTICS_CACHE_MAX_BYTES) return null;
        if (!hash_equals($storedDigest, oppw_analytics_cache_payload_digest($cfg, $payload))) return null;
        return $payload;
    } finally {
        @flock($handle, LOCK_UN);
        fclose($handle);
        if ($stale) @unlink($path);
    }
}

function oppw_analytics_cache_write(array $cfg, string $slot, string $key, string $payload): bool
{
    if (!preg_match('/^[a-f0-9]{64}$/', $key)
        || $payload === ''
        || strlen($payload) > OPPW_ANALYTICS_CACHE_MAX_BYTES) {
        return false;
    }
    $path = oppw_analytics_cache_entry_path($cfg, $slot);
    if ($path === null || is_link($path)) return false;

    $content = OPPW_ANALYTICS_CACHE_FORMAT . "\n"
        . $key . "\n"
        . oppw_analytics_cache_payload_digest($cfg, $payload) . "\n"
        . $payload;
    $handle = @fopen($path, 'c+b');
    if ($handle === false) return false;
    $written = 0;
    try {
        if (!flock($handle, LOCK_EX) || !ftruncate($handle, 0) || !rewind($handle)) return false;
        $length = strlen($content);
        while ($written < $length) {
            $count = fwrite($handle, substr($content, $written));
            if ($count === false || $count === 0) return false;
            $written += $count;
        }
        if (!fflush($handle)) return false;
    } finally {
        @flock($handle, LOCK_UN);
        fclose($handle);
    }
    @chmod($path, 0600);
    oppw_analytics_cache_cleanup($cfg, $path);
    return $written === strlen($content);
}

function oppw_analytics_cache_payload_digest(array $cfg, string $payload): string
{
    return hash_hmac(
        'sha256',
        OPPW_ANALYTICS_CACHE_FORMAT . "\0" . $payload,
        (string)($cfg['rate_limit_hmac_secret'] ?? 'analytics-cache-local')
    );
}

function oppw_analytics_segment_identifiers(array $cfg, array $context): array
{
    $canonical = json_encode(
        oppw_analytics_cache_normalize($context),
        JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE | JSON_THROW_ON_ERROR
    );
    $slot = hash('sha256', OPPW_ANALYTICS_SEGMENT_FORMAT . "\0" . $canonical);
    $key = hash_hmac(
        'sha256',
        OPPW_ANALYTICS_SEGMENT_FORMAT . "\0" . $canonical,
        (string)($cfg['rate_limit_hmac_secret'] ?? 'analytics-segment-local')
    );
    return ['slot' => $slot, 'key' => $key];
}

function oppw_analytics_segment_entry_path(array $cfg, string $slot): ?string
{
    if (!preg_match('/^[a-f0-9]{64}$/', $slot)) return null;
    $directory = oppw_analytics_cache_directory($cfg);
    if ($directory === null) return null;
    return $directory . DIRECTORY_SEPARATOR . 'analytics-segment-v1-' . $slot . '.cache';
}

function oppw_analytics_segment_payload_digest(array $cfg, string $payload): string
{
    return hash_hmac(
        'sha256',
        OPPW_ANALYTICS_SEGMENT_FORMAT . "\0" . $payload,
        (string)($cfg['rate_limit_hmac_secret'] ?? 'analytics-segment-local')
    );
}

function oppw_analytics_segment_read(array $cfg, string $slot, string $expectedKey, int $rowLimit): ?array
{
    if (!preg_match('/^[a-f0-9]{64}$/', $expectedKey) || $rowLimit < 1) return null;
    $path = oppw_analytics_segment_entry_path($cfg, $slot);
    if ($path === null || is_link($path) || !is_file($path)) return null;

    $handle = @fopen($path, 'rb');
    if ($handle === false) return null;
    $stale = false;
    try {
        if (!flock($handle, LOCK_SH)) return null;
        $stat = fstat($handle);
        $modifiedAt = is_array($stat) ? (int)($stat['mtime'] ?? 0) : 0;
        if ($modifiedAt <= 0 || time() - $modifiedAt > oppw_analytics_segment_ttl_seconds($cfg)) {
            $stale = true;
            return null;
        }
        $format = rtrim((string)fgets($handle, 128), "\r\n");
        $storedKey = rtrim((string)fgets($handle, 128), "\r\n");
        $storedDigest = rtrim((string)fgets($handle, 128), "\r\n");
        if ($format !== OPPW_ANALYTICS_SEGMENT_FORMAT || !hash_equals($expectedKey, $storedKey)) return null;
        if (!preg_match('/^[a-f0-9]{64}$/', $storedDigest)) return null;
        $payload = stream_get_contents($handle, OPPW_ANALYTICS_SEGMENT_MAX_BYTES + 1);
        if ($payload === false || strlen($payload) > OPPW_ANALYTICS_SEGMENT_MAX_BYTES) return null;
        if (!hash_equals($storedDigest, oppw_analytics_segment_payload_digest($cfg, $payload))) return null;
        $rows = json_decode($payload, true, 512, JSON_THROW_ON_ERROR);
        if (!is_array($rows) || !array_is_list($rows) || count($rows) > $rowLimit) return null;
        return $rows;
    } catch (Throwable) {
        return null;
    } finally {
        @flock($handle, LOCK_UN);
        fclose($handle);
        if ($stale) @unlink($path);
    }
}

function oppw_analytics_segment_write(array $cfg, string $slot, string $key, array $rows, bool $cleanup = true): bool
{
    if (!preg_match('/^[a-f0-9]{64}$/', $key) || !array_is_list($rows)) return false;
    try {
        $payload = json_encode($rows, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE | JSON_THROW_ON_ERROR);
    } catch (Throwable) {
        return false;
    }
    if (strlen($payload) > OPPW_ANALYTICS_SEGMENT_MAX_BYTES) return false;
    $path = oppw_analytics_segment_entry_path($cfg, $slot);
    if ($path === null || is_link($path)) return false;
    $content = OPPW_ANALYTICS_SEGMENT_FORMAT . "\n"
        . $key . "\n"
        . oppw_analytics_segment_payload_digest($cfg, $payload) . "\n"
        . $payload;
    $handle = @fopen($path, 'c+b');
    if ($handle === false) return false;
    $written = 0;
    try {
        if (!flock($handle, LOCK_EX) || !ftruncate($handle, 0) || !rewind($handle)) return false;
        $length = strlen($content);
        while ($written < $length) {
            $count = fwrite($handle, substr($content, $written));
            if ($count === false || $count === 0) return false;
            $written += $count;
        }
        if (!fflush($handle)) return false;
    } finally {
        @flock($handle, LOCK_UN);
        fclose($handle);
    }
    @chmod($path, 0600);
    if ($cleanup) oppw_analytics_segment_cleanup($cfg, $path);
    return $written === strlen($content);
}

function oppw_analytics_segment_cleanup(array $cfg, string $currentPath): void
{
    $directory = dirname($currentPath);
    $cutoff = time() - max(172800, oppw_analytics_segment_ttl_seconds($cfg) * 2);
    try {
        $visited = 0;
        foreach (new FilesystemIterator($directory, FilesystemIterator::SKIP_DOTS) as $file) {
            if (++$visited > 128) break;
            $path = $file->getPathname();
            if ($path === $currentPath
                || !$file->isFile()
                || !preg_match('/^analytics-segment-v1-[a-f0-9]{64}\.cache$/', $file->getFilename())) {
                continue;
            }
            if ($file->getMTime() < $cutoff) @unlink($path);
        }
    } catch (Throwable) {
    }
}

function oppw_analytics_week_segments(
    DateTimeImmutable $windowStartUtc,
    DateTimeImmutable $windowEndUtc,
    ?DateTimeImmutable $now = null
): array {
    if ($windowStartUtc >= $windowEndUtc) return ['completed' => [], 'live' => null];
    $warsaw = new DateTimeZone('Europe/Warsaw');
    $utc = new DateTimeZone('UTC');
    $now ??= new DateTimeImmutable('now', $utc);
    $currentWeekLocal = $now->setTimezone($warsaw)->modify('monday this week')->setTime(0, 0, 0, 0);
    $lastIncluded = $windowEndUtc->modify('-1 microsecond')->setTimezone($warsaw);
    $lastWindowWeekLocal = $lastIncluded->modify('monday this week')->setTime(0, 0, 0, 0);
    $completedUntilLocal = $currentWeekLocal < $lastWindowWeekLocal ? $currentWeekLocal : $lastWindowWeekLocal;
    $completedUntilUtc = $completedUntilLocal->setTimezone($utc);
    if ($completedUntilUtc < $windowStartUtc) $completedUntilUtc = $windowStartUtc;
    if ($completedUntilUtc > $windowEndUtc) $completedUntilUtc = $windowEndUtc;

    $completed = [];
    $cursor = $windowStartUtc;
    while ($cursor < $completedUntilUtc) {
        $cursorLocal = $cursor->setTimezone($warsaw);
        $nextLocal = $cursorLocal->modify('monday next week')->setTime(0, 0, 0, 0);
        $next = $nextLocal->setTimezone($utc);
        if ($next <= $cursor) $next = $cursor->modify('+7 days');
        if ($next > $completedUntilUtc) $next = $completedUntilUtc;
        $completed[] = ['start' => $cursor, 'end' => $next];
        $cursor = $next;
    }
    $live = $completedUntilUtc < $windowEndUtc
        ? ['start' => $completedUntilUtc, 'end' => $windowEndUtc]
        : null;
    return ['completed' => $completed, 'live' => $live];
}

function oppw_analytics_segment_stats(): array
{
    return ['hits' => 0, 'misses' => 0, 'liveQueries' => 0, 'cacheRows' => 0, 'databaseRows' => 0, 'cleanupRuns' => 0];
}

function oppw_analytics_segmented_rows(
    array $cfg,
    array $context,
    DateTimeImmutable $windowStartUtc,
    DateTimeImmutable $windowEndUtc,
    callable $loader,
    array &$stats,
    int $rowLimitPerSegment = 100000,
    ?DateTimeImmutable $now = null,
    ?int $rowLimitTotal = null
): Generator {
    if ($rowLimitTotal !== null && $rowLimitTotal < 1) {
        throw new InvalidArgumentException('Analytics total row limit must be positive');
    }
    $totalRows = 0;
    $cleanupPending = true;
    $segments = oppw_analytics_week_segments($windowStartUtc, $windowEndUtc, $now);
    foreach ($segments['completed'] as $range) {
        $segmentContext = array_merge($context, [
            'segmentStart' => $range['start']->format('Y-m-d\TH:i:s.uP'),
            'segmentEnd' => $range['end']->format('Y-m-d\TH:i:s.uP'),
        ]);
        $identity = oppw_analytics_segment_identifiers($cfg, $segmentContext);
        $rows = oppw_analytics_segment_read($cfg, $identity['slot'], $identity['key'], $rowLimitPerSegment);
        if ($rows === null) {
            $stats['misses']++;
            $rows = [];
            foreach ($loader($range['start'], $range['end'], $rowLimitPerSegment + 1) as $row) {
                $rows[] = $row;
                if (count($rows) > $rowLimitPerSegment) {
                    throw new OppwAnalyticsSegmentLimitException('Analytics weekly segment exceeds its row limit');
                }
            }
            $stats['databaseRows'] += count($rows);
            oppw_analytics_segment_write($cfg, $identity['slot'], $identity['key'], $rows, $cleanupPending);
            if ($cleanupPending) {
                $stats['cleanupRuns']++;
                $cleanupPending = false;
            }
        } else {
            $stats['hits']++;
            $stats['cacheRows'] += count($rows);
        }
        foreach ($rows as $row) {
            if ($rowLimitTotal !== null && ++$totalRows > $rowLimitTotal) {
                throw new OppwAnalyticsSegmentLimitException('Analytics request exceeds its total row limit');
            }
            yield $row;
        }
        unset($rows);
    }
    if (is_array($segments['live'])) {
        $stats['liveQueries']++;
        $liveRows = 0;
        foreach ($loader($segments['live']['start'], $segments['live']['end'], $rowLimitPerSegment + 1) as $row) {
            if (++$liveRows > $rowLimitPerSegment) {
                throw new OppwAnalyticsSegmentLimitException('Analytics live segment exceeds its row limit');
            }
            if ($rowLimitTotal !== null && ++$totalRows > $rowLimitTotal) {
                throw new OppwAnalyticsSegmentLimitException('Analytics request exceeds its total row limit');
            }
            $stats['databaseRows']++;
            yield $row;
        }
    }
}

function oppw_analytics_cache_cleanup(array $cfg, string $currentPath): void
{
    $directory = dirname($currentPath);
    $cutoff = time() - max(300, oppw_analytics_cache_ttl_seconds($cfg) * 4);
    try {
        $visited = 0;
        foreach (new FilesystemIterator($directory, FilesystemIterator::SKIP_DOTS) as $file) {
            if (++$visited > 64) break;
            $path = $file->getPathname();
            if ($path === $currentPath
                || !$file->isFile()
                || !preg_match('/^analytics-v1-[a-f0-9]{64}\.cache$/', $file->getFilename())) {
                continue;
            }
            if ($file->getMTime() < $cutoff) @unlink($path);
        }
    } catch (Throwable) {
    }
}

function oppw_analytics_data_watermark(PDO $db, array $accountKeys): string
{
    $accountKeys = array_values(array_unique(array_map(static fn(mixed $key): string => (string)$key, $accountKeys)));
    sort($accountKeys, SORT_STRING);
    if (!$accountKeys) return hash('sha256', 'no-accounts');
    $placeholders = implode(',', array_fill(0, count($accountKeys), '?'));
    $parts = ['accounts' => $accountKeys];

    $tradeStmt = $db->prepare(
        "SELECT strategy_key,COUNT(*) AS row_count,COALESCE(MAX(id),0) AS max_id,"
        . "COALESCE(DATE_FORMAT(MAX(updated_at),'%Y-%m-%d %H:%i:%s'),'') AS max_updated_at,"
        . "COALESCE(BIT_XOR(CRC32(CONCAT_WS('|',id,position_ticket,symbol,side,volume,opened_at,closed_at,"
        . "open_price,close_price,profit,profit_percent,balance_before,balance_after,mfe_points,mfe_percent,"
        . "mae_points,mae_percent,entry_slippage_points,exit_slippage_points,max_profit,max_drawdown,exit_reason,"
        . "preleverage_return_percent,trade_class,decision_id,strategy_build,parameter_hash,entry_leverage))),0) AS content_crc "
        . "FROM strategy_trades WHERE strategy_key IN ($placeholders) GROUP BY strategy_key ORDER BY strategy_key"
    );
    $tradeStmt->execute($accountKeys);
    $parts['trades'] = $tradeStmt->fetchAll();

    foreach ([
        'cashFlows' => "SELECT strategy_key,COUNT(*) AS row_count,COALESCE(MAX(id),0) AS max_id FROM account_cash_flows WHERE strategy_key IN ($placeholders) GROUP BY strategy_key ORDER BY strategy_key",
        'executionStages' => "SELECT strategy_key,COUNT(*) AS row_count,COALESCE(MAX(id),0) AS max_id FROM strategy_execution_stages WHERE strategy_key IN ($placeholders) GROUP BY strategy_key ORDER BY strategy_key",
        'diagnosticStages' => "SELECT strategy_key,COUNT(*) AS row_count,COALESCE(MAX(id),0) AS max_id FROM strategy_events WHERE strategy_key IN ($placeholders) AND name IN ('EXECUTION_STAGE','MOBILE_RECEIPT') GROUP BY strategy_key ORDER BY strategy_key",
    ] as $name => $sql) {
        $stmt = $db->prepare($sql);
        $stmt->execute($accountKeys);
        $parts[$name] = $stmt->fetchAll();
    }

    $minuteStmt = $db->prepare(
        "SELECT p.strategy_key,p.captured_minute,p.balance,p.equity,p.deposit,p.current_profit,p.position_ticket "
        . "FROM strategy_equity_points p JOIN (SELECT strategy_key,MAX(captured_minute) AS captured_minute "
        . "FROM strategy_equity_points WHERE strategy_key IN ($placeholders) GROUP BY strategy_key) latest "
        . "ON latest.strategy_key=p.strategy_key AND latest.captured_minute=p.captured_minute ORDER BY p.strategy_key"
    );
    $minuteStmt->execute($accountKeys);
    $parts['latestMinuteEquity'] = $minuteStmt->fetchAll();

    $dailyStmt = $db->prepare(
        "SELECT d.strategy_key,d.equity_day,d.first_captured_at,d.last_captured_at,d.open_balance,d.open_equity,"
        . "d.close_balance,d.close_equity,d.minimum_equity,d.maximum_equity,d.sample_count,d.updated_at "
        . "FROM strategy_equity_daily d JOIN (SELECT strategy_key,MAX(equity_day) AS equity_day "
        . "FROM strategy_equity_daily WHERE strategy_key IN ($placeholders) GROUP BY strategy_key) latest "
        . "ON latest.strategy_key=d.strategy_key AND latest.equity_day=d.equity_day ORDER BY d.strategy_key"
    );
    $dailyStmt->execute($accountKeys);
    $parts['latestDailyEquity'] = $dailyStmt->fetchAll();

    return hash('sha256', json_encode(
        oppw_analytics_cache_normalize($parts),
        JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE | JSON_THROW_ON_ERROR
    ));
}
