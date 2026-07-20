#!/usr/bin/env python3
from __future__ import annotations

import shutil
import sys
from pathlib import Path

START = "// OPPW_V47_3_V13_2_BEGIN"
END = "// OPPW_V47_3_V13_2_END"
OLD_V46_START = "// OPPW_V46_TRADING_DAY_EQUITY_BEGIN"
OLD_V46_END = "// OPPW_V46_TRADING_DAY_EQUITY_END"

MARKET_FUNCTION = r'''function build_market_week_stats(array $rows, DateTimeImmutable $weekStart, DateTimeZone $localTimezone): ?array
{
    $weekStartKey = $weekStart->format('Y-m-d');
    $weekRows = [];
    $regularRows = [];
    $currentPrice = null;

    foreach ($rows as $marketRow) {
        $local = (new DateTimeImmutable((string)$marketRow['captured_minute'], new DateTimeZone('UTC')))->setTimezone($localTimezone);
        if (strategy_week_start($local)->format('Y-m-d') !== $weekStartKey) continue;
        $weekRows[] = [$marketRow, $local];
        $price = positive_number($marketRow, 'current_price') ?? positive_number($marketRow, 'bid') ?? positive_number($marketRow, 'ask');
        if ($price !== null) $currentPrice = $price;
        if (strtoupper(trim((string)($marketRow['phase'] ?? ''))) === 'REGULAR') $regularRows[] = [$marketRow, $local];
    }

    if (!$weekRows) return null;

    $weekEnd = $weekStart->modify('+6 days');
    $emptyResult = static function () use ($weekStart, $weekEnd, $currentPrice): array {
        return [
            'week' => $weekStart->format('d M') . ' – ' . $weekEnd->format('d M Y'),
            'currentPrice' => $currentPrice,
            'weekOpen' => null,
            'weekOpenDate' => '',
            'weeklyHigh' => null,
            'weeklyLow' => null,
            'weeklyClose' => null,
            'weeklyHighPercent' => null,
            'weeklyLowPercent' => null,
            'weeklyClosePercent' => null,
            'dailyDate' => '',
            'dailyOpen' => null,
            'dailyHigh' => null,
            'dailyLow' => null,
            'dailyClose' => null,
            'dailyHighPercent' => null,
            'dailyLowPercent' => null,
            'dailyClosePercent' => null,
            'fridayOpen' => null,
            'dailyLowDate' => '',
        ];
    };

    // Current price may be premarket. Every O/H/L/C value below is REGULAR-only.
    if (!$regularRows) return $emptyResult();

    usort($regularRows, static fn(array $a, array $b): int => $a[1]->getTimestamp() <=> $b[1]->getTimestamp());
    $days = [];
    $weekOpen = null;
    $weekOpenDate = '';
    $weeklyHigh = null;
    $weeklyLow = null;
    $weeklyClose = null;

    foreach ($regularRows as [$row, $local]) {
        $dayKey = $local->format('Y-m-d');
        $price = positive_number($row, 'current_price') ?? positive_number($row, 'bid') ?? positive_number($row, 'ask');
        $open = market_point_price($row, 'm1_open', $price);
        $high = market_point_price($row, 'm1_high', $price);
        $low = market_point_price($row, 'm1_low', $price);
        $close = market_point_price($row, 'm1_close', $price);

        if (!isset($days[$dayKey])) {
            $days[$dayKey] = ['open' => $open, 'high' => null, 'low' => null, 'close' => null];
            if ($weekOpen === null && $open !== null) {
                $weekOpen = $open;
                $weekOpenDate = $dayKey;
            }
        }
        if ($days[$dayKey]['open'] === null && $open !== null) $days[$dayKey]['open'] = $open;
        if ($high !== null) {
            $days[$dayKey]['high'] = $days[$dayKey]['high'] === null ? $high : max((float)$days[$dayKey]['high'], $high);
            $weeklyHigh = $weeklyHigh === null ? $high : max($weeklyHigh, $high);
        }
        if ($low !== null) {
            $days[$dayKey]['low'] = $days[$dayKey]['low'] === null ? $low : min((float)$days[$dayKey]['low'], $low);
            $weeklyLow = $weeklyLow === null ? $low : min($weeklyLow, $low);
        }
        if ($close !== null) {
            $days[$dayKey]['close'] = $close;
            $weeklyClose = $close;
        }
    }

    if (!$days || $weekOpen === null) return $emptyResult();
    ksort($days, SORT_STRING);
    $latestDayDate = (string)(array_key_last($days) ?? '');
    $latestDay = $latestDayDate !== '' ? $days[$latestDayDate] : null;
    $relative = static fn(?float $value): ?float => $weekOpen > 0 && $value !== null ? ($value / $weekOpen - 1.0) * 100.0 : null;

    return [
        'week' => $weekStart->format('d M') . ' – ' . $weekEnd->format('d M Y'),
        'currentPrice' => $currentPrice,
        'weekOpen' => $weekOpen,
        'weekOpenDate' => $weekOpenDate,
        'weeklyHigh' => $weeklyHigh,
        'weeklyLow' => $weeklyLow,
        'weeklyClose' => $weeklyClose,
        'weeklyHighPercent' => $relative($weeklyHigh),
        'weeklyLowPercent' => $relative($weeklyLow),
        'weeklyClosePercent' => $relative($weeklyClose),
        'dailyDate' => $latestDayDate,
        'dailyOpen' => $latestDay !== null && $latestDay['open'] !== null ? (float)$latestDay['open'] : null,
        'dailyHigh' => $latestDay !== null && $latestDay['high'] !== null ? (float)$latestDay['high'] : null,
        'dailyLow' => $latestDay !== null && $latestDay['low'] !== null ? (float)$latestDay['low'] : null,
        'dailyClose' => $latestDay !== null && $latestDay['close'] !== null ? (float)$latestDay['close'] : null,
        'dailyHighPercent' => $latestDay !== null ? $relative($latestDay['high'] === null ? null : (float)$latestDay['high']) : null,
        'dailyLowPercent' => $latestDay !== null ? $relative($latestDay['low'] === null ? null : (float)$latestDay['low']) : null,
        'dailyClosePercent' => $latestDay !== null ? $relative($latestDay['close'] === null ? null : (float)$latestDay['close']) : null,
        'fridayOpen' => $weekOpen,
        'dailyLowDate' => $latestDayDate,
    ];
}'''

HELPERS = r'''
// OPPW_V47_3_V13_2_BEGIN
function oppw_valid_iso_day(mixed $value): ?string
{
    $text = trim((string)$value);
    if (!preg_match('/^\d{4}-\d{2}-\d{2}$/', $text)) return null;
    $parsed = DateTimeImmutable::createFromFormat('!Y-m-d', $text, new DateTimeZone('Europe/Warsaw'));
    return $parsed && $parsed->format('Y-m-d') === $text ? $text : null;
}

function oppw_previous_weekday(DateTimeImmutable $localDay): DateTimeImmutable
{
    $candidate = $localDay->modify('-1 day');
    while ((int)$candidate->format('N') > 5) $candidate = $candidate->modify('-1 day');
    return $candidate;
}

function oppw_equity_period_points(
    PDO $db,
    string $accountKey,
    DateTimeImmutable $startLocal,
    DateTimeImmutable $endLocal,
    int $maximum
): array {
    if ($endLocal <= $startLocal) return [];
    $utc = new DateTimeZone('UTC');
    $startUtc = $startLocal->setTimezone($utc);
    $endUtc = $endLocal->setTimezone($utc);
    $startSql = $startUtc->format('Y-m-d H:i:s');
    $endSql = $endUtc->format('Y-m-d H:i:s');

    $baselineStmt = $db->prepare(
        'SELECT captured_minute, equity FROM strategy_equity_points '
        . 'WHERE strategy_key = ? AND captured_minute <= ? '
        . 'ORDER BY captured_minute DESC LIMIT 1'
    );
    $baselineStmt->execute([$accountKey, $startSql]);
    $baseline = $baselineStmt->fetch();

    $pointsStmt = $db->prepare(
        'SELECT captured_minute, equity FROM strategy_equity_points '
        . 'WHERE strategy_key = ? AND captured_minute >= ? AND captured_minute <= ? '
        . 'ORDER BY captured_minute'
    );
    $pointsStmt->execute([$accountKey, $startSql, $endSql]);
    $stored = $pointsStmt->fetchAll();

    $startValue = $baseline && is_numeric($baseline['equity'] ?? null)
        ? (float)$baseline['equity']
        : ($stored && is_numeric($stored[0]['equity'] ?? null) ? (float)$stored[0]['equity'] : null);
    if ($startValue === null) return [];

    $rows = [['time' => atom_datetime($startUtc), 'value' => $startValue]];
    $lastValue = $startValue;
    foreach ($stored as $row) {
        if (!is_numeric($row['equity'] ?? null)) continue;
        $time = new DateTimeImmutable((string)$row['captured_minute'], $utc);
        $lastValue = (float)$row['equity'];
        if ($time <= $startUtc) {
            $rows[0]['value'] = $lastValue;
            continue;
        }
        $rows[] = ['time' => atom_datetime($time), 'value' => $lastValue];
    }

    $endAtom = atom_datetime($endUtc);
    if (!$rows || (string)end($rows)['time'] !== $endAtom) $rows[] = ['time' => $endAtom, 'value' => $lastValue];
    return downsample_points($rows, $maximum);
}

function oppw_selected_equity_periods(
    PDO $db,
    string $accountKey,
    array $snapshot,
    DateTimeImmutable $localNow,
    DateTimeZone $localTimezone
): array {
    $session = is_array($snapshot['market']['session'] ?? null) ? $snapshot['market']['session'] : [];
    $isTradingDay = array_key_exists('isTradingDay', $session)
        ? (bool)$session['isTradingDay']
        : ((int)$localNow->format('N') <= 5 && strtoupper((string)($snapshot['connection']['phase'] ?? '')) !== 'WEEKEND');

    $today = $localNow->setTimezone($localTimezone)->setTime(0, 0, 0);
    $previousTradingDayKey = oppw_valid_iso_day($session['previousTradingDay'] ?? null);
    $previousTradingDay = $previousTradingDayKey !== null
        ? new DateTimeImmutable($previousTradingDayKey . ' 00:00:00', $localTimezone)
        : oppw_previous_weekday($today);

    if ($isTradingDay) {
        $dailyStart = $today;
        $dailyEnd = $localNow;
        $weeklyStart = strategy_week_start($today);
        $weeklyEnd = $localNow;
    } else {
        $dailyStart = $previousTradingDay;
        $dailyEnd = $dailyStart->modify('+1 day');
        $thisMonday = strategy_week_start($today);
        $weeklyStart = $thisMonday->modify('-7 days');
        $weeklyEnd = $thisMonday;
    }

    return [
        'daily' => oppw_equity_period_points($db, $accountKey, $dailyStart, $dailyEnd, 144),
        'weekly' => oppw_equity_period_points($db, $accountKey, $weeklyStart, $weeklyEnd, 168),
    ];
}
// OPPW_V47_3_V13_2_END
'''

CURVES = r'''$oppwEquityPeriods = oppw_selected_equity_periods($db, $accountKey, $snapshot, $localNow, $warsaw);
$snapshot['equityCurves'] = [
    'daily' => $oppwEquityPeriods['daily'],
    'weekly' => $oppwEquityPeriods['weekly'],
    'allTime' => all_time_equity_points($db, $accountKey),
];'''


def remove_marked(text: str, start_marker: str, end_marker: str) -> str:
    while start_marker in text:
        start = text.index(start_marker)
        line_start = text.rfind("\n", 0, start) + 1
        end = text.index(end_marker, start) + len(end_marker)
        line_end = text.find("\n", end)
        if line_end < 0:
            line_end = len(text)
        text = text[:line_start] + text[line_end + (1 if line_end < len(text) else 0):]
    return text


def matching_delimiter(text: str, opening: int, open_char: str, close_char: str) -> int:
    depth = 0
    quote: str | None = None
    escaped = False
    line_comment = False
    block_comment = False
    index = opening
    while index < len(text):
        char = text[index]
        next_char = text[index + 1] if index + 1 < len(text) else ""
        if line_comment:
            if char == "\n": line_comment = False
        elif block_comment:
            if char == "*" and next_char == "/":
                block_comment = False
                index += 1
        elif quote is not None:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
        else:
            if char in ("'", '"'):
                quote = char
            elif char == "/" and next_char == "/":
                line_comment = True
                index += 1
            elif char == "#":
                line_comment = True
            elif char == "/" and next_char == "*":
                block_comment = True
                index += 1
            elif char == open_char:
                depth += 1
            elif char == close_char:
                depth -= 1
                if depth == 0: return index
        index += 1
    raise RuntimeError(f"Unmatched {open_char} at byte {opening}")


def replace_function(text: str, function_name: str, replacement: str) -> str:
    marker = f"function {function_name}"
    start = text.find(marker)
    if start < 0: raise RuntimeError(f"Could not find {marker} in status.php")
    opening = text.find("{", start)
    if opening < 0: raise RuntimeError(f"Could not find opening brace for {marker}")
    closing = matching_delimiter(text, opening, "{", "}")
    return text[:start] + replacement + text[closing + 1:]


def replace_equity_curves(text: str) -> str:
    marker = "$snapshot['equityCurves']"
    start = text.find(marker)
    if start < 0: raise RuntimeError("Could not find equityCurves assignment in status.php")
    equals = text.find("=", start)
    opening = text.find("[", equals)
    if equals < 0 or opening < 0: raise RuntimeError("Malformed equityCurves assignment")
    closing = matching_delimiter(text, opening, "[", "]")
    semicolon = text.find(";", closing)
    if semicolon < 0: raise RuntimeError("Missing semicolon after equityCurves assignment")
    # Replace a preceding generated variable assignment when re-running.
    prior = text.rfind("$oppwEquityPeriods", max(0, start - 500), start)
    if prior >= 0:
        prior_semicolon = text.find(";", prior, start)
        if prior_semicolon >= 0: start = prior
    return text[:start] + CURVES + text[semicolon + 1:]


def patch(path: Path) -> None:
    original = path.read_text(encoding="utf-8-sig")
    if not original.lstrip().startswith("<?php"):
        raise RuntimeError("status.php is truncated or is not an executable PHP file; restore the intact file before patching")
    text = remove_marked(original, START, END)
    text = remove_marked(text, OLD_V46_START, OLD_V46_END)
    text = replace_function(text, "build_market_week_stats", MARKET_FUNCTION)
    text = replace_equity_curves(text)
    anchor = "function all_time_equity_points"
    if anchor not in text: raise RuntimeError(f"Could not find {anchor} helper anchor")
    text = text.replace(anchor, HELPERS.strip() + "\n\n" + anchor, 1)
    backup = path.with_suffix(path.suffix + ".pre-v47.3-v13.2.bak")
    if not backup.exists(): shutil.copy2(path, backup)
    path.write_text(text, encoding="utf-8")


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    path = root / "Mobile/backend/status.php"
    if not path.exists(): raise RuntimeError(f"Missing {path}")
    patch(path)
    print(f"Patched {path}")
    print(f"Backup: {path.with_suffix(path.suffix + '.pre-v47.3-v13.2.bak')}")
    return 0


if __name__ == "__main__": raise SystemExit(main())
