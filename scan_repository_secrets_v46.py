#!/usr/bin/env python3
"""Report likely committed OPPW secrets without printing their values."""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

SENSITIVE_NAMES = re.compile(
    r"^(?:MT5_PASSWORD|MT5_LOGIN|MONITOR_WRITE_TOKEN|OPPW_MONITOR_WRITE_TOKEN|"
    r"ACCESS_TOKEN|REFRESH_TOKEN|API_KEY|SECRET|PASSWORD|TOKEN)$",
    re.IGNORECASE,
)
ASSIGNMENT = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+?)\s*$")
PLACEHOLDERS = {"", "none", "null", "changeme", "change-me", "example", "your_password", "your-token", "0"}
RUNTIME = re.compile(r"(?:^|/)(?:log/|__pycache__/)|\.(?:lock|pid|log|jsonl)(?:\.|$)|(?:state|heartbeat|presence|history).*\.json$", re.IGNORECASE)
CONFIG = re.compile(r"(?:^|/)(?:oppw[-_]mt5[-_]config|real[-_]mt5[-_]config)\.py$", re.IGNORECASE)


def tracked_files(root: Path) -> list[str]:
    completed = subprocess.run(["git", "ls-files"], cwd=root, check=True, capture_output=True, text=True)
    return [line.strip().replace("\\", "/") for line in completed.stdout.splitlines() if line.strip()]


def normalize_value(raw: str) -> str:
    value = raw.split("#", 1)[0].strip().strip("'\"").strip()
    return value.lower()


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    if not (root / ".git").exists():
        print(f"Not a Git repository: {root}", file=sys.stderr)
        return 1
    findings: list[tuple[str, str]] = []
    runtime_files: list[str] = []
    for relative in tracked_files(root):
        if RUNTIME.search(relative): runtime_files.append(relative)
        if not CONFIG.search(relative): continue
        path = root / relative
        if not path.is_file(): continue
        try: lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError: continue
        for line in lines:
            match = ASSIGNMENT.match(line)
            if not match or not SENSITIVE_NAMES.match(match.group(1)): continue
            normalized = normalize_value(match.group(2))
            if normalized not in PLACEHOLDERS and not normalized.startswith("os.getenv("):
                findings.append((relative, match.group(1)))
    if findings:
        print("Potential committed secrets (values intentionally suppressed):")
        for path, field in sorted(set(findings)): print(f"  {path}: {field}")
    else:
        print("No obvious non-placeholder secret assignments were found in tracked MT5 config files.")
    if runtime_files:
        print("Tracked runtime artifacts:")
        for path in sorted(set(runtime_files)): print(f"  {path}")
    else:
        print("No tracked runtime artifacts matched the v46 rules.")
    return 2 if findings or runtime_files else 0


if __name__ == "__main__":
    raise SystemExit(main())
