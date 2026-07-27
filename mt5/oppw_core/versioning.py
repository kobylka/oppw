"""Canonical product identity and runtime role constants."""

from __future__ import annotations

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]


def read_project_version() -> str:
    for candidate in (BASE_DIR.parent / "VERSION", BASE_DIR / "VERSION"):
        if candidate.is_file():
            value = candidate.read_text(encoding="utf-8").strip()
            if value:
                return value
    raise RuntimeError("VERSION file is missing; run only from a complete OPPW source or release tree")


PROJECT_VERSION = read_project_version()
BUILD_ID = f"oppw-{PROJECT_VERSION}"
INSTANCE_MODE_EXECUTOR = "EXECUTOR"
INSTANCE_MODE_PUBLISHER = "PUBLISHER"
ACCOUNT_DEMO = "DEMO"
ACCOUNT_REAL = "REAL"
ACCOUNT_CONFIG_FILES = {ACCOUNT_DEMO: "demo_mt5_config.py", ACCOUNT_REAL: "real_mt5_config.py"}
