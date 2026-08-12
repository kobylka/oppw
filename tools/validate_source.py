"""Fail-fast repository invariants for the canonical OPPW release tree."""

from __future__ import annotations

import argparse
import hashlib
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
        "docs/decisions/0006-two-node-windows-supervision.md": ("Status: Accepted", "OPPWContinuousSupervisor"),
        "docs/decisions/0007-independent-android-version.md": ("Status: Accepted", "Mobile/VERSION", "1,000,000"),
        "docs/decisions/0008-interactive-mt5-service-session.md": ("Status: Accepted", "CreateProcessAsUser", "winsta0\\default"),
        "docs/decisions/0009-mt5-readiness-gated-startup.md": ("Status: Accepted", "Demo Executor", "readiness"),
        "docs/decisions/0010-cohesive-mt5-runtime-modules.md": ("Status: Accepted", "behavior-preserving", "oppw_core"),
        "docs/decisions/0011-single-source-mt5-configuration.md": ("Status: Accepted", "override-only", "exact equality"),
        "docs/decisions/0012-bounded-current-snapshot-projection.md": ("Status: Accepted", "one row per", "upserts"),
        "docs/decisions/0013-disposable-recovery-and-data-retention.md": (
            "Status: Accepted", "strategy_market_points", "online indefinitely", "backup-and-restore",
            "D:\\OPPW-Backups\\mysql", "02:15",
        ),
        "docs/DATA_LIFECYCLE.md": (
            "Market minute OHLC", "Indefinite", "retention.php", "validate_backup_restore.ps1",
            "OPPW MySQL Production Backup", "D:\\OPPW-Backups\\mysql", "02:15",
        ),
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

    mobile_version_file = root / "Mobile" / "VERSION"
    mobile_version = (
        mobile_version_file.read_text(encoding="utf-8").strip()
        if mobile_version_file.is_file()
        else ""
    )
    if not SEMVER.fullmatch(mobile_version):
        fail(errors, "Mobile/VERSION must exist and contain MAJOR.MINOR.PATCH")
    else:
        _, mobile_minor, mobile_patch = (int(part) for part in mobile_version.split("."))
        if mobile_minor > 99 or mobile_patch > 99:
            fail(errors, "Mobile/VERSION minor and patch components must each be between 0 and 99")

    mt5_requirements_file = root / "requirements_mt5"
    mt5_requirements = (
        {
            re.split(r"[\s<>=!~;\[]", line.strip(), maxsplit=1)[0]
            .lower()
            .replace("_", "-")
            for line in mt5_requirements_file.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        }
        if mt5_requirements_file.is_file()
        else set()
    )
    for dependency in ("MetaTrader5", "tzdata", "exchange-calendars"):
        if dependency.lower() not in mt5_requirements:
            fail(errors, f"requirements_mt5 is missing direct runtime dependency: {dependency}")
    requirements_text = mt5_requirements_file.read_text(encoding="utf-8") if mt5_requirements_file.is_file() else ""
    if "--require-hashes" not in requirements_text or "--only-binary=:all:" not in requirements_text:
        fail(errors, "requirements_mt5 must require hashed binary artifacts")
    expected_mt5_lock = {
        "MetaTrader5": ("5.0.5735", "0933ea4a9a52b32adcf5590df00f9f75ff380a02bad7b62e23cbd757f34fbb12"),
        "tzdata": ("2026.3", "dc096730c87af6cab1b171c9d532be840741ff5d459015e7f6947bd7d7e54931"),
        "exchange-calendars": ("4.13.2", "fc5a2ad0d61b5c3a6539a3061cd4cbb55c59f4a903455cec7926e4b798919996"),
        "numpy": ("2.3.2", "c63d95dc9d67b676e9108fe0d2182987ccb0f11933c1e8959f42fa0da8d4fa56"),
        "pandas": ("3.0.3", "a82d532a3351d435432cd913edbccaf8b8e01d4dd0e5ced5a8d2e8ecd94c7e44"),
        "pyluach": ("2.3.0", "4497b731aef59508b079dbf5f00bc5bf4329ac45090a6cd37b5a83756f0e69ab"),
        "toolz": ("1.1.0", "15ccc861ac51c53696de0a5d6d4607f99c210739caf987b5d2054f3efed429d8"),
        "korean-lunar-calendar": ("0.4.0", "c042e20de0bb702add6bec8d0f6da1ea8d3b170838e63846f70420cf341fe4e7"),
        "python-dateutil": ("2.9.0.post0", "a8b2bc7bffae282281c8140a97d3aa9c14da0b136dfe83f850eea9a5f7470427"),
        "six": ("1.17.0", "4721f391ed90541fddacab5acf947aa0d3dc7d27b2e1e8eda2be8970586c3274"),
    }
    for dependency, (locked_version, locked_hash) in expected_mt5_lock.items():
        pattern = rf"(?mi)^{re.escape(dependency)}=={re.escape(locked_version)}\s*\\\s*\n\s*--hash=sha256:{locked_hash}\s*$"
        if not re.search(pattern, requirements_text):
            fail(errors, f"requirements_mt5 lock is incomplete or changed for {dependency}=={locked_version}")

    wrapper_jar = root / "Mobile/gradle/wrapper/gradle-wrapper.jar"
    expected_wrapper_hash = "55243ef57851f12b070ad14f7f5bb8302daceeebc5bce5ece5fa6edb23e1145c"
    if not wrapper_jar.is_file() or hashlib.sha256(wrapper_jar.read_bytes()).hexdigest() != expected_wrapper_hash:
        fail(errors, "Gradle wrapper JAR is not the pinned official Gradle 9.4.1 artifact")
    wrapper_properties = root / "Mobile/gradle/wrapper/gradle-wrapper.properties"
    wrapper_properties_text = wrapper_properties.read_text(encoding="utf-8") if wrapper_properties.is_file() else ""
    if "distributionSha256Sum=2ab2958f2a1e51120c326cad6f385153bb11ee93b3c216c5fccebfdfbb7ec6cb" not in wrapper_properties_text:
        fail(errors, "Gradle 9.4.1 distribution checksum is not pinned")
    for bootstrap_relative in ("Mobile/bootstrap-gradle-wrapper.ps1", "Mobile/bootstrap-gradle-wrapper.sh"):
        bootstrap_path = root / bootstrap_relative
        bootstrap_text = bootstrap_path.read_text(encoding="utf-8") if bootstrap_path.is_file() else ""
        if expected_wrapper_hash not in bootstrap_text or "2ab2958f2a1e51120c326cad6f385153bb11ee93b3c216c5fccebfdfbb7ec6cb" not in bootstrap_text:
            fail(errors, f"Gradle bootstrap does not pin both verified artifacts: {bootstrap_relative}")
        if "wrapper.jar.sha256" in bootstrap_text:
            fail(errors, f"Gradle bootstrap trusts a mutable colocated checksum: {bootstrap_relative}")
    verification_metadata = root / "Mobile/gradle/verification-metadata.xml"
    verification_text = verification_metadata.read_text(encoding="utf-8") if verification_metadata.is_file() else ""
    if "<verify-metadata>true</verify-metadata>" not in verification_text or verification_text.count("<sha256 value=") < 100:
        fail(errors, "Gradle dependency verification metadata is missing or incomplete")
    if ('<trust file=".*-sources[.]jar" regex="true"' not in verification_text
            or '<trust file=".*-javadoc[.]jar" regex="true"' not in verification_text
            or '<trust file="gradle-9.4.1-src.zip"' not in verification_text):
        fail(errors, "Gradle IDE source/documentation attachments are not narrowly trusted")
    for unsafe_trust in ('<trust group=', '<trust name=', '<trust file=".*"', '<trust file=".*[.]jar"'):
        if unsafe_trust in verification_text:
            fail(errors, f"Gradle dependency verification contains an overly broad trust rule: {unsafe_trust}")

    canonical = root / "mt5" / "oppw_mt5_continuous.py"
    if not canonical.is_file():
        fail(errors, "canonical MT5 source is missing: mt5/oppw_mt5_continuous.py")
        canonical_text = ""
    else:
        canonical_text = canonical.read_text(encoding="utf-8")
        for required in ("PROJECT_VERSION = read_project_version()", 'BUILD_ID = f"oppw-{PROJECT_VERSION}"'):
            if required not in canonical_text:
                fail(errors, f"canonical MT5 source does not derive identity from VERSION: {required}")

    expected_core_modules = {
        "__init__.py",
        "account_config.py",
        "broker_execution.py",
        "coordination.py",
        "logging_support.py",
        "models.py",
        "monitoring.py",
        "position_lifecycle.py",
        "publishing.py",
        "runtime.py",
        "session_calendar.py",
        "settings.py",
        "strategy_decision.py",
        "utilities.py",
        "versioning.py",
    }
    core_dir = root / "mt5" / "oppw_core"
    actual_core_modules = {
        path.name for path in core_dir.glob("*.py")
    } if core_dir.is_dir() else set()
    if actual_core_modules != expected_core_modules:
        missing = sorted(expected_core_modules - actual_core_modules)
        unexpected = sorted(actual_core_modules - expected_core_modules)
        fail(
            errors,
            "canonical MT5 module set is incorrect; "
            f"missing={missing} unexpected={unexpected}",
        )
    if canonical_text:
        canonical_lines = len(canonical_text.splitlines())
        if canonical_lines >= 600:
            fail(errors, f"canonical MT5 entrypoint must remain a thin composition root; lines={canonical_lines}")
        for marker in (
            "SessionCalendarMixin",
            "PositionLifecycleMixin",
            "StrategyDecisionMixin",
            "MonitoringMixin",
            "BrokerExecutionMixin",
            "RuntimeMixin",
        ):
            if marker not in canonical_text:
                fail(errors, f"canonical MT5 composition is missing: {marker}")
        for forbidden in (
            "class BackendLeaseCoordinator",
            "class MobileMonitorPublisher",
            "def send_buy(",
            "def build_mobile_snapshot(",
        ):
            if forbidden in canonical_text:
                fail(errors, f"cohesive MT5 implementation leaked back into the entrypoint: {forbidden}")

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

    config_authority_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (core_dir / "versioning.py", core_dir / "account_config.py")
        if path.is_file()
    )
    required_config_names = (
        'ACCOUNT_CONFIG_FILES = {ACCOUNT_DEMO: "demo_mt5_config.py", ACCOUNT_REAL: "real_mt5_config.py"}',
        'account_dir / ACCOUNT_CONFIG_FILES[account]',
    )
    for marker in required_config_names:
        if marker not in config_authority_text:
            fail(errors, f"canonical MT5 account-config mapping is missing: {marker}")
    settings_path = core_dir / "settings.py"
    settings_text = settings_path.read_text(encoding="utf-8") if settings_path.is_file() else ""
    if "class Config:" not in settings_text:
        fail(errors, "canonical MT5 Config must be defined in oppw_core/settings.py")
    if "from .settings import Config" not in config_authority_text:
        fail(errors, "account configuration must import the canonical settings.Config")
    if "ACCOUNT_CONFIG_FALLBACKS" in canonical_text or "ACCOUNT_CONFIG_FALLBACKS" in config_authority_text:
        fail(errors, "legacy MT5 account-config aliases are not allowed")

    service_files = {
        "service/oppw_windows_supervisor.py": ("ACCOUNTS = (\"DEMO\", \"REAL\")", "ROLES = (\"EXECUTOR\", \"PUBLISHER\")", "assignmentTtlSeconds", "STARTUP_ORDER", "--service-ready-file"),
        "service/OPPWServiceHost.cs": ("ServiceName = \"OPPWContinuousSupervisor\"", "CreateKillOnCloseJob", "WTSQueryUserToken", "CreateProcessAsUser"),
        "service/install-service.ps1": (
            "ValidateSet('Master','Backup')", "delayed-auto", "RuntimeUser", "runtimeSid",
            "$acl.SetAccessRuleProtection($true, $false)", "RemoveAccessRuleSpecific",
            "$acl.SetOwner($administratorsIdentity)",
            "Set-ExactPathAcl -Path $programData -RuntimeSid $runtimeSecurityIdentifier -RuntimeAccess Traverse -RuntimeChildrenInherit",
            "Set-ExactPathAcl -Path $binDir", "Set-ExactPathAcl -Path $hostPath",
            "Set-ExactPathAcl -Path $runtimeDir", "Set-ExactPathAcl -Path $logDir",
            "Set-ExactPathAcl -Path $configPath",
        ),
        "Mobile/backend/service-control.php": ("setDesiredState", "strategy_service_control_events", "MASTER_ONLINE"),
        "Mobile/backend/strategy-controls.php": ("setRule", "recordWeekState", "strategy_entry_rule_week_events"),
    }
    for relative, markers in service_files.items():
        path = root / relative
        if not path.is_file():
            fail(errors, f"required service-supervision file is missing: {relative}")
            continue
        content = path.read_text(encoding="utf-8")
        for marker in markers:
            if marker not in content:
                fail(errors, f"service-supervision marker missing from {relative}: {marker}")
    installer_path = root / "service" / "install-service.ps1"
    installer_text = installer_path.read_text(encoding="utf-8") if installer_path.is_file() else ""
    for unsafe_marker in ('icacls.exe $programData', '"*${runtimeSid}:(OI)(CI)(M)"'):
        if unsafe_marker in installer_text:
            fail(errors, f"runtime user must not receive inherited Modify access over the LocalSystem service root: {unsafe_marker}")
    if re.search(
        r"Set-ExactPathAcl -Path \$(?:programData|binDir|hostPath|configPath)[^\r\n]*-RuntimeAccess Modify",
        installer_text,
    ):
        fail(errors, "runtime Modify access is allowed only on the service runtime and log directories")

    config_examples = sorted((root / "mt5").rglob("*config*.example.py"))
    expected_config = root / "mt5" / "oppw_mt5_config.example.py"
    if config_examples != [expected_config]:
        names = ", ".join(path.relative_to(root).as_posix() for path in config_examples)
        fail(errors, "exactly one canonical MT5 config example is allowed; found: " + names)
    example_text = expected_config.read_text(encoding="utf-8") if expected_config.is_file() else ""
    for forbidden in ("class Config", "@dataclass", "def env_"):
        if forbidden in example_text:
            fail(errors, f"MT5 config example duplicates canonical configuration: {forbidden}")
    for required in (
        "MT5_TERMINAL_PATH =",
        "MT5_LOGIN =",
        "MT5_PASSWORD =",
        "MT5_SERVER =",
        "MONITOR_WRITE_TOKEN =",
        "OVERRIDES = {",
    ):
        if required not in example_text:
            fail(errors, f"MT5 override-only config example is missing: {required}")
    migration_tool = root / "tools" / "migrate_mt5_config.py"
    migration_text = migration_tool.read_text(encoding="utf-8") if migration_tool.is_file() else ""
    for required in ("without_oppw_environment", "values_verified", "os.replace"):
        if required not in migration_text:
            fail(errors, f"MT5 private-config migration safety marker missing: {required}")

    tracked_config_classes = []
    for path in tracked:
        relative = path.relative_to(root).as_posix()
        if not relative.startswith("mt5/") or path.suffix != ".py" or relative.startswith("mt5/tests/"):
            continue
        if "class Config:" in path.read_text(encoding="utf-8") and relative != "mt5/oppw_core/settings.py":
            tracked_config_classes.append(relative)
    if tracked_config_classes:
        fail(errors, "copied MT5 Config classes found: " + ", ".join(tracked_config_classes))

    for test in (root / "mt5" / "tests").glob("test_*.py"):
        text = test.read_text(encoding="utf-8")
        if re.search(r"oppw_mt5_continuous_v[^\"']+\.py", text):
            fail(errors, f"test references a historical source copy: {test.relative_to(root)}")

    android_build = root / "Mobile" / "app" / "build.gradle.kts"
    android_text = android_build.read_text(encoding="utf-8") if android_build.is_file() else ""
    android_version_markers = (
        'rootProject.file("VERSION")',
        "mobileVersionCodeEpoch = 1_000_000",
        "versionName = mobileVersion",
        "versionCode = mobileVersionCode",
    )
    if any(marker not in android_text for marker in android_version_markers):
        fail(errors, "Android versionName/versionCode must be derived from Mobile/VERSION with the canonical epoch")
    if re.search(r"versionName\s*=\s*\"", android_text):
        fail(errors, "Android contains a hard-coded versionName")

    contract_files = {
        "contracts/README.md": ("Executable cross-component contracts",),
        "contracts/expectations.json": ('"decisionToSendMs"', '"backendPublicationMs"', '"authorityStages"', '"maxDrawdownPercent"'),
        "contracts/fixtures/open-position.json": ('"strategyDocument"', '"PUBLISHED"'),
        "tools/validate_contracts.py": (
            "coordination.php", "ingest.php", "status.php", "analytics.php",
            "mobile-receipt.php", "ContractResponseParserTest", "sourceGranularity",
        ),
        "Mobile/app/src/test/java/com/oppw/monitor/data/ContractResponseParserTest.kt": (
            "parseAccounts", "parseResponse", "parseAnalytics", "maxDrawdownPercent",
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

    bounded_snapshot_files = {
        "Mobile/backend/sql/schema.sql": ("UNIQUE KEY uq_snapshot_strategy (strategy_key)",),
        "Mobile/backend/sql/migrate_v54_1_current_snapshot.sql": (
            "CREATE TABLE IF NOT EXISTS strategy_snapshots",
            "uq_snapshot_strategy",
        ),
        "Mobile/backend/sql/migration-order.txt": ("migrate_v54_1_current_snapshot.sql",),
        "Mobile/backend/ingest.php": (
            "SELECT payload FROM strategy_snapshots WHERE strategy_key = ? FOR UPDATE",
            "ON DUPLICATE KEY UPDATE captured_at = ?, payload = ?",
        ),
        "Mobile/backend/status.php": (
            "SELECT payload, captured_at FROM strategy_snapshots WHERE strategy_key = ?",
        ),
        "Mobile/backend/accounts.php": (
            "LEFT JOIN strategy_snapshots s ON s.strategy_key = a.account_key",
        ),
    }
    for relative, markers in bounded_snapshot_files.items():
        path = root / relative
        if not path.is_file():
            fail(errors, f"bounded current-snapshot file is missing: {relative}")
            continue
        content = path.read_text(encoding="utf-8")
        for marker in markers:
            if marker not in content:
                fail(errors, f"bounded current-snapshot marker missing from {relative}: {marker}")

    status_path = root / "Mobile" / "backend" / "status.php"
    status_text = status_path.read_text(encoding="utf-8") if status_path.is_file() else ""
    if "function equity_points(" in status_text or "$whereSql" in status_text:
        fail(errors, "status endpoint must not expose a raw SQL-fragment query helper")

    security_boundary_files = {
        "Mobile/backend/mobile-receipt.php": (
            "'MOBILE_RECEIPT'", "diagnostic write failed",
        ),
        "Mobile/backend/analytics.php": (
            "requested_analytics_rolling_weeks", "$allHistory", "enforce_single_flight", "oppw_analytics_segmented_rows",
            "oppw_analytics_data_watermark", "X-OPPW-Analytics-Cache: HIT", "X-OPPW-Analytics-Segments",
            "name='MOBILE_RECEIPT'", "AND occurred_at>=? AND occurred_at<?", "windowEndDate",
        ),
        "Mobile/backend/analytics-window.php": (
            "window_end_date must use YYYY-MM-DD", "Europe/Warsaw", "availableStartDate", "availableEndDate",
        ),
        "Mobile/backend/tests/analytics-window-test.php": (
            "default rolling window did not end at the latest observation",
            "historical window did not preserve its four-week duration",
            "historical window ignored Warsaw daylight-saving time",
        ),
        "Mobile/backend/analytics-cache.php": (
            "OPPW_ANALYTICS_CACHE_MAX_BYTES", "OPPW_ANALYTICS_SEGMENT_MAX_BYTES", "analytics_cache_ttl_seconds",
            "analytics_segment_cache_ttl_seconds", "oppw_analytics_week_segments", "hash_hmac(", "realpath(__DIR__)",
            "is_link($path)", "LOCK_SH", "LOCK_EX",
            "latestMinuteEquity", "latestDailyEquity", "strategy_execution_stages", "MOBILE_RECEIPT",
        ),
        "Mobile/backend/market-admin.php": (
            "independent_manual_admin_token", "require_same_origin_browser_post",
        ),
        "Mobile/backend/trade-admin.php": (
            "independent_manual_admin_token", "require_same_origin_browser_post",
        ),
        "Mobile/backend/push-admin.php": (
            "require_https", "browser_admin_headers", "require_same_origin_browser_post",
            "enforce_rate_limit('push-admin'",
        ),
        "Mobile/backend/tests/security-boundaries-test.php": (
            "pairing token fallback remains active", "paired receipt still writes execution authority",
            "unused Apache artifact remains", "deployment-specific Nginx example remains",
            "FCM OAuth cache fell back to shared system temp",
            "strategy specifications retain the undefined authentication path", "analytics cache boundary missing",
        ),
        "Mobile/backend/tests/analytics-cache-test.php": (
            "data watermark did not invalidate the cache key", "cache hit changed the encoded response",
            "expired cache entry was reused", "authorization context did not isolate cache entries",
        ),
        "Mobile/backend/tests/analytics-segment-test.php": (
            "completed Warsaw weeks were not split independently", "warm segmented read queried completed historical weeks again",
            "current Warsaw week was cached as historical", "warm and cold segmented rows differ",
        ),
        "Mobile/app/src/main/java/com/oppw/monitor/data/Models.kt": (
            "val allHistory: Boolean = false", "val windowEndDate: String = \"\"",
        ),
        "Mobile/app/src/main/java/com/oppw/monitor/data/StatusApiClient.kt": (
            "analyticsWindowQuery", "&all_history=1", "&window_end_date=",
        ),
        "Mobile/app/src/main/java/com/oppw/monitor/ui/screens/AnalyticsScreen.kt": (
            "All history", "allHistory = false", "allHistory = true", "Window ending", "Latest available observation",
        ),
        "docs/decisions/0018-paired-mobile-receipts-are-diagnostic.md": (
            "Paired mobile receipts are diagnostic", "never enters an immutable strategy-authority table",
        ),
        "docs/decisions/0023-secure-token-storage-and-verified-build-inputs.md": (
            "Shared temporary storage is not a fallback",
            "strict dependency verification metadata", "deployment-specific Apache, Nginx, or `.htaccess`",
        ),
        "docs/decisions/0019-explicit-all-history-analytics.md": (
            "Explicit all-history analytics", "all_history=1", "A request for 82 weeks remains 82 weeks",
        ),
        "docs/decisions/0020-watermark-keyed-analytics-response-cache.md": (
            "Watermark-keyed analytics response cache", "Authorization and throttling are never cached or bypassed",
            "No database migration or Android contract change is required",
        ),
        "docs/decisions/0021-completed-week-analytics-input-segments.md": (
            "Completed-week analytics input segments", "latest requested week is always queried live",
            "No database migration or Android contract change is required",
        ),
        "docs/decisions/0022-streaming-daily-equity-reduction.md": (
            "Streaming daily-equity reduction", "dedicated streaming prepass",
            "No database migration is required",
        ),
        "docs/decisions/0027-movable-fixed-duration-analytics-windows.md": (
            "Movable fixed-duration analytics windows", "window_end_date=YYYY-MM-DD",
            "No database migration is required",
        ),
    }
    for relative, markers in security_boundary_files.items():
        path = root / relative
        if not path.is_file():
            fail(errors, f"required backend security-boundary file is missing: {relative}")
            continue
        content = path.read_text(encoding="utf-8")
        for marker in markers:
            if marker not in content:
                fail(errors, f"backend security-boundary marker missing from {relative}: {marker}")

    mobile_receipt_text = (root / "Mobile/backend/mobile-receipt.php").read_text(encoding="utf-8")
    for forbidden in ("authority.php", "oppw_authority_event", "strategy_execution_stages"):
        if forbidden in mobile_receipt_text:
            fail(errors, f"paired mobile receipt crosses execution authority via {forbidden}")
    for apache_artifact in (
        "Mobile/backend/apache-vhost.example.conf", "Mobile/backend/.htaccess",
        "Mobile/backend/admin/.htaccess", "Mobile/backend/private/.htaccess",
        "Mobile/backend/publisher/.htaccess", "Mobile/backend/sql/.htaccess",
    ):
        if (root / apache_artifact).exists():
            fail(errors, f"unused Apache deployment artifact remains: {apache_artifact}")

    lifecycle_files = {
        "Mobile/backend/sql/schema.sql": (
            "strategy_equity_daily", "strategy_retention_runs", "strategy_market_points_no_delete",
        ),
        "Mobile/backend/sql/migrate_data_lifecycle.sql": (
            "strategy_equity_daily", "strategy_retention_runs", "strategy_market_points_no_delete",
            "idx_event_retention_time", "idx_equity_retention_time", "ON DELETE RESTRICT",
        ),
        "Mobile/backend/sql/migrate_v55_entry_rules.sql": (
            "strategy_entry_rule_controls", "strategy_entry_rule_control_events",
            "strategy_entry_rule_week_state", "strategy_entry_rule_week_events",
        ),
        "Mobile/backend/sql/migrate_v56_single_premarket_low.sql": (
            "premarket_low_enabled", "premarket_range_enabled AND premarket_close_low_enabled",
        ),
        "Mobile/backend/sql/migration-order.txt": (
            "migrate_data_lifecycle.sql", "migrate_v55_entry_rules.sql", "migrate_v56_single_premarket_low.sql",
        ),
        "Mobile/backend/admin/retention.php": (
            "OPPW_EVENT_RETENTION_DAYS = 180", "OPPW_EQUITY_RETENTION_DAYS = 400",
            "name <> 'EXECUTION_STAGE'", "GET_LOCK", "oppw-retention-ndjson-v1",
        ),
        "Mobile/backend/status.php": ("strategy_equity_daily", "close_equity AS equity"),
        "Mobile/backend/equity-periods.php": (
            "weekCashOpen", "manual", "openedAt", "setTime(15, 30, 0)",
            "dailyStart", "weeklyStart",
        ),
        "Mobile/app/src/main/java/com/oppw/monitor/data/EquityBoundaries.kt": (
            "weeklyEquityFromMarketOpen", "publishedWeekCashOpen", "publishedOpen ?: return points",
            "sameIsoWeek", "position?.takeIf { it.manual }",
        ),
        "Mobile/backend/tests/equity-periods-test.php": (
            "first-session daily", "holiday-first-session daily", "manual-preopen daily",
            "manual-after-open weekly", "following-day daily", "completed-week weekly",
        ),
        "Mobile/backend/analytics.php": ("strategy_equity_daily", "equity-history-v1", "DAILY_FALLBACK"),
        "Mobile/backend/analytics-drawdown.php": (
            "cashFlowAdjusted", "statisticsExact", "MINUTE_WITH_DAILY_FALLBACK",
            "oppw_downsample_drawdown_series", "oppw_reduce_daily_equity_history",
            "oppw_update_trade_episode_states_by_time",
        ),
        "Mobile/backend/tests/analytics-drawdown-test.php": (
            "optimized daily reduction changed the canonical minute-derived state",
        ),
        "tools/validate_backup_restore.ps1": (
            "--single-transaction", "--routines", "--triggers", "sourceContainer",
            "restoreContainer", "strategy_market_points", "strategy_service_control_events",
        ),
        "tools/backup_mysql.ps1": (
            "--single-transaction", "--routines", "--triggers", "TLS_REQUIRED", "tls=required",
            "WINDOWS_EFS", "Restore-And-Verify", "Start-Transcript", "KeepDaily = 35",
            "KeepMonthly = 12", "KeepLogDays = 180",
        ),
        "tools/install_mysql_backup_task.ps1": (
            "OPPW MySQL Production Backup", "D:\\OPPW-Backups\\mysql", "02:15",
            "New-ScheduledTaskTrigger -Daily", "LogonType Interactive", "RunOnlyIfNetworkAvailable",
        ),
        "tools/write_mysql_client_config.php": (
            "PHP_SAPI !== 'cli'", "ssl-mode=REQUIRED", "file_put_contents", "LOCK_EX",
        ),
    }
    for relative, markers in lifecycle_files.items():
        path = root / relative
        if not path.is_file():
            fail(errors, f"required data-lifecycle file is missing: {relative}")
            continue
        content = path.read_text(encoding="utf-8")
        for marker in markers:
            if marker not in content:
                fail(errors, f"data-lifecycle marker missing from {relative}: {marker}")

    migration_order = root / "Mobile" / "backend" / "sql" / "migration-order.txt"
    migration_names = (
        [
            line.strip()
            for line in migration_order.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        if migration_order.is_file()
        else []
    )
    if not migration_names or migration_names[-1] != "migrate_v56_2_execution_lifecycle_links.sql":
        fail(errors, "migrate_v56_2_execution_lifecycle_links.sql must be the last ordered forward migration")
    elif migration_names.index("migrate_data_lifecycle.sql") >= migration_names.index("migrate_v55_entry_rules.sql"):
        fail(errors, "migrate_v55_entry_rules.sql must follow migrate_data_lifecycle.sql")
    elif migration_names.index("migrate_v55_entry_rules.sql") >= migration_names.index("migrate_v56_single_premarket_low.sql"):
        fail(errors, "migrate_v56_single_premarket_low.sql must follow migrate_v55_entry_rules.sql")
    elif migration_names.index("migrate_v56_single_premarket_low.sql") >= migration_names.index("migrate_v56_2_execution_lifecycle_links.sql"):
        fail(errors, "migrate_v56_2_execution_lifecycle_links.sql must follow migrate_v56_single_premarket_low.sql")

    retention_path = root / "Mobile" / "backend" / "admin" / "retention.php"
    retention_text = retention_path.read_text(encoding="utf-8") if retention_path.is_file() else ""
    protected_retention_tables = (
        "strategy_market_points", "strategy_service_control_events", "strategy_specifications",
        "strategy_account_spec_assignments", "strategy_decisions", "strategy_execution_stages",
        "strategy_fills", "strategy_protection_changes", "strategy_trade_ledger", "account_cash_flows",
        "strategy_entry_rule_controls", "strategy_entry_rule_control_events",
        "strategy_entry_rule_week_state", "strategy_entry_rule_week_events",
    )
    for table in protected_retention_tables:
        if re.search(rf"DELETE\s+FROM\s+`?{re.escape(table)}\b", retention_text, re.IGNORECASE):
            fail(errors, f"retention command contains a forbidden deletion path: {table}")

    production_backup = root / "tools" / "backup_mysql.ps1"
    production_backup_text = production_backup.read_text(encoding="utf-8") if production_backup.is_file() else ""
    if "--password=" in production_backup_text or "-p$" in production_backup_text:
        fail(errors, "production backup must not pass the database password on a process command line")

    release_script = root / "tools" / "release.ps1"
    release_text = release_script.read_text(encoding="utf-8") if release_script.is_file() else ""
    release_gates = (
        "validate_source.py",
        "-m unittest discover",
        "Get-Command php",
        "validate_mysql.ps1",
        "validate_backup_restore.ps1",
        "backup_mysql.ps1",
        "install_mysql_backup_task.ps1",
        "write_mysql_client_config.php",
        "equity-periods-test.php",
        "validate_contracts.py",
        "--dependency-verification strict",
        "testDebugUnitTest assembleDebug assembleRelease",
        "git diff --cached --quiet",
        "service\\tests",
        "build-service-host.ps1",
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
    if (backend / "nginx.example.conf").exists():
        fail(errors, "deployment-specific Nginx configuration must not be committed")
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
    print(f"SOURCE VALIDATION PASSED version={version} mobileVersion={mobile_version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
