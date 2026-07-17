from __future__ import annotations

import csv
import json
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pandas_market_calendars as mcal


INPUT_DIRECTORY = Path.cwd()
OUTPUT_FILE = INPUT_DIRECTORY / "combined_dst_adjusted.csv"

try:
    NEW_YORK = ZoneInfo("America/New_York")
except ZoneInfoNotFoundError as error:
    raise RuntimeError("Time-zone database is unavailable. Install it with: pip install tzdata") from error

UTC_PLUS_ONE = timezone(timedelta(hours=1))
UTC_PLUS_TWO = timezone(timedelta(hours=2))

EXPECTED_ROWS_PER_DAY = 1335
MAX_MISSING_TO_FILL = 50
NORMAL_NYSE_SESSION = timedelta(hours=6, minutes=30)

Candle = tuple[Decimal, Decimal, Decimal, Decimal]


def format_price(value: Decimal) -> str:
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def convert_utc_to_session_time(utc_timestamp: datetime) -> datetime:
    utc_timestamp = utc_timestamp.replace(tzinfo=timezone.utc) if utc_timestamp.tzinfo is None else utc_timestamp.astimezone(timezone.utc)
    new_york_timestamp = utc_timestamp.astimezone(NEW_YORK)
    is_us_dst = new_york_timestamp.dst() is not None and new_york_timestamp.dst() != timedelta(0)
    return utc_timestamp.astimezone(UTC_PLUS_TWO if is_us_dst else UTC_PLUS_ONE)


def load_json_file(json_file: Path) -> dict:
    with json_file.open("r", encoding="utf-8-sig") as source:
        data = json.load(source)

    required_fields = {"timestamp", "multiplier", "shift", "open", "high", "low", "close", "times", "opens", "highs", "lows", "closes"}
    missing_fields = required_fields - data.keys()

    if missing_fields:
        raise ValueError(f"Missing fields: {sorted(missing_fields)}")

    array_names = ["times", "opens", "highs", "lows", "closes"]
    lengths = {name: len(data[name]) for name in array_names}

    if len(set(lengths.values())) != 1:
        raise ValueError(f"Arrays have different lengths: {lengths}")

    return data


def decode_json_file(json_file: Path, data: dict) -> list[tuple[datetime, Candle]]:
    multiplier = Decimal(str(data["multiplier"]))
    shift_ms = int(data["shift"])
    timestamp_ms = int(data["timestamp"])

    current_open = Decimal(str(data["open"]))
    current_high = Decimal(str(data["high"]))
    current_low = Decimal(str(data["low"]))
    current_close = Decimal(str(data["close"]))

    decoded_rows: list[tuple[datetime, Candle]] = []

    for index in range(len(data["times"])):
        timestamp_ms += int(data["times"][index]) * shift_ms
        current_open += Decimal(str(data["opens"][index])) * multiplier
        current_high += Decimal(str(data["highs"][index])) * multiplier
        current_low += Decimal(str(data["lows"][index])) * multiplier
        current_close += Decimal(str(data["closes"][index])) * multiplier

        utc_timestamp = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
        session_timestamp = convert_utc_to_session_time(utc_timestamp)
        candle: Candle = (current_open, current_high, current_low, current_close)

        decoded_rows.append((session_timestamp, candle))

    if decoded_rows:
        first_timestamp = decoded_rows[0][0]
        last_timestamp = decoded_rows[-1][0]
        print(f"Decoded {json_file.name}: {len(decoded_rows):,} rows, {first_timestamp.isoformat()} -> {last_timestamp.isoformat()}")
    else:
        print(f"Decoded {json_file.name}: 0 rows")

    return decoded_rows


def create_expected_timestamps(trading_day: date) -> list[datetime]:
    noon_utc = datetime.combine(trading_day, time(12, 0), tzinfo=timezone.utc)
    session_timezone = convert_utc_to_session_time(noon_utc).tzinfo

    if session_timezone is None:
        raise RuntimeError(f"Could not determine timezone for {trading_day}")

    session_start = datetime.combine(trading_day, time(0, 0), tzinfo=session_timezone)
    return [session_start + timedelta(minutes=minute) for minute in range(EXPECTED_ROWS_PER_DAY)]


def format_times(timestamps: list[datetime], limit: int = 5) -> str:
    displayed = ", ".join(timestamp.strftime("%H:%M") for timestamp in timestamps[:limit])
    return displayed + ", ..." if len(timestamps) > limit else displayed


def create_market_calendar(first_day: date, last_day: date) -> tuple[set[date], set[date]]:
    nyse = mcal.get_calendar("NYSE")
    schedule = nyse.schedule(start_date=first_day.isoformat(), end_date=last_day.isoformat())

    normal_trading_days: set[date] = set()
    shortened_trading_days: set[date] = set()

    for session_label, row in schedule.iterrows():
        trading_day = session_label.date()
        session_duration = (row["market_close"] - row["market_open"]).to_pytimedelta()

        if session_duration < NORMAL_NYSE_SESSION:
            shortened_trading_days.add(trading_day)
        else:
            normal_trading_days.add(trading_day)

    return normal_trading_days, shortened_trading_days


def group_consecutive_timestamps(timestamps: list[datetime]) -> list[list[datetime]]:
    if not timestamps:
        return []

    ordered = sorted(timestamps)
    groups: list[list[datetime]] = [[ordered[0]]]

    for timestamp in ordered[1:]:
        if timestamp - groups[-1][-1] == timedelta(minutes=1):
            groups[-1].append(timestamp)
        else:
            groups.append([timestamp])

    return groups


def fill_small_midday_gaps(session_candles: dict[datetime, Candle], expected_timestamps: list[datetime]) -> tuple[dict[datetime, Candle], list[datetime]]:
    missing = [timestamp for timestamp in expected_timestamps if timestamp not in session_candles]

    if not missing or len(missing) > MAX_MISSING_TO_FILL or not session_candles:
        return dict(session_candles), []

    expected_set = set(expected_timestamps)
    first_five_minutes = set(expected_timestamps[:5])
    final_session_timestamp = expected_timestamps[-1]

    repaired = dict(session_candles)
    filled_timestamps: list[datetime] = []

    for gap in group_consecutive_timestamps(missing):
        gap_start = gap[0]
        gap_end = gap[-1]
        previous_timestamp = gap_start - timedelta(minutes=1)
        next_timestamp = gap_end + timedelta(minutes=1)

        gap_is_in_first_five_minutes = all(timestamp in first_five_minutes for timestamp in gap)
        gap_is_at_end = gap_end == final_session_timestamp

        if gap_is_in_first_five_minutes:
            if next_timestamp not in session_candles:
                return dict(session_candles), []
            source_candle = session_candles[next_timestamp]

        elif gap_is_at_end:
            if previous_timestamp not in repaired:
                return dict(session_candles), []
            source_candle = repaired[previous_timestamp]

        else:
            if previous_timestamp not in expected_set or next_timestamp not in expected_set:
                return dict(session_candles), []

            if previous_timestamp not in repaired or next_timestamp not in session_candles:
                return dict(session_candles), []

            source_candle = repaired[previous_timestamp]

        for missing_timestamp in gap:
            repaired[missing_timestamp] = tuple(source_candle)
            filled_timestamps.append(missing_timestamp)

    return repaired, filled_timestamps


def fill_early_close_tail(session_candles: dict[datetime, Candle], expected_timestamps: list[datetime]) -> tuple[dict[datetime, Candle], list[datetime]]:
    existing_timestamps = [timestamp for timestamp in expected_timestamps if timestamp in session_candles]

    if not existing_timestamps:
        return dict(session_candles), []

    last_existing_timestamp = existing_timestamps[-1]
    last_existing_candle = session_candles[last_existing_timestamp]

    repaired = dict(session_candles)
    filled_timestamps: list[datetime] = []

    for timestamp in expected_timestamps:
        if timestamp <= last_existing_timestamp or timestamp in repaired:
            continue

        repaired[timestamp] = tuple(last_existing_candle)
        filled_timestamps.append(timestamp)

    return repaired, filled_timestamps


def main() -> None:
    json_files = list(INPUT_DIRECTORY.glob("*.json"))

    if not json_files:
        raise FileNotFoundError(f"No JSON files found in: {INPUT_DIRECTORY}")

    loaded_files: list[tuple[Path, dict]] = []

    for json_file in json_files:
        try:
            loaded_files.append((json_file, load_json_file(json_file)))
        except (json.JSONDecodeError, ValueError, TypeError, KeyError) as error:
            print(f"Skipping file {json_file.name}: {error}")

    if not loaded_files:
        raise RuntimeError("No valid JSON files were found.")

    loaded_files.sort(key=lambda item: int(item[1]["timestamp"]))

    all_candles: dict[datetime, Candle] = {}
    processed_files = 0

    for json_file, data in loaded_files:
        try:
            for timestamp, candle in decode_json_file(json_file, data):
                existing_candle = all_candles.get(timestamp)

                if existing_candle is None:
                    all_candles[timestamp] = candle
                elif existing_candle != candle:
                    raise ValueError(f"Conflicting duplicate candle at {timestamp.isoformat()}")

            processed_files += 1

        except (ValueError, TypeError, KeyError) as error:
            print(f"Skipping decoded data from {json_file.name}: {error}")

    if not all_candles:
        raise RuntimeError("No candles were decoded.")

    first_day = min(all_candles).date()
    last_day = max(all_candles).date()

    normal_trading_days, shortened_trading_days = create_market_calendar(first_day, last_day)

    candles_by_day: dict[date, dict[datetime, Candle]] = {}

    for timestamp, candle in all_candles.items():
        candles_by_day.setdefault(timestamp.date(), {})[timestamp] = candle

    complete_days: list[tuple[date, list[tuple[datetime, Candle]]]] = []

    skipped_weekends = 0
    skipped_holidays = 0
    skipped_incomplete_days = 0
    filled_days = 0
    filled_candles_total = 0
    filled_shortened_days = 0
    filled_shortened_candles = 0
    outside_candles_ignored = 0

    current_day = first_day

    while current_day <= last_day:
        raw_day_candles = candles_by_day.get(current_day, {})
        available_raw = len(raw_day_candles)

        if current_day.weekday() >= 5:
            #print(f"Skipping {current_day}: weekend, available={available_raw:,}")
            skipped_weekends += 1
            current_day += timedelta(days=1)
            continue

        is_early_close = current_day in shortened_trading_days
        is_normal_session = current_day in normal_trading_days

        if not is_normal_session and not is_early_close:
            #print(f"Skipping {current_day}: market holiday, available={available_raw:,}")
            skipped_holidays += 1
            current_day += timedelta(days=1)
            continue

        expected_timestamps = create_expected_timestamps(current_day)
        expected_set = set(expected_timestamps)

        outside_session = sorted(timestamp for timestamp in raw_day_candles if timestamp not in expected_set)
        session_candles = {timestamp: candle for timestamp, candle in raw_day_candles.items() if timestamp in expected_set}

        if outside_session:
            outside_candles_ignored += len(outside_session)
            print(f"Ignoring {current_day}: {len(outside_session):,} outside-session candles")
            print(f"  First outside-session times: {format_times(outside_session)}")

        early_close_filled: list[datetime] = []

        if is_early_close:
            session_candles, early_close_filled = fill_early_close_tail(session_candles, expected_timestamps)

            if early_close_filled:
                filled_shortened_days += 1
                filled_shortened_candles += len(early_close_filled)
                #print(f"Extended early-close day {current_day}: filled={len(early_close_filled):,} candles through 22:14")
                #print(f"  First filled times: {format_times(early_close_filled)}")

        missing_before_fill = [timestamp for timestamp in expected_timestamps if timestamp not in session_candles]
        filled_timestamps: list[datetime] = []

        if missing_before_fill:
            session_candles, filled_timestamps = fill_small_midday_gaps(session_candles, expected_timestamps)

        missing_after_fill = [timestamp for timestamp in expected_timestamps if timestamp not in session_candles]

        if filled_timestamps:
            filled_days += 1
            filled_candles_total += len(filled_timestamps)
            #print(f"Filled {current_day}: {len(filled_timestamps):,} missing candles")
            #print(f"  Filled times: {format_times(filled_timestamps)}")

        if missing_after_fill:
            available_count = EXPECTED_ROWS_PER_DAY - len(missing_after_fill)
            print(f"Skipping {current_day}: available={available_count:,}, missing={len(missing_after_fill):,}, outside session={len(outside_session):,}")
            print(f"  First missing times: {format_times(missing_after_fill)}")
            skipped_incomplete_days += 1
            current_day += timedelta(days=1)
            continue

        rows = [(timestamp, session_candles[timestamp]) for timestamp in expected_timestamps]

        if len(rows) != EXPECTED_ROWS_PER_DAY:
            raise RuntimeError(f"{current_day} has {len(rows):,} rows instead of {EXPECTED_ROWS_PER_DAY:,}")

        first_time = rows[0][0].strftime("%H:%M")
        last_time = rows[-1][0].strftime("%H:%M")

        if first_time != "00:00":
            raise RuntimeError(f"{current_day} starts at {first_time}, expected 00:00")

        if last_time != "22:14":
            raise RuntimeError(f"{current_day} ends at {last_time}, expected 22:14")

        complete_days.append((current_day, rows))

        offset_raw = rows[0][0].strftime("%z")
        offset_text = f"{offset_raw[:3]}:{offset_raw[3:]}"
        fill_description = ""

        if filled_timestamps:
            fill_description += f", filled={len(filled_timestamps)}"

        if early_close_filled:
            fill_description += f", early-close-filled={len(early_close_filled)}"

        #print(f"Complete {current_day}: {len(rows):,} rows, {first_time}–{last_time}, offset={offset_text}{fill_description}")

        current_day += timedelta(days=1)

    if not complete_days:
        raise RuntimeError("No complete trading days were found.")

    total_rows_written = 0

    with OUTPUT_FILE.open("w", encoding="utf-8", newline="") as destination:
        writer = csv.writer(destination, delimiter=";", lineterminator="\n")

        for trading_day, rows in complete_days:
            if len(rows) != EXPECTED_ROWS_PER_DAY:
                raise RuntimeError(f"Refusing to write {trading_day}: incorrect row count")

            for timestamp, candle in rows:
                open_price, high_price, low_price, close_price = candle

                writer.writerow([
                    timestamp.strftime("%Y%m%d"),
                    timestamp.strftime("%H:%M"),
                    format_price(open_price),
                    format_price(high_price),
                    format_price(low_price),
                    format_price(close_price),
                ])

                total_rows_written += 1

    expected_total_rows = len(complete_days) * EXPECTED_ROWS_PER_DAY

    if total_rows_written != expected_total_rows:
        raise RuntimeError(f"Output validation failed: written={total_rows_written:,}, expected={expected_total_rows:,}")

    print()
    print("Finished")
    print(f"Processed JSON files: {processed_files:,}")
    print(f"Complete days written: {len(complete_days):,}")
    print(f"Days repaired: {filled_days:,}")
    print(f"Normal missing candles filled: {filled_candles_total:,}")
    print(f"Early-close days extended: {filled_shortened_days:,}")
    print(f"Early-close candles generated: {filled_shortened_candles:,}")
    print(f"Outside-session candles ignored: {outside_candles_ignored:,}")
    print(f"Weekends skipped: {skipped_weekends:,}")
    print(f"Market holidays skipped: {skipped_holidays:,}")
    print(f"Incomplete trading days skipped: {skipped_incomplete_days:,}")
    print(f"Rows per written day: {EXPECTED_ROWS_PER_DAY:,}")
    print(f"Total rows written: {total_rows_written:,}")
    print(f"Output: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()