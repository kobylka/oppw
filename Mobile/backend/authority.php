<?php
declare(strict_types=1);

/** v51 immutable-authority persistence shared by snapshot and event ingestion. */

function oppw_canonical_value(mixed $value): mixed
{
    if (!is_array($value)) return $value;
    $isList = $value === [] || array_keys($value) === range(0, count($value) - 1);
    if ($isList) return array_map('oppw_canonical_value', $value);
    ksort($value, SORT_STRING);
    foreach ($value as $key => $item) $value[$key] = oppw_canonical_value($item);
    return $value;
}

function oppw_canonical_json(array $value): string
{
    return json_encode(
        oppw_canonical_value($value),
        JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE | JSON_PRESERVE_ZERO_FRACTION | JSON_THROW_ON_ERROR
    );
}

function oppw_payload_hash(array $value): string
{
    return hash('sha256', oppw_canonical_json($value));
}

function oppw_nullable_number(mixed $value): ?float
{
    return is_numeric($value) ? (float)$value : null;
}

function oppw_nullable_bool(mixed $value): ?int
{
    if ($value === null || $value === '' || strtolower((string)$value) === 'none') return null;
    if (is_bool($value)) return $value ? 1 : 0;
    if (is_int($value) || is_float($value)) return ((float)$value) != 0.0 ? 1 : 0;
    $normalized = strtolower(trim((string)$value));
    if (in_array($normalized, ['true', 'yes', 'on', '1'], true)) return 1;
    if (in_array($normalized, ['false', 'no', 'off', '0'], true)) return 0;
    return null;
}

function oppw_current_spec_id(PDO $db, string $accountKey): ?string
{
    $stmt = $db->prepare(
        'SELECT spec_id FROM strategy_account_spec_assignments
          WHERE strategy_key=? ORDER BY assigned_at DESC,id DESC LIMIT 1'
    );
    $stmt->execute([$accountKey]);
    $value = $stmt->fetchColumn();
    return is_string($value) && $value !== '' ? $value : null;
}

function oppw_store_strategy_specification(
    PDO $db,
    string $accountKey,
    array $specification,
    array $coordination,
    string $capturedAt
): array {
    $document = is_array($specification['document'] ?? null) ? $specification['document'] : null;
    if ($document === null) throw new RuntimeException('strategy specification document required');
    $computedHash = oppw_payload_hash($document);
    $suppliedHash = strtolower(trim((string)($specification['specHash'] ?? '')));
    $specId = strtolower(trim((string)($specification['specId'] ?? '')));
    if (!preg_match('/^[a-f0-9]{64}$/', $suppliedHash) || !hash_equals($computedHash, $suppliedHash)) {
        throw new RuntimeException('strategy specification hash mismatch');
    }
    if (!preg_match('/^[a-f0-9]{32}$/', $specId) || !hash_equals(substr($computedHash, 0, 32), $specId)) {
        throw new RuntimeException('strategy specification id mismatch');
    }

    $documentJson = oppw_canonical_json($document);
    $effectiveFrom = normalize_datetime($specification['effectiveFrom'] ?? $capturedAt);
    $createdAt = normalize_datetime($specification['createdAt'] ?? $capturedAt);
    $insert = $db->prepare(
        'INSERT IGNORE INTO strategy_specifications(
            spec_id,spec_hash,spec_key,spec_version,effective_from,created_at,strategy_build,
            execution_symbol,signal_symbol,document,document_hash
         ) VALUES (?,?,?,?,?,?,?,?,?,?,?)'
    );
    $insert->execute([
        $specId, $computedHash, substr((string)($specification['specKey'] ?? 'OPPW24'), 0, 64),
        substr((string)($specification['specVersion'] ?? '51'), 0, 32), $effectiveFrom, $createdAt,
        substr((string)($specification['build'] ?? ''), 0, 160),
        substr((string)($document['instruments']['execution'] ?? ''), 0, 32),
        substr((string)($document['instruments']['signal'] ?? ''), 0, 32),
        $documentJson, $computedHash,
    ]);
    $verify = $db->prepare('SELECT spec_hash,document_hash FROM strategy_specifications WHERE spec_id=?');
    $verify->execute([$specId]);
    $stored = $verify->fetch();
    if (!is_array($stored) || !hash_equals($computedHash, (string)$stored['spec_hash']) || !hash_equals($computedHash, (string)$stored['document_hash'])) {
        throw new RuntimeException('immutable strategy specification conflict');
    }

    $assign = $db->prepare(
        'INSERT IGNORE INTO strategy_account_spec_assignments(
            strategy_key,spec_id,assigned_at,owner_id,fencing_token,strategy_build
         ) VALUES (?,?,?,?,?,?)'
    );
    $assign->execute([
        $accountKey, $specId, $capturedAt,
        substr((string)($coordination['ownerId'] ?? ''), 0, 32),
        (int)($coordination['fencingToken'] ?? 0),
        substr((string)($specification['build'] ?? ''), 0, 160),
    ]);
    return ['stored' => true, 'specId' => $specId, 'specHash' => $computedHash];
}

function oppw_authority_event(
    PDO $db,
    string $accountKey,
    array $event,
    string $eventHash,
    string $receivedAt
): array {
    $name = strtoupper((string)($event['name'] ?? ''));
    $details = is_array($event['details'] ?? null) ? $event['details'] : [];
    $eventTime = normalize_datetime($event['time'] ?? $receivedAt);
    $specId = substr((string)($details['strategy_spec_id'] ?? ''), 0, 32);
    if ($specId === '') $specId = (string)(oppw_current_spec_id($db, $accountKey) ?? '');
    $specValue = $specId !== '' ? $specId : null;
    $payload = ['name' => $name, 'time' => $eventTime, 'result' => $event['result'] ?? null, 'details' => $details];
    $payloadJson = oppw_canonical_json($payload);
    $payloadHash = hash('sha256', $payloadJson);
    $counts = ['stages' => 0, 'fills' => 0, 'protections' => 0, 'trades' => 0];

    if ($name === 'EXECUTION_STAGE') {
        $stage = strtoupper(substr((string)($details['stage'] ?? ''), 0, 40));
        $executionId = substr((string)($details['execution_id'] ?? ''), 0, 96);
        if ($stage !== '' && $executionId !== '') {
            $stmt = $db->prepare(
                'INSERT IGNORE INTO strategy_execution_stages(
                    strategy_key,stage_record_id,execution_id,decision_id,spec_id,position_ticket,stage,
                    occurred_at,scheduled_at,result,reference_price,actual_price,latency_ms,retcode,
                    filling_mode,reason,order_ticket,deal_ticket,side,volume,payload,payload_hash,received_at
                 ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)'
            );
            $scheduled = trim((string)($details['scheduled_at'] ?? ''));
            $stmt->execute([
                $accountKey, $eventHash, $executionId,
                ($details['decision_id'] ?? '') !== '' ? substr((string)$details['decision_id'], 0, 32) : null,
                $specValue, (int)($details['position_ticket'] ?? 0), $stage, $eventTime,
                $scheduled !== '' && strtolower($scheduled) !== 'none' ? normalize_datetime($scheduled) : null,
                oppw_nullable_bool($details['result'] ?? null),
                oppw_nullable_number($details['reference_price'] ?? null), oppw_nullable_number($details['actual_price'] ?? null),
                oppw_nullable_number($details['latency_ms'] ?? null), is_numeric($details['retcode'] ?? null) ? (int)$details['retcode'] : null,
                substr((string)($details['filling_mode'] ?? ''), 0, 32), substr((string)($details['reason'] ?? ''), 0, 100),
                (int)($details['order_ticket'] ?? 0), (int)($details['deal_ticket'] ?? 0),
                substr(strtoupper((string)($details['side'] ?? '')), 0, 8), oppw_nullable_number($details['volume'] ?? null),
                $payloadJson, $payloadHash, $receivedAt,
            ]);
            $counts['stages'] += $stmt->rowCount();

            if (in_array($stage, ['FILLED', 'EXIT_FILLED'], true) && (float)($details['actual_price'] ?? 0) > 0) {
                $fillId = hash('sha256', $eventHash . '|fill');
                $fill = $db->prepare(
                    'INSERT IGNORE INTO strategy_fills(
                        strategy_key,fill_record_id,execution_id,decision_id,spec_id,position_ticket,
                        order_ticket,deal_ticket,side,filled_at,reference_price,fill_price,volume,
                        retcode,filling_mode,fill_source,is_exact,payload,payload_hash,received_at
                     ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)'
                );
                $fill->execute([
                    $accountKey, $fillId, $executionId,
                    ($details['decision_id'] ?? '') !== '' ? substr((string)$details['decision_id'], 0, 32) : null,
                    $specValue, (int)($details['position_ticket'] ?? 0), (int)($details['order_ticket'] ?? 0),
                    (int)($details['deal_ticket'] ?? 0), substr(strtoupper((string)($details['side'] ?? ($stage === 'EXIT_FILLED' ? 'SELL' : 'BUY'))), 0, 8),
                    $eventTime, oppw_nullable_number($details['reference_price'] ?? null), (float)$details['actual_price'],
                    oppw_nullable_number($details['volume'] ?? null), is_numeric($details['retcode'] ?? null) ? (int)$details['retcode'] : null,
                    substr((string)($details['filling_mode'] ?? ''), 0, 32), 'EXECUTION_STAGE',
                    (int)((int)($details['deal_ticket'] ?? 0) > 0), $payloadJson, $payloadHash, $receivedAt,
                ]);
                $counts['fills'] += $fill->rowCount();
            }

            if (in_array($stage, ['PROTECTION_REQUESTED', 'PROTECTED', 'MODIFIED', 'PROTECTION_REJECTED'], true)) {
                $changeId = hash('sha256', $eventHash . '|protection');
                $change = $db->prepare(
                    'INSERT IGNORE INTO strategy_protection_changes(
                        strategy_key,change_record_id,execution_id,decision_id,spec_id,position_ticket,
                        occurred_at,change_stage,old_sl,new_sl,old_tp,new_tp,reason,result,retcode,
                        payload,payload_hash,received_at
                     ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)'
                );
                $change->execute([
                    $accountKey, $changeId, $executionId,
                    ($details['decision_id'] ?? '') !== '' ? substr((string)$details['decision_id'], 0, 32) : null,
                    $specValue, (int)($details['position_ticket'] ?? 0), $eventTime, $stage,
                    oppw_nullable_number($details['old_sl'] ?? null), oppw_nullable_number($details['new_sl'] ?? null),
                    oppw_nullable_number($details['old_tp'] ?? null), oppw_nullable_number($details['new_tp'] ?? null),
                    substr((string)($details['reason'] ?? ''), 0, 160),
                    oppw_nullable_bool($details['result'] ?? null),
                    is_numeric($details['retcode'] ?? null) ? (int)$details['retcode'] : null,
                    $payloadJson, $payloadHash, $receivedAt,
                ]);
                $counts['protections'] += $change->rowCount();
            }
        }
    }

    if (in_array($name, ['POSITION_RECOVERED', 'POSITION_CLOSED'], true)) {
        $ticket = (int)($details['ticket'] ?? $details['position_identifier'] ?? 0);
        if ($ticket > 0) {
            $recordId = hash('sha256', $eventHash . '|trade');
            $trade = $db->prepare(
                'INSERT IGNORE INTO strategy_trade_ledger(
                    strategy_key,trade_record_id,position_ticket,execution_id,decision_id,spec_id,
                    transition_type,occurred_at,symbol,side,volume,price,reason,payload,payload_hash,received_at
                 ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)'
            );
            $trade->execute([
                $accountKey, $recordId, $ticket, substr((string)($details['execution_id'] ?? ''), 0, 96),
                ($details['decision_id'] ?? '') !== '' ? substr((string)$details['decision_id'], 0, 32) : null,
                $specValue, $name === 'POSITION_CLOSED' ? 'CLOSED' : 'RECOVERED', $eventTime,
                substr((string)($details['symbol'] ?? ''), 0, 32), 'BUY', oppw_nullable_number($details['volume'] ?? null),
                oppw_nullable_number($details[$name === 'POSITION_CLOSED' ? 'exit' : 'entry'] ?? null),
                substr((string)($details['reason'] ?? ''), 0, 100), $payloadJson, $payloadHash, $receivedAt,
            ]);
            $counts['trades'] += $trade->rowCount();
        }
    }
    return $counts;
}

function oppw_store_trade_transition(
    PDO $db,
    string $accountKey,
    string $transition,
    array $position,
    array $snapshot,
    string $occurredAt,
    string $reason = ''
): int {
    $ticket = (int)($position['ticket'] ?? 0);
    if ($ticket <= 0) return 0;
    $execution = is_array($snapshot['execution'] ?? null) ? $snapshot['execution'] : [];
    $spec = is_array($snapshot['strategySpecification'] ?? null) ? $snapshot['strategySpecification'] : [];
    $specId = substr((string)($spec['specId'] ?? ''), 0, 32);
    if ($specId === '' && empty($snapshot['authorityNoSpecFallback'])) {
        $specId = (string)(oppw_current_spec_id($db, $accountKey) ?? '');
    }
    $payload = ['transition' => $transition, 'position' => $position, 'execution' => $execution, 'reason' => $reason];
    $payloadJson = oppw_canonical_json($payload);
    $payloadHash = hash('sha256', $payloadJson);
    $recordId = hash('sha256', $accountKey . '|' . $ticket . '|' . $transition . '|' . $occurredAt . '|' . $payloadHash);
    $stmt = $db->prepare(
        'INSERT IGNORE INTO strategy_trade_ledger(
            strategy_key,trade_record_id,position_ticket,execution_id,decision_id,spec_id,
            transition_type,occurred_at,symbol,side,volume,price,reason,payload,payload_hash,received_at
         ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)'
    );
    $stmt->execute([
        $accountKey, $recordId, $ticket, substr((string)($execution['executionId'] ?? ''), 0, 96),
        ($execution['decisionId'] ?? '') !== '' ? substr((string)$execution['decisionId'], 0, 32) : null,
        $specId !== '' ? $specId : null, substr($transition, 0, 32), $occurredAt,
        substr((string)($position['symbol'] ?? ''), 0, 32), substr((string)($position['side'] ?? 'BUY'), 0, 8),
        oppw_nullable_number($position['volume'] ?? null),
        oppw_nullable_number($position[$transition === 'CLOSED' ? 'bid' : 'openPrice'] ?? null),
        substr($reason, 0, 100), $payloadJson, $payloadHash, $occurredAt,
    ]);
    $inserted = $stmt->rowCount();
    if ($transition === 'CLOSED' && empty($snapshot['authoritySkipReconciledFill'])) {
        $market = is_array($snapshot['market'] ?? null) ? $snapshot['market'] : [];
        $reconciledPrice = oppw_nullable_number($market['currentPrice'] ?? $position['bid'] ?? null);
        if ($reconciledPrice !== null && $reconciledPrice > 0) {
            $fillRecordId = hash('sha256', $recordId . '|reconciled-close-fill');
            $fillPayload = [
                'source' => 'POSITION_DISAPPEARANCE_RECONCILIATION',
                'tradeRecordId' => $recordId,
                'position' => $position,
                'market' => $market,
                'reason' => $reason,
            ];
            $fillPayloadJson = oppw_canonical_json($fillPayload);
            $fillPayloadHash = hash('sha256', $fillPayloadJson);
            $fill = $db->prepare(
                'INSERT IGNORE INTO strategy_fills(
                    strategy_key,fill_record_id,execution_id,decision_id,spec_id,position_ticket,
                    order_ticket,deal_ticket,side,filled_at,reference_price,fill_price,volume,
                    retcode,filling_mode,fill_source,is_exact,payload,payload_hash,received_at
                 ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)'
            );
            $fill->execute([
                $accountKey,$fillRecordId,substr((string)($execution['executionId'] ?? ''),0,96),
                ($execution['decisionId'] ?? '') !== '' ? substr((string)$execution['decisionId'],0,32) : null,
                $specId !== '' ? $specId : null,$ticket,0,0,'SELL',$occurredAt,null,$reconciledPrice,
                oppw_nullable_number($position['volume'] ?? null),null,'','POSITION_DISAPPEARANCE_RECONCILIATION',0,
                $fillPayloadJson,$fillPayloadHash,$occurredAt,
            ]);
        }
    }
    return $inserted;
}
