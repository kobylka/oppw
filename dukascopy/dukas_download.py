from __future__ import annotations

import json
import time
from datetime import date, timedelta
from pathlib import Path

import requests


YEAR = 2012
INSTRUMENT = "USATECH.IDX-USD"
OFFER_SIDE = "BID"

OUTPUT_DIR = Path(f"dukascopy_{INSTRUMENT}_{OFFER_SIDE}_{YEAR}")

REQUEST_TIMEOUT = 30
MAX_RETRIES = 5
RETRY_DELAY_SECONDS = 3

BASE_URL = "https://jetta.dukascopy.com/v1/candles/minute"


def download_day(
    session: requests.Session,
    current_date: date,
) -> bool:
    url = (
        f"{BASE_URL}/{INSTRUMENT}/{OFFER_SIDE}/"
        f"{current_date.year}/{current_date.month}/{current_date.day}"
    )

    output_file = OUTPUT_DIR / f"{current_date.isoformat()}.json"

    # Do not download files that already exist.
    if output_file.exists() and output_file.stat().st_size > 0:
        print(f"Already exists: {output_file.name}")
        return True

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = session.get(url, timeout=REQUEST_TIMEOUT)

            if response.status_code == 404:
                print(f"No data: {current_date} [404]")
                return False

            response.raise_for_status()

            # Validate that the response really contains JSON.
            data = response.json()

            # Save formatted JSON.
            with output_file.open("w", encoding="utf-8") as file:
                json.dump(
                    data,
                    file,
                    ensure_ascii=False,
                    indent=2,
                )

            print(
                f"Saved: {output_file.name} "
                f"({output_file.stat().st_size:,} bytes)"
            )
            return True

        except (
            requests.Timeout,
            requests.ConnectionError,
            requests.HTTPError,
            requests.JSONDecodeError,
        ) as error:
            print(
                f"Error downloading {current_date}, "
                f"attempt {attempt}/{MAX_RETRIES}: {error}"
            )

            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY_SECONDS * attempt)

    print(f"Failed permanently: {current_date}")
    return False


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    start_date = date(YEAR, 1, 1)
    end_date = date(2018, 4, 12)

    successful = 0
    failed = 0

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 Chrome/150.0 Safari/537.36"
        ),
        "Accept": "application/json",
    }

    with requests.Session() as session:
        session.headers.update(headers)

        current_date = start_date

        while current_date < end_date:
            if download_day(session, current_date):
                successful += 1
            else:
                failed += 1

            current_date += timedelta(days=1)

            # Small delay to avoid sending requests too rapidly.
            time.sleep(0.25)

    print()
    print("Finished.")
    print(f"Successful: {successful}")
    print(f"Failed or unavailable: {failed}")
    print(f"Output directory: {OUTPUT_DIR.resolve()}")


if __name__ == "__main__":
    main()