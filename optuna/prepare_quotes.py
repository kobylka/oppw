from __future__ import annotations

import pickle
from pathlib import Path

from config import QUOTES_CACHE, RAW_DATA_DIR
from strategy import Sim


def main() -> None:
    files = [
        str(path)
        for path in RAW_DATA_DIR.iterdir()
        if path.is_file()
    ]
    
    print(files)

    if not files:
        raise RuntimeError(
            f"No quote files found in {RAW_DATA_DIR}"
        )

    sim = Sim()

    # Adjust these calls if you only use one file format.
    sim.read_quotes(files, "20000104")
    #sim.read_csv_quotes(files, "20100101")

    if not sim.quotes:
        raise RuntimeError("No quotes were loaded")

    missing_qqq = [
        date
        for date, stocks in sim.quotes.items()
        if "QQQ" not in stocks
    ]

    print("Dates loaded:", len(sim.quotes))
    print("First date:", min(sim.quotes))
    print("Last date:", max(sim.quotes))
    print("Dates missing QQQ:", len(missing_qqq))

    with QUOTES_CACHE.open("wb") as file:
        pickle.dump(
            sim.quotes,
            file,
            protocol=pickle.HIGHEST_PROTOCOL,
        )

    print("Saved:", QUOTES_CACHE)


if __name__ == "__main__":
    main()