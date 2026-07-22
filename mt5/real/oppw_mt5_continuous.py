"""Compatibility launcher for the canonical MT5 strategy source."""

from pathlib import Path
import runpy


CANONICAL_SOURCE = Path(__file__).resolve().parents[1] / "oppw_mt5_continuous.py"
if not CANONICAL_SOURCE.is_file():
    raise SystemExit(f"Canonical strategy source is missing: {CANONICAL_SOURCE}")

runpy.run_path(str(CANONICAL_SOURCE), run_name="__main__")
