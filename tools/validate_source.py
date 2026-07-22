"""Fail-fast repository invariants for the canonical OPPW release tree."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path


SEMVER = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
VERSIONED_LOOP = re.compile(r"oppw_mt5_continuous_v.+\.py$", re.IGNORECASE)
SECRET_MARKERS = (
    "-----BEGIN " + "PRIVATE KEY-----",
    '"type": "' + 'service_account"',
    "firebase-" + "adminsdk",
)


def fail(errors: list[str], message: str) -> None:
    errors.append(message)


def tracked_files(root: Path) -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z"], cwd=root, check=True, capture_output=True
    )
    return [root / value.decode("utf-8") for value in result.stdout.split(b"\0") if value]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.root.resolve()
    errors: list[str] = []
    tracked = tracked_files(root)

    required_governance = {
        "AGENTS.md": ("Context reset protocol", "Canonical source rules", "Required completion gate"),
        "docs/CURRENT_ARCHITECTURE.md": ("Canonical source map", "Data authority", "Runtime topology"),
        "docs/CONTRACT_POLICY.md": ("Atomic contract change rule", "Compatibility rules", "Required tests"),
        "docs/CHANGE_CHECKLIST.md": ("Before editing", "Implementation", "Validation"),
        "docs/decisions/0001-canonical-source-and-release-pipeline.md": ("Status: Accepted",),
        "docs/decisions/0002-immutable-mysql-authority.md": ("Status: Accepted",),
        "docs/decisions/0003-atomic-cross-component-contracts.md": ("Status: Accepted",),
        "docs/decisions/0004-executable-cross-component-contracts.md": ("Status: Accepted",),
        "docs/decisions/0005-single-mt5-entrypoint.md": ("Status: Accepted", "Supersedes"),
        ".github/pull_request_template.md": ("Contract impact", "Architecture and safety", "Validation"),
    }
    for relative, markers in required_governance.items():
        path = root / relative
        if not path.is_file():
            fail(errors, f"required project-governance file is missing: {relative}")
            continue
        content = path.read_text(encoding="utf-8")
        for marker in markers:
            if marker not in content:
                fail(errors, f"project-governance marker missing from {relative}: {marker}")

    agent_files = sorted(
        path.relative_to(root).as_posix()
        for path in tracked
        if path.name.lower() == "agents.md"
    )
    if agent_files != ["AGENTS.md"]:
        fail(errors, "exactly one root AGENTS.md must govern the repository; found: " + ", ".join(agent_files))

    version_file = root / "VERSION"
    version = version_file.read_text(encoding="utf-8").strip() if version_file.is_file() else ""
    if not SEMVER.fullmatch(version):
        fail(errors, "VERSION must exist and contain MAJOR.MINOR.PATCH")

    canonical = root / "mt5" / "oppw_mt5_continuous.py"
    if not canonical.is_file():
        fail(errors, "canonical MT5 source is missing: mt5/oppw_mt5_continuous.py")
        canonical_text = ""
    else:
        canonical_text = canonical.read_text(encoding="utf-8")
        for required in ("PROJECT_VERSION = read_project_version()", 'BUILD_ID = f"oppw-{PROJECT_VERSION}"'):
            if required not in canonical_text:
                fail(errors, f"canonical MT5 source does not derive identity from VERSION: {required}")

    versioned_sources = [
        path.relative_to(root).as_posix()
        for path in (root / "mt5").rglob("*.py")
        if VERSIONED_LOOP.fullmatch(path.name)
    ]
    if versioned_sources:
        fail(errors, "versioned MT5 source copies found: " + ", ".join(versioned_sources))

    loop_entrypoints = sorted(
        path.relative_to(root).as_posix()
        for path in (root / "mt5").rglob("oppw_mt5_continuous.py")
    )
    if loop_entrypoints != ["mt5/oppw_mt5_continuous.py"]:
        fail(errors, "exactly one MT5 entrypoint is allowed; found: " + ", ".join(loop_entrypoints))

    required_config_names = (
        'ACCOUNT_CONFIG_FILES = {ACCOUNT_DEMO: "demo_mt5_config.py", ACCOUNT_REAL: "real_mt5_config.py"}',
        'account_dir / ACCOUNT_CONFIG_FILES[account]',
    )
    for marker in required_config_names:
        if marker not in canonical_text:
            fail(errors, f"canonical MT5 account-config mapping is missing: {marker}")
    if "ACCOUNT_CONFIG_FALLBACKS" in canonical_text:
        fail(errors, "legacy MT5 account-config aliases are not allowed")

    config_examples = sorted((root / "mt5").rglob("*config*.example.py"))
    expected_config = root / "mt5" / "oppw_mt5_config.example.py"
    if config_examples != [expected_config]:
        names = ", ".join(path.relative_to(root).as_posix() for path in config_examples)
        fail(errors, "exactly one canonical MT5 config example is allowed; found: " + names)

    for test in (root / "mt5" / "tests").glob("test_*.py"):
        text = test.read_text(encoding="utf-8")
        if re.search(r"oppw_mt5_continuous_v[^\"']+\.py", text):
            fail(errors, f"test references a historical source copy: {test.relative_to(root)}")

    android_build = root / "Mobile" / "app" / "build.gradle.kts"
    android_text = android_build.read_text(encoding="utf-8") if android_build.is_file() else ""
    if 'resolve("VERSION")' not in android_text or "versionName = projectVersion" not in android_text:
        fail(errors, "Android versionName/versionCode must be derived from root VERSION")
    if re.search(r"versionName\s*=\s*\"", android_text):
        fail(errors, "Android contains a hard-coded versionName")

    contract_files = {
        "contracts/README.md": ("Executable cross-component contracts",),
        "contracts/expectations.json": ('"decisionToSendMs"', '"backendPublicationMs"', '"authorityStages"'),
        "contracts/fixtures/open-position.json": ('"strategyDocument"', '"PUBLISHED"'),
        "tools/validate_contracts.py": (
            "coordination.php", "ingest.php", "status.php", "analytics.php",
            "mobile-receipt.php", "ContractResponseParserTest",
        ),
        "Mobile/app/src/test/java/com/oppw/monitor/data/ContractResponseParserTest.kt": (
            "parseAccounts", "parseResponse", "parseAnalytics",
        ),
    }
    for relative, markers in contract_files.items():
        path = root / relative
        if not path.is_file():
            fail(errors, f"required executable-contract file is missing: {relative}")
            continue
        content = path.read_text(encoding="utf-8")
        for marker in markers:
            if marker not in content:
                fail(errors, f"executable-contract marker missing from {relative}: {marker}")
    if 'testImplementation("org.json:json:' not in android_text:
        fail(errors, "Android JVM contract test requires a real org.json implementation")

    release_script = root / "tools" / "release.ps1"
    release_text = release_script.read_text(encoding="utf-8") if release_script.is_file() else ""
    release_gates = (
        "validate_source.py",
        "-m unittest discover",
        "Get-Command php",
        "validate_mysql.ps1",
        "validate_contracts.py",
        "testDebugUnitTest assembleDebug",
        "git diff --cached --quiet",
    )
    for gate in release_gates:
        if gate not in release_text:
            fail(errors, f"release pipeline is missing required gate: {gate}")

    mysql_validator = root / "tools" / "validate_mysql.ps1"
    mysql_text = mysql_validator.read_text(encoding="utf-8") if mysql_validator.is_file() else ""
    if "MYSQL_ALLOW_EMPTY_PASSWORD=yes" not in mysql_text:
        fail(errors, "MySQL validator must use an isolated passwordless disposable container")
    if re.search(r"mysql(?:admin)?[^\n]*\s-p(?:ass|\$|\"|'|\s)", mysql_text, re.IGNORECASE):
        fail(errors, "MySQL validator must not pass passwords on a command line")

    forbidden_worktree = []
    source_roots = (root / "mt5", root / "Mobile", root / "tools", root / "docs")
    for source_root in source_roots:
        for path in source_root.rglob("*"):
            if not path.is_file() or any(
                part in {"dist", "build", ".gradle", ".idea"} for part in path.parts
            ):
                continue
            if path.suffix.lower() in {".bak", ".diff"}:
                forbidden_worktree.append(path.relative_to(root).as_posix())
    if forbidden_worktree:
        fail(errors, "backup/diff artifacts found in source tree: " + ", ".join(forbidden_worktree))

    forbidden_tracked: list[str] = []
    for path in tracked:
        relative = path.relative_to(root).as_posix()
        lowered = relative.lower()
        if (
            lowered.startswith("dist/")
            or lowered.startswith(".idea/")
            or lowered.endswith((".zip", ".zip.sha256", ".apk", ".bak", ".diff", ".lock"))
            or "__pycache__/" in lowered
            or re.search(r"mt5/.*/oppw_monitor_equity.*\.json$", lowered)
        ):
            forbidden_tracked.append(relative)
    if forbidden_tracked:
        fail(errors, "generated/runtime files are tracked: " + ", ".join(forbidden_tracked))

    backend = root / "Mobile" / "backend"
    forbidden_endpoint_names = {
        "latest-trade.php", "last-trade-authority.php", "oppw_latest_trade_v45_2.php"
    }
    endpoint_conflicts = [path.name for path in backend.glob("*.php") if path.name in forbidden_endpoint_names]
    if endpoint_conflicts:
        fail(errors, "duplicate/legacy backend endpoints found: " + ", ".join(endpoint_conflicts))

    backend_php = [path for path in backend.rglob("*.php") if path.is_file()]
    deprecated_curl_cleanup = [
        path.relative_to(root).as_posix()
        for path in backend_php
        if "curl_close(" in path.read_text(encoding="utf-8")
    ]
    if deprecated_curl_cleanup:
        fail(
            errors,
            "PHP 8.5-deprecated curl_close calls found: " + ", ".join(deprecated_curl_cleanup),
        )
    lib_text = (backend / "lib.php").read_text(encoding="utf-8")
    for marker in ("ini_set('display_errors', '0')", "ini_set('log_errors', '1')"):
        if marker not in lib_text:
            fail(errors, f"backend JSON error-output protection missing from lib.php: {marker}")

    for path in tracked:
        if not path.is_file() or path.stat().st_size > 2_000_000:
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if any(marker in content for marker in SECRET_MARKERS):
            fail(errors, f"private-key/service-account marker found in tracked file: {path.relative_to(root)}")

    if errors:
        print("SOURCE VALIDATION FAILED", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print(f"SOURCE VALIDATION PASSED version={version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
