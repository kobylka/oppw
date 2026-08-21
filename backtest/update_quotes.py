"""Refresh the OPPW24 QQQ research datasets and quote cache.

The updater intentionally reuses ``dukascopy/dukas_download.py`` for downloads,
``dukascopy/json_converter.py`` for minute-bar conversion, and the quote-loading
methods in ``backtest/oppw24.py`` for ``quotes.pkl`` generation.

Run from any directory with the repository's Python environment::

    python D:/oppw/backtest/update_quotes.py

Stooq occasionally puts its bulk archive behind a browser verification page. If
that happens, download ``d_us_txt.zip`` from https://stooq.com/db/h/ and run::

    python D:/oppw/backtest/update_quotes.py --stooq-zip D:/Downloads/d_us_txt.zip
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import pickle
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path, PurePosixPath
from types import ModuleType


BACKTEST_DIR = Path(__file__).resolve().parent
REPO_ROOT = BACKTEST_DIR.parent
DUKASCOPY_DIR = REPO_ROOT / "dukascopy"
DUKAS_DOWNLOADER = DUKASCOPY_DIR / "dukas_download.py"
JSON_CONVERTER = DUKASCOPY_DIR / "json_converter.py"

QQQ_CSV = BACKTEST_DIR / "qqq.csv"
QQQ_DAILY = BACKTEST_DIR / "qqq.us.txt"
QUOTES_PICKLE = BACKTEST_DIR / "quotes.pkl"

STOOQ_ARCHIVE_URL = "https://stooq.com/db/d/?b=d_us_txt"
STOOQ_MEMBER_NAME = "qqq.us.txt"
ROWS_PER_INTRADAY_DAY = 1335
DAILY_FIELDS = 10
MINUTE_FIELDS = 6
DOWNLOAD_CHUNK_SIZE = 1024 * 1024
STOOQ_RETRIES = 3


class UpdateError(RuntimeError):
    """Raised when an input cannot be safely promoted to the live dataset."""


def parse_iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"invalid ISO date {value!r}; expected YYYY-MM-DD") from error


def read_intraday_boundary(path: Path, *, first: bool) -> date:
    """Read the first or last non-empty YYYYMMDD record without loading the file."""
    if not path.is_file():
        raise FileNotFoundError(f"Intraday dataset does not exist: {path}")

    if first:
        with path.open("rb") as source:
            for raw_line in source:
                if raw_line.strip():
                    return parse_intraday_date(raw_line, path)
    else:
        with path.open("rb") as source:
            source.seek(0, os.SEEK_END)
            position = source.tell()
            buffer = bytearray()

            while position > 0:
                position -= 1
                source.seek(position)
                byte = source.read(1)
                if byte in (b"\n", b"\r"):
                    if buffer:
                        return parse_intraday_date(bytes(reversed(buffer)), path)
                    continue
                buffer.append(byte[0])

            if buffer:
                return parse_intraday_date(bytes(reversed(buffer)), path)

    raise UpdateError(f"Intraday dataset is empty: {path}")


def parse_intraday_date(raw_line: bytes, path: Path) -> date:
    try:
        first_field = raw_line.decode("utf-8").split(";", 1)[0]
        return datetime.strptime(first_field, "%Y%m%d").date()
    except (UnicodeDecodeError, ValueError) as error:
        raise UpdateError(f"Invalid intraday row in {path}: {raw_line[:100]!r}") from error


def load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise UpdateError(f"Could not load Python module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_dukas_downloader() -> ModuleType:
    try:
        return load_module(DUKAS_DOWNLOADER, "oppw_dukas_download")
    except ModuleNotFoundError as error:
        if error.name == "requests":
            raise UpdateError(
                "dukas_download.py requires the 'requests' package. "
                "Install it with: python -m pip install requests"
            ) from error
        raise


def new_http_session(downloader: ModuleType):
    session = downloader.requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/150.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
        }
    )
    return session


def download_dukas_days(
    downloader: ModuleType,
    session,
    output_dir: Path,
    start_day: date,
    through_day: date,
) -> tuple[int, int]:
    output_dir.mkdir(parents=True, exist_ok=True)
    downloader.OUTPUT_DIR = output_dir

    successful = 0
    unavailable = 0
    current_day = start_day

    while current_day <= through_day:
        if downloader.download_day(session, current_day):
            successful += 1
        else:
            unavailable += 1
        current_day += timedelta(days=1)
        if current_day <= through_day:
            time.sleep(0.25)

    return successful, unavailable


def run_json_converter(json_dir: Path) -> Path | None:
    if not any(json_dir.glob("*.json")):
        return None

    try:
        subprocess.run(
            [sys.executable, str(JSON_CONVERTER)],
            cwd=json_dir,
            check=True,
        )
    except subprocess.CalledProcessError as error:
        raise UpdateError(f"json_converter.py failed with exit code {error.returncode}") from error

    converted = json_dir / "combined_dst_adjusted.csv"
    if not converted.is_file():
        raise UpdateError(f"json_converter.py did not create {converted}")
    return converted


def inspect_converted_days(path: Path, last_existing_day: date, through_day: date) -> dict[date, int]:
    day_counts: dict[date, int] = {}
    previous_day: date | None = None

    with path.open("r", encoding="utf-8", newline="") as source:
        for line_number, line in enumerate(source, start=1):
            fields = line.rstrip("\r\n").split(";")
            if len(fields) != MINUTE_FIELDS:
                raise UpdateError(f"{path}:{line_number} has {len(fields)} fields, expected {MINUTE_FIELDS}")
            try:
                current_day = datetime.strptime(fields[0], "%Y%m%d").date()
            except ValueError as error:
                raise UpdateError(f"{path}:{line_number} has an invalid date: {fields[0]!r}") from error
            if not last_existing_day < current_day <= through_day:
                raise UpdateError(f"Converted day {current_day} is outside the requested update range")
            if previous_day is not None and current_day < previous_day:
                raise UpdateError(f"Converted rows are not date-sorted at {path}:{line_number}")
            day_counts[current_day] = day_counts.get(current_day, 0) + 1
            previous_day = current_day

    wrong_counts = {day: count for day, count in day_counts.items() if count != ROWS_PER_INTRADAY_DAY}
    if wrong_counts:
        details = ", ".join(f"{day}={count}" for day, count in sorted(wrong_counts.items()))
        raise UpdateError(f"Converted sessions do not contain {ROWS_PER_INTRADAY_DAY} rows: {details}")
    return day_counts


def expected_completed_sessions(start_day: date, through_day: date) -> set[date]:
    """Return exchange sessions that must already be complete (never require today)."""
    last_required = min(through_day, date.today() - timedelta(days=1))
    if start_day > last_required:
        return set()

    try:
        import pandas_market_calendars as mcal
    except ModuleNotFoundError as error:
        raise UpdateError(
            "json_converter.py requires the 'pandas_market_calendars' package. "
            "Install the repository's research dependencies before running this updater."
        ) from error

    schedule = mcal.get_calendar("NYSE").schedule(
        start_date=start_day.isoformat(),
        end_date=last_required.isoformat(),
    )
    return {timestamp.date() for timestamp in schedule.index}


def stage_intraday_file(source: Path, converted: Path | None, destination: Path) -> date:
    shutil.copyfile(source, destination)
    last_day = read_intraday_boundary(source, first=False)

    if converted is not None and converted.stat().st_size:
        with destination.open("ab") as target, converted.open("rb") as additions:
            if destination.stat().st_size:
                with destination.open("rb") as check:
                    check.seek(-1, os.SEEK_END)
                    if check.read(1) not in (b"\n", b"\r"):
                        target.write(b"\n")
            shutil.copyfileobj(additions, target, DOWNLOAD_CHUNK_SIZE)
        last_day = read_intraday_boundary(destination, first=False)

    return last_day


def download_stooq_archive(session, destination: Path, url: str) -> None:
    last_error: Exception | None = None

    for attempt in range(1, STOOQ_RETRIES + 1):
        try:
            with session.get(url, stream=True, timeout=(30, 300)) as response:
                response.raise_for_status()
                with destination.open("wb") as output:
                    for chunk in response.iter_content(chunk_size=DOWNLOAD_CHUNK_SIZE):
                        if chunk:
                            output.write(chunk)

            if not zipfile.is_zipfile(destination):
                preview = destination.read_bytes()[:120].decode("utf-8", errors="replace")
                raise UpdateError(
                    "Stooq returned something other than d_us_txt.zip "
                    f"({preview!r}). The site may require browser verification."
                )
            return
        except Exception as error:
            # The deliberately broad boundary includes requests' transport/status
            # exceptions without coupling this script to requests directly.
            last_error = error
            if isinstance(error, UpdateError):
                break
            if attempt < STOOQ_RETRIES:
                time.sleep(3 * attempt)

    raise UpdateError(
        f"Could not download the Stooq archive from {url}: {last_error}. "
        "Stooq may require interactive browser verification; download d_us_txt.zip from "
        "https://stooq.com/db/h/ and rerun with --stooq-zip PATH_TO_ZIP."
    ) from last_error


def extract_stooq_qqq(archive: Path, destination: Path) -> None:
    try:
        with zipfile.ZipFile(archive) as source:
            matches = [
                member
                for member in source.infolist()
                if not member.is_dir()
                and PurePosixPath(member.filename.replace("\\", "/")).name.lower() == STOOQ_MEMBER_NAME
            ]
            if len(matches) != 1:
                raise UpdateError(
                    f"Expected exactly one {STOOQ_MEMBER_NAME} in {archive}, found {len(matches)}"
                )
            with source.open(matches[0]) as input_file, destination.open("wb") as output_file:
                shutil.copyfileobj(input_file, output_file, DOWNLOAD_CHUNK_SIZE)
    except zipfile.BadZipFile as error:
        raise UpdateError(f"Invalid Stooq ZIP archive: {archive}") from error


def inspect_stooq_daily(path: Path) -> tuple[date, date, int]:
    first_day: date | None = None
    last_day: date | None = None
    row_count = 0

    with path.open("r", encoding="utf-8-sig", newline="") as source:
        header = source.readline().rstrip("\r\n")
        expected_header = "<TICKER>,<PER>,<DATE>,<TIME>,<OPEN>,<HIGH>,<LOW>,<CLOSE>,<VOL>,<OPENINT>"
        if header != expected_header:
            raise UpdateError(f"Unexpected Stooq header in {path}: {header!r}")

        for line_number, line in enumerate(source, start=2):
            fields = line.rstrip("\r\n").split(",")
            if len(fields) != DAILY_FIELDS:
                raise UpdateError(f"{path}:{line_number} has {len(fields)} fields, expected {DAILY_FIELDS}")
            if fields[0].upper() != "QQQ.US" or fields[1] != "D":
                raise UpdateError(f"Unexpected Stooq instrument at {path}:{line_number}")
            try:
                current_day = datetime.strptime(fields[2], "%Y%m%d").date()
            except ValueError as error:
                raise UpdateError(f"Invalid Stooq date at {path}:{line_number}: {fields[2]!r}") from error
            if last_day is not None and current_day <= last_day:
                raise UpdateError(f"Stooq dates are not strictly increasing at {path}:{line_number}")
            first_day = first_day or current_day
            last_day = current_day
            row_count += 1

    if first_day is None or last_day is None:
        raise UpdateError(f"Stooq QQQ file has no data rows: {path}")
    return first_day, last_day, row_count


@contextmanager
def working_directory(path: Path) -> Iterator[None]:
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def build_quotes_pickle(stage_dir: Path, first_intraday_day: date) -> Path:
    sys.path.insert(0, str(BACKTEST_DIR))
    try:
        oppw24 = load_module(BACKTEST_DIR / "oppw24.py", "oppw24_update_quotes")
    finally:
        try:
            sys.path.remove(str(BACKTEST_DIR))
        except ValueError:
            pass

    start_date = first_intraday_day.strftime("%Y%m%d")
    with working_directory(stage_dir):
        simulation = oppw24.Sim()
        simulation.read_quotes([QQQ_DAILY.name], start_date)
        simulation.read_csv_quotes([QQQ_CSV.name], start_date)

    staged_pickle = stage_dir / QUOTES_PICKLE.name
    if not staged_pickle.is_file():
        raise UpdateError(f"oppw24.py did not create {staged_pickle}")
    return staged_pickle


def inspect_quotes_pickle(path: Path, required_intraday_days: set[date]) -> tuple[int, date]:
    with path.open("rb") as source:
        quotes = pickle.load(source)
    if not isinstance(quotes, dict) or not quotes:
        raise UpdateError(f"Quote cache is not a non-empty dictionary: {path}")

    for trading_day in sorted(required_intraday_days):
        key = trading_day.strftime("%Y%m%d")
        qqq = quotes.get(key, {}).get("QQQ")
        expected_count = 4 + ROWS_PER_INTRADAY_DAY
        if not isinstance(qqq, list) or len(qqq) != expected_count:
            actual = len(qqq) if isinstance(qqq, list) else None
            raise UpdateError(f"quotes.pkl has {actual} QQQ values for {key}, expected {expected_count}")

    try:
        last_day = datetime.strptime(max(quotes), "%Y%m%d").date()
    except (TypeError, ValueError) as error:
        raise UpdateError("quotes.pkl contains an invalid date key") from error
    return len(quotes), last_day


def reset_windows_acl_to_parent(path: Path) -> None:
    """Make a promoted artifact inherit the backtest directory's Windows ACL."""
    if os.name != "nt":
        return

    result = subprocess.run(
        ["icacls", str(path), "/reset", "/Q"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        details = (result.stderr or result.stdout).strip()
        raise UpdateError(f"Could not reset inherited permissions on {path}: {details}")


def replace_artifacts(staged: dict[Path, Path]) -> None:
    backups: dict[Path, Path] = {}
    promoted: list[Path] = []
    try:
        for target, source in staged.items():
            backup = source.with_name(f"{source.name}.previous")
            if target.exists():
                os.replace(target, backup)
                backups[target] = backup
            os.replace(source, target)
            reset_windows_acl_to_parent(target)
            promoted.append(target)
    except Exception:
        for target in reversed(promoted):
            if target.exists():
                target.unlink()
            backup = backups.get(target)
            if backup is not None and backup.exists():
                os.replace(backup, target)
        for target, backup in backups.items():
            if target not in promoted and backup.exists():
                os.replace(backup, target)
        raise
    else:
        for backup in backups.values():
            backup.unlink(missing_ok=True)


def update_quotes(through_day: date, stooq_zip: Path | None, stooq_url: str) -> None:
    first_existing_day = read_intraday_boundary(QQQ_CSV, first=True)
    last_existing_day = read_intraday_boundary(QQQ_CSV, first=False)
    if through_day > date.today():
        raise UpdateError(f"requested through date {through_day} is in the future")
    if through_day < last_existing_day:
        raise UpdateError(
            f"qqq.csv already ends at {last_existing_day}, after requested through date {through_day}"
        )

    print(f"qqq.csv range: {first_existing_day} -> {last_existing_day}")
    print(f"Requested through: {through_day}")

    stage_path = Path(tempfile.mkdtemp(prefix=".update_quotes-", dir=BACKTEST_DIR))
    try:
        converted: Path | None = None
        converted_days: dict[date, int] = {}

        if last_existing_day < through_day:
            last_download_day = min(through_day, date.today() - timedelta(days=1))
            downloader = load_dukas_downloader()
            with new_http_session(downloader) as session:
                dukas_dir = stage_path / "dukascopy"
                successful, unavailable = download_dukas_days(
                    downloader,
                    session,
                    dukas_dir,
                    # Each UTC Dukascopy response supplies the opening local
                    # hours of the following day, so retain one overlap day.
                    last_existing_day,
                    last_download_day,
                )
                print(f"Dukascopy responses saved: {successful}; unavailable: {unavailable}")
                converted = run_json_converter(dukas_dir)
                if converted is not None:
                    converted_days = inspect_converted_days(converted, last_existing_day, through_day)

                required = expected_completed_sessions(last_existing_day + timedelta(days=1), through_day)
                missing = sorted(required - converted_days.keys())
                if missing:
                    formatted = ", ".join(day.isoformat() for day in missing)
                    raise UpdateError(f"Dukascopy conversion is missing completed NYSE sessions: {formatted}")

        staged_qqq = stage_path / QQQ_CSV.name
        new_last_intraday_day = stage_intraday_file(QQQ_CSV, converted, staged_qqq)
        print(f"Staged qqq.csv through {new_last_intraday_day} ({len(converted_days)} new sessions)")

        archive = stage_path / "d_us_txt.zip"
        if stooq_zip is not None:
            if not stooq_zip.is_file():
                raise FileNotFoundError(f"Stooq archive does not exist: {stooq_zip}")
            shutil.copyfile(stooq_zip, archive)
            if not zipfile.is_zipfile(archive):
                raise UpdateError(f"Not a ZIP archive: {stooq_zip}")
        else:
            downloader = load_dukas_downloader()
            with new_http_session(downloader) as session:
                print(f"Downloading Stooq daily US archive: {stooq_url}")
                download_stooq_archive(session, archive, stooq_url)

        staged_daily = stage_path / QQQ_DAILY.name
        extract_stooq_qqq(archive, staged_daily)
        stooq_first, stooq_last, stooq_rows = inspect_stooq_daily(staged_daily)
        print(f"Staged {QQQ_DAILY.name}: {stooq_first} -> {stooq_last} ({stooq_rows:,} rows)")
        if stooq_last < new_last_intraday_day:
            raise UpdateError(
                f"Stooq QQQ ends at {stooq_last}, before intraday data at {new_last_intraday_day}; "
                "rerun when the Stooq archive catches up"
            )

        staged_pickle = build_quotes_pickle(stage_path, first_existing_day)
        required_pickle_days = set(converted_days)
        required_pickle_days.add(new_last_intraday_day)
        quote_days, quote_last = inspect_quotes_pickle(staged_pickle, required_pickle_days)
        print(f"Staged quotes.pkl: {quote_days:,} dates through {quote_last}")

        replace_artifacts(
            {
                QQQ_CSV: staged_qqq,
                QQQ_DAILY: staged_daily,
                QUOTES_PICKLE: staged_pickle,
            }
        )
        print("Update complete:")
        print(f"  {QQQ_CSV}")
        print(f"  {QQQ_DAILY}")
        print(f"  {QUOTES_PICKLE}")
    finally:
        shutil.rmtree(stage_path, ignore_errors=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--through",
        type=parse_iso_date,
        default=date.today(),
        help="last calendar day to request from Dukascopy (YYYY-MM-DD; default: today)",
    )
    parser.add_argument(
        "--stooq-zip",
        type=Path,
        help="use an already downloaded d_us_txt.zip instead of downloading it",
    )
    parser.add_argument(
        "--stooq-url",
        default=STOOQ_ARCHIVE_URL,
        help="Stooq bulk archive URL (default: %(default)s)",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        update_quotes(
            through_day=args.through,
            stooq_zip=args.stooq_zip.resolve() if args.stooq_zip else None,
            stooq_url=args.stooq_url,
        )
    except (OSError, UpdateError, pickle.PickleError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
