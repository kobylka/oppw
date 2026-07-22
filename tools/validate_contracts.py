"""Run the real OPPW publisher/backend/database/Android contract in isolation."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


MYSQL_IMAGE = "mysql:8.4"
WRITE_TOKEN = secrets.token_urlsafe(32)
PAIRING_SECRET = secrets.token_urlsafe(32)
TOKEN_HMAC_SECRET = secrets.token_urlsafe(32)
RATE_LIMIT_HMAC_SECRET = secrets.token_urlsafe(32)
PAIRING_CODE = "OPPWTEST2026"
DB_USER = "oppw_contract"
DB_PASSWORD = secrets.token_hex(24)


def run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, text=True, check=True, **kwargs)


def docker_sql(
    docker: str,
    container: str,
    sql: str,
    docker_env: dict[str, str],
    database: bool = True,
) -> str:
    command = [docker, "exec", "-i", container, "mysql", "-N", "-uroot"]
    if database:
        command.append("--database=oppw_monitor")
    completed = run(command, input=sql, capture_output=True, env=docker_env)
    return completed.stdout.strip()


def iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def substitute(value: Any, replacements: dict[str, str]) -> Any:
    if isinstance(value, dict):
        return {key: substitute(item, replacements) for key, item in value.items()}
    if isinstance(value, list):
        return [substitute(item, replacements) for item in value]
    if isinstance(value, str):
        for key, replacement in replacements.items():
            value = value.replace("${" + key + "}", replacement)
    return value


def canonical_json(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def http_json(
    method: str,
    url: str,
    payload: Any | None = None,
    token: str = "",
    expected: tuple[int, ...] = (200,),
    raw_body: bytes | None = None,
) -> tuple[int, dict[str, Any], str]:
    body = raw_body
    if body is None and payload is not None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = "Bearer " + token
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        response = urllib.request.urlopen(request, timeout=20)
    except urllib.error.HTTPError as error:
        response = error
    status = int(response.status)
    content_type = response.headers.get("Content-Type", "")
    text = response.read().decode("utf-8", errors="strict")
    if not content_type.lower().startswith("application/json"):
        raise AssertionError(f"{url} returned non-JSON Content-Type {content_type!r}: {text[:300]}")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as error:
        raise AssertionError(f"{url} returned invalid JSON: {text[:300]}") from error
    if not isinstance(parsed, dict):
        raise AssertionError(f"{url} did not return a JSON object")
    if status not in expected:
        raise AssertionError(f"{url} returned HTTP {status}, expected {expected}: {parsed}")
    return status, parsed, text


def build_ingest(fixture: dict[str, Any], version: str) -> tuple[dict[str, Any], dict[str, str]]:
    now = datetime.now(timezone.utc)
    base = now - timedelta(seconds=3)
    captured = base + timedelta(seconds=1)
    decision_id = hashlib.sha256(b"oppw-contract-decision").hexdigest()[:32]
    document = fixture["strategyDocument"]
    document["strategy"]["version"] = version
    spec_hash = hashlib.sha256(canonical_json(document).encode("utf-8")).hexdigest()
    spec_id = spec_hash[:32]
    replacements = {
        "CAPTURED_AT": iso(captured),
        "OPENED_AT": iso(base - timedelta(hours=1)),
        "NEXT_ACTION_AT": iso(base + timedelta(hours=1)),
        "SCHEDULED_AT": iso(base),
        "STARTED_AT": iso(base + timedelta(milliseconds=50)),
        "DECISION_ID": decision_id,
    }
    snapshot = substitute(fixture["snapshot"], replacements)
    decision = fixture["decision"] | {
        "decisionId": decision_id,
        "recordedAt": iso(base + timedelta(milliseconds=100)),
        "build": "oppw-" + version,
        "strategySpecId": spec_id,
        "strategySpecHash": spec_hash,
    }
    snapshot["strategyDecision"] = decision
    events = []
    for index, stage in enumerate(fixture["stages"]):
        event_at = base + timedelta(milliseconds=int(stage["offsetMs"]))
        details = {
            "execution_id": fixture["executionId"],
            "decision_id": decision_id,
            "strategy_spec_id": spec_id,
            "position_ticket": fixture["positionTicket"],
            "stage": stage["stage"],
            "event_at": iso(event_at),
            "scheduled_at": iso(base),
            "result": stage.get("result"),
            "retcode": stage.get("retcode"),
            "filling_mode": stage.get("fillingMode", ""),
            "reference_price": stage.get("referencePrice"),
            "actual_price": stage.get("actualPrice"),
            "latency_ms": stage.get("latencyMs"),
            "reason": stage.get("reason", "CONTRACT"),
            "order_ticket": stage.get("orderTicket", 0),
            "deal_ticket": stage.get("dealTicket", 0),
            "side": stage.get("side", "BUY"),
            "volume": stage.get("volume", 0.02),
            "old_sl": stage.get("oldSl"),
            "new_sl": stage.get("newSl"),
            "old_tp": 0.0,
            "new_tp": 0.0,
        }
        events.append({
            "time": iso(event_at),
            "level": "INFO",
            "name": "EXECUTION_STAGE",
            "result": stage.get("result"),
            "message": f"contract lifecycle stage {index}: {stage['stage']}",
            "details": details,
        })
    specification = {
        "specId": spec_id,
        "specHash": spec_hash,
        "specKey": "OPPW24",
        "specVersion": version,
        "effectiveFrom": iso(base),
        "createdAt": iso(base),
        "build": "oppw-" + version,
        "document": document,
    }
    payload = {
        "accountKey": fixture["accountKey"],
        "capturedAt": iso(captured),
        "snapshot": snapshot,
        "events": events,
        "strategyDecision": decision,
        "strategySpecification": specification,
    }
    return payload, {"decisionId": decision_id, "specId": spec_id, "specHash": spec_hash}


def assert_close(actual: Any, expected: float, label: str) -> None:
    if actual is None or abs(float(actual) - expected) > 0.01:
        raise AssertionError(f"{label}: expected {expected}, got {actual}")


def sql_text(value: Any) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def seed_analytics_fixture(
    docker: str,
    container: str,
    account_key: str,
    fixture: dict[str, Any],
    current_monday: datetime,
    docker_env: dict[str, str],
) -> None:
    trade_rows = []
    for item in fixture["closedTrades"]:
        opened = (current_monday + timedelta(
            weeks=int(item["weekOffset"]), days=int(item["dayOffset"]),
        )).replace(hour=15, minute=30)
        closed = opened + timedelta(hours=1)
        open_price = float(item["openPrice"])
        close_price = float(item["closePrice"])
        profit = float(item["profit"])
        balance_before = float(item["balanceBefore"])
        raw_return_percent = (close_price / open_price - 1.0) * 100.0
        trade_rows.append(
            "({},{},'US100','BUY',1.0,{},{},{},{},{},{},{},{},{},{})".format(
                sql_text(account_key), int(item["ticket"]),
                sql_text(opened.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]),
                sql_text(closed.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]),
                open_price, close_price, profit, raw_return_percent, balance_before,
                balance_before + profit, sql_text(item["exitReason"]), float(item["entryLeverage"]),
            )
        )
    docker_sql(
        docker, container,
        "INSERT INTO strategy_trades(strategy_key,position_ticket,symbol,side,volume,opened_at,closed_at,open_price,close_price,profit,profit_percent,balance_before,balance_after,exit_reason,entry_leverage) VALUES "
        + ",".join(trade_rows), docker_env,
    )

    equity_rows = []
    for item in fixture["dailyEquity"]:
        captured = (current_monday + timedelta(
            weeks=int(item["weekOffset"]), days=int(item["dayOffset"]),
        )).replace(hour=21, minute=0)
        captured_utc = captured.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        equity = float(item["equity"])
        equity_rows.append(
            f"({sql_text(account_key)},{sql_text(captured_utc)},{equity},{equity},0,0,NULL)"
        )
    docker_sql(
        docker, container,
        f"DELETE FROM strategy_equity_points WHERE strategy_key={sql_text(account_key)}",
        docker_env,
    )
    docker_sql(
        docker, container,
        "INSERT INTO strategy_equity_points(strategy_key,captured_minute,balance,equity,deposit,current_profit,position_ticket) VALUES "
        + ",".join(equity_rows), docker_env,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--php", default="")
    parser.add_argument("--docker", default="")
    args = parser.parse_args()
    root = args.root.resolve()
    php = args.php or shutil.which("php")
    docker = args.docker or shutil.which("docker")
    if not php:
        raise RuntimeError("PHP CLI is required for contract validation")
    if not docker:
        raise RuntimeError("Docker is required for contract validation")

    version = (root / "VERSION").read_text(encoding="utf-8").strip()
    fixture = json.loads((root / "contracts/fixtures/open-position.json").read_text(encoding="utf-8"))
    expected = json.loads((root / "contracts/expectations.json").read_text(encoding="utf-8"))
    ingest_payload, identities = build_ingest(fixture, version)
    owner_id = uuid.uuid4().hex
    container = "oppw-contract-" + uuid.uuid4().hex[:12]
    php_process: subprocess.Popen[str] | None = None
    stdout_handle: Any | None = None
    stderr_handle: Any | None = None

    with tempfile.TemporaryDirectory(prefix="oppw-contract-") as temp_name:
        temp = Path(temp_name)
        docker_env = os.environ.copy()
        docker_env["DOCKER_CONFIG"] = str(temp / "docker-config")
        (temp / "docker-config").mkdir()
        php_stdout = temp / "php.stdout.log"
        php_stderr = temp / "php.stderr.log"
        try:
            run([docker, "info", "--format", "{{.ServerVersion}}"], env=docker_env, capture_output=True)
            run([
                docker, "run", "--detach", "--rm", "--name", container,
                "--publish", "127.0.0.1::3306",
                "--env", "MYSQL_ALLOW_EMPTY_PASSWORD=yes",
                "--env", "MYSQL_DATABASE=oppw_monitor",
                MYSQL_IMAGE,
            ], env=docker_env, capture_output=True)

            ready = False
            for _ in range(80):
                probe = subprocess.run([
                    docker, "exec", container, "mysql", "-N", "-uroot", "-e",
                    "SELECT SCHEMA_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME='oppw_monitor'",
                ], env=docker_env, text=True, capture_output=True)
                if probe.returncode == 0 and probe.stdout.strip() == "oppw_monitor":
                    ready = True
                    break
                time.sleep(0.5)
            if not ready:
                raise RuntimeError("contract MySQL did not initialize within 40 seconds")

            migration_names = [
                line.strip() for line in (root / "Mobile/backend/sql/migration-order.txt").read_text(encoding="utf-8").splitlines()
                if line.strip() and not line.lstrip().startswith("#")
            ]
            for name in migration_names:
                sql = (root / "Mobile/backend/sql" / name).read_text(encoding="utf-8")
                docker_sql(docker, container, sql, docker_env, database=True)

            docker_sql(docker, container, f"""
                CREATE USER IF NOT EXISTS '{DB_USER}'@'%' IDENTIFIED BY '{DB_PASSWORD}';
                GRANT ALL PRIVILEGES ON oppw_monitor.* TO '{DB_USER}'@'%';
                FLUSH PRIVILEGES;
            """, docker_env)
            port_result = run([docker, "port", container, "3306/tcp"], env=docker_env, capture_output=True).stdout.strip()
            db_port = int(port_result.rsplit(":", 1)[1])

            config_path = temp / "contract-config.php"
            config_path.write_text(f"""<?php
declare(strict_types=1);
return [
  'dsn' => 'mysql:host=127.0.0.1;port={db_port};dbname=oppw_monitor;charset=utf8mb4',
  'db_user' => '{DB_USER}', 'db_password' => '{DB_PASSWORD}',
  'write_token' => '{WRITE_TOKEN}',
  'token_hmac_secret' => '{TOKEN_HMAC_SECRET}',
  'pairing_hmac_secret' => '{PAIRING_SECRET}',
  'rate_limit_hmac_secret' => '{RATE_LIMIT_HMAC_SECRET}',
  'access_token_ttl_seconds' => 900, 'refresh_token_ttl_days' => 90,
  'pairing_code_ttl_minutes' => 10, 'default_account_key' => 'DEMO',
  'event_limit' => 50, 'monitor_heartbeat_stale_seconds' => 180,
  'monitor_price_warning_seconds' => 60, 'service_supervisor_stale_seconds' => 20, 'require_https' => false,
  'trust_forwarded_proto' => false, 'push_enabled' => false,
  'firebase_project_id' => '', 'firebase_service_account_file' => ''
];
""", encoding="utf-8")

            pairing_hash = hmac.new(PAIRING_SECRET.encode(), PAIRING_CODE.encode(), hashlib.sha256).hexdigest()
            docker_sql(docker, container, f"""
                INSERT INTO monitor_pairing_codes(id,code_hash,label,expires_at)
                VALUES (1,'{pairing_hash}','contract',UTC_TIMESTAMP(3)+INTERVAL 10 MINUTE);
                INSERT INTO monitor_pairing_code_accounts(pairing_code_id,account_key,can_control_service) VALUES (1,'DEMO',TRUE);
            """, docker_env)

            php_port = free_port()
            php_env = os.environ.copy()
            php_env["OPPW_MONITOR_CONFIG"] = str(config_path)
            creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            stdout_handle = php_stdout.open("w", encoding="utf-8")
            stderr_handle = php_stderr.open("w", encoding="utf-8")
            php_process = subprocess.Popen(
                [php, "-S", f"127.0.0.1:{php_port}", "-t", str(root / "Mobile/backend")],
                env=php_env, stdout=stdout_handle, stderr=stderr_handle, text=True,
                creationflags=creation_flags,
            )
            base_url = f"http://127.0.0.1:{php_port}/"
            for _ in range(60):
                try:
                    _, health, _ = http_json("GET", base_url + "health.php")
                    if health.get("ok") is True:
                        break
                except Exception:
                    time.sleep(0.25)
            else:
                raise RuntimeError("PHP contract server did not become healthy")

            _, pair, _ = http_json("POST", base_url + "auth/pair.php", {
                "pairingCode": PAIRING_CODE, "deviceName": "Contract validator",
            }, expected=(201,))
            access_token = pair["session"]["accessToken"]

            processes = [
                {"account": account, "role": role, "running": True, "pid": index + 10,
                 "startedAt": iso(datetime.now(timezone.utc)), "restartCount": 1, "lastExitCode": None}
                for index, (account, role) in enumerate(
                    (("DEMO", "EXECUTOR"), ("DEMO", "PUBLISHER"), ("REAL", "EXECUTOR"), ("REAL", "PUBLISHER"))
                )
            ]
            _, backup_first, _ = http_json("POST", base_url + "service-control.php", {
                "action": "heartbeat", "nodeId": "b" * 32, "nodeRole": "BACKUP",
                "hostname": "backup-contract", "pid": 2, "build": "oppw-" + version,
                "startedAt": iso(datetime.now(timezone.utc)), "processes": processes,
            }, token=WRITE_TOKEN)
            if not all(item["assigned"] for item in backup_first["assignments"]):
                raise AssertionError("backup was not assigned while master was absent")
            _, master_heartbeat, _ = http_json("POST", base_url + "service-control.php", {
                "action": "heartbeat", "nodeId": "a" * 32, "nodeRole": "MASTER",
                "hostname": "master-contract", "pid": 1, "build": "oppw-" + version,
                "startedAt": iso(datetime.now(timezone.utc)), "processes": processes,
            }, token=WRITE_TOKEN)
            if not all(item["assigned"] for item in master_heartbeat["assignments"]):
                raise AssertionError("master was not assigned on return")
            _, backup_idled, _ = http_json("POST", base_url + "service-control.php", {
                "action": "heartbeat", "nodeId": "b" * 32, "nodeRole": "BACKUP",
                "hostname": "backup-contract", "pid": 2, "build": "oppw-" + version,
                "startedAt": iso(datetime.now(timezone.utc)), "processes": processes,
            }, token=WRITE_TOKEN)
            if any(item["assigned"] for item in backup_idled["assignments"]):
                raise AssertionError("backup remained assigned after master returned")
            http_json("POST", base_url + "service-control.php", {
                "action": "heartbeat", "nodeId": "b" * 32, "nodeRole": "BACKUP",
                "hostname": "master-contract", "pid": 2, "build": "oppw-" + version,
                "startedAt": iso(datetime.now(timezone.utc)), "processes": processes,
            }, token=WRITE_TOKEN, expected=(409,))

            _, lease, _ = http_json("POST", base_url + "coordination.php", {
                "action": "acquireLease", "accountKey": "DEMO", "role": "PUBLISHER",
                "ownerId": owner_id, "leaseName": "PUBLISHER", "ttlSeconds": 120,
                "hostname": "contract", "pid": 1, "build": "oppw-" + version,
            }, token=WRITE_TOKEN)
            if lease.get("acquired") is not True:
                raise AssertionError(f"publisher lease was not acquired: {lease}")
            ingest_payload["coordination"] = {
                "role": "PUBLISHER", "ownerId": owner_id,
                "fencingToken": int(lease["fencingToken"]),
            }

            for delivery in range(2):
                _, stored, _ = http_json(
                    "POST", base_url + "ingest.php", ingest_payload,
                    token=WRITE_TOKEN, expected=(201,),
                )
                if stored.get("strategyDecisionId") != identities["decisionId"]:
                    raise AssertionError(f"decision acknowledgement mismatch on delivery {delivery + 1}")
                if stored.get("strategySpecificationHash") != identities["specHash"]:
                    raise AssertionError(f"specification acknowledgement mismatch on delivery {delivery + 1}")

            local_now = datetime.now(timezone.utc).astimezone(ZoneInfo("Europe/Warsaw"))
            current_monday = (local_now - timedelta(days=local_now.weekday())).replace(hour=15, minute=30, second=0, microsecond=0)
            market_rows = []
            for week_offset, first, latest in (
                (0, (100.0, 101.0, 99.0, 100.0), (110.0, 112.0, 108.0, 111.0)),
                (-1, (200.0, 201.0, 199.0, 200.0), (220.0, 224.0, 216.0, 222.0)),
            ):
                monday = current_monday + timedelta(weeks=week_offset)
                friday = (monday + timedelta(days=4)).replace(hour=23, minute=59)
                for captured, (open_price, high, low, close) in ((monday, first), (friday, latest)):
                    captured_utc = captured.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                    market_rows.append(
                        "('DEMO','{}',{},{},{},{},{},{},{},'REGULAR')".format(
                            captured_utc, close, close, close + 0.1, open_price, high, low, close,
                        )
                    )
            docker_sql(docker, container, "DELETE FROM strategy_market_points WHERE strategy_key='DEMO';", docker_env)
            docker_sql(
                docker,
                container,
                "INSERT INTO strategy_market_points(strategy_key,captured_minute,current_price,bid,ask,m1_open,m1_high,m1_low,m1_close,phase) VALUES "
                + ",".join(market_rows),
                docker_env,
            )

            http_json(
                "POST", base_url + "ingest.php", token=WRITE_TOKEN,
                expected=(400,), raw_body=b"{invalid-json",
            )
            http_json("GET", base_url + "status.php?account=DEMO", expected=(401,))

            _, accounts, accounts_raw = http_json("GET", base_url + "accounts.php", token=access_token)
            if not accounts["accounts"][0].get("canControlService"):
                raise AssertionError("service-control pairing permission was not propagated")
            request_id = "c" * 32
            for _ in range(2):
                _, stopped, _ = http_json("POST", base_url + "service-control.php", {
                    "action": "setDesiredState", "requestId": request_id, "accountKey": "DEMO",
                    "role": "EXECUTOR", "desiredRunning": False,
                }, token=access_token)
                if stopped.get("desiredRunning") is not False:
                    raise AssertionError("mobile service stop was not persisted")
            event_count = int(docker_sql(
                docker, container,
                "SELECT COUNT(*) FROM strategy_service_control_events WHERE request_id='" + request_id + "'",
                docker_env,
            ))
            if event_count != 1:
                raise AssertionError("service control request was not idempotent")
            http_json("POST", base_url + "service-control.php", {
                "action": "setDesiredState", "requestId": request_id, "accountKey": "DEMO",
                "role": "EXECUTOR", "desiredRunning": True,
            }, token=access_token, expected=(409,))
            http_json("POST", base_url + "service-control.php", {
                "action": "setDesiredState", "requestId": "e" * 32, "accountKey": "DEMO",
                "role": "EXECUTOR", "desiredRunning": "false",
            }, token=access_token, expected=(400,))
            http_json("POST", base_url + "service-control.php", {
                "action": "setDesiredState", "requestId": "d" * 32, "accountKey": "DEMO",
                "role": "EXECUTOR", "desiredRunning": True,
            }, token=access_token)
            _, service_control, service_control_raw = http_json(
                "GET", base_url + "service-control.php?account=DEMO", token=access_token,
            )
            if not service_control.get("canControl") or service_control.get("master", {}).get("online") is not True:
                raise AssertionError("service-control status did not expose authorized master state")
            _, status, status_raw = http_json("GET", base_url + "status.php?account=DEMO", token=access_token)
            snapshot = status["snapshot"]
            if snapshot["position"]["ticket"] != expected["positionTicket"]:
                raise AssertionError("status position ticket does not match ingested contract")
            assert_close(snapshot["position"]["volume"], expected["positionVolume"], "status position volume")
            assert_close(snapshot["account"]["balance"], expected["balance"], "status balance")
            assert_close(snapshot["account"]["equity"], expected["equity"], "status equity")
            assert_close(snapshot["account"]["deposit"], expected["deposit"], "status deposit")
            if snapshot["strategyDecision"]["decisionId"] != identities["decisionId"]:
                raise AssertionError("status lost the authoritative strategy decision")
            if snapshot["closestCondition"]["name"] != "BE CHECK":
                raise AssertionError("scheduled break-even check is not the closest mobile condition")
            if not any(condition.get("name") == "BE CHECK" for condition in snapshot["conditions"]):
                raise AssertionError("scheduled break-even check is missing from all mobile conditions")
            for label, values in (
                ("currentWeek", (110.0, 112.0, 108.0, 111.0)),
                ("previousWeek", (220.0, 224.0, 216.0, 222.0)),
            ):
                stats = snapshot["marketStats"][label]
                daily_open, daily_high, daily_low, daily_close = values
                assert_close(stats["dailyOpen"], daily_open, f"{label} daily open")
                assert_close(stats["dailyHigh"], daily_high, f"{label} daily high")
                assert_close(stats["dailyLow"], daily_low, f"{label} daily low")
                assert_close(stats["dailyClose"], daily_close, f"{label} daily close")
                assert_close(stats["dailyHighPercent"], (daily_high / daily_open - 1.0) * 100.0, f"{label} daily high change")
                assert_close(stats["dailyLowPercent"], (daily_low / daily_open - 1.0) * 100.0, f"{label} daily low change")
                assert_close(stats["dailyClosePercent"], (daily_close / daily_open - 1.0) * 100.0, f"{label} daily close change")
                if abs(float(stats["dailyHighPercent"]) - float(stats["weeklyHighPercent"])) < 0.01:
                    raise AssertionError(f"{label} latest-day change incorrectly duplicates the weekly change")

            _, receipt, _ = http_json("POST", base_url + "mobile-receipt.php", {
                "accountKey": "DEMO", "executionId": fixture["executionId"],
                "decisionId": identities["decisionId"], "positionTicket": fixture["positionTicket"],
                "receivedAt": iso(datetime.now(timezone.utc)),
                "snapshotGeneratedAt": status["generatedAt"],
            }, token=access_token)
            if receipt.get("latencyMs") is None:
                raise AssertionError("mobile receipt did not calculate delivery latency")

            seed_analytics_fixture(
                docker, container, fixture["accountKey"], fixture["analytics"],
                current_monday, docker_env,
            )
            _, analytics, analytics_raw = http_json(
                "GET", base_url + "analytics.php?account=DEMO&rolling_weeks=2", token=access_token,
            )
            summary = analytics["summary"]
            for key in (
                "averageWeeklyPreleverageReturnPercent", "averageWeeklyLeveragedReturnPercent",
                "averageWinPreleverageReturnPercent", "averageWinLeveragedReturnPercent",
                "averageLossPreleverageReturnPercent", "averageLossLeveragedReturnPercent",
                "calmarRatio", "omegaRatio", "ulcerIndexPercent", "valueAtRisk95Percent",
                "expectedShortfall95Percent",
            ):
                assert_close(summary[key], float(expected[key]), "analytics " + key)
            if int(summary["riskSampleDays"]) != int(expected["riskSampleDays"]):
                raise AssertionError(
                    f"analytics riskSampleDays: expected {expected['riskSampleDays']}, got {summary['riskSampleDays']}"
                )
            class_values = {item["tradeClass"]: item for item in analytics["tradeClasses"]}
            for trade_class, expected_return in expected["classAveragePreleverageReturnPercent"].items():
                assert_close(
                    class_values[trade_class]["averagePreleverageReturnPercent"],
                    float(expected_return), f"analytics class {trade_class} average pre-leverage return",
                )
            quality = analytics["executionQuality"]
            if quality["decisionToSend"]["sampleCount"] != 1:
                raise AssertionError("analytics did not reconstruct the execution lifecycle")
            assert_close(quality["decisionToSend"]["medianMs"], expected["decisionToSendMs"], "decision-to-send")
            assert_close(quality["brokerAcknowledgement"]["medianMs"], expected["brokerAcknowledgementMs"], "acknowledgement")
            assert_close(quality["fill"]["medianMs"], expected["fillMs"], "fill latency")
            assert_close(quality["protectionAttachment"]["medianMs"], expected["protectionAttachmentMs"], "protection latency")
            assert_close(quality["backendPublication"]["medianMs"], expected["backendPublicationMs"], "publication latency")
            if quality["executorToMobile"]["sampleCount"] != 1:
                raise AssertionError("analytics did not include the mobile receipt")

            counts = {
                "strategySpecifications": int(docker_sql(docker, container, "SELECT COUNT(*) FROM strategy_specifications", docker_env)),
                "strategyDecisions": int(docker_sql(docker, container, "SELECT COUNT(*) FROM strategy_decisions", docker_env)),
                "authorityStages": int(docker_sql(docker, container, "SELECT COUNT(*) FROM strategy_execution_stages", docker_env)),
                "authorityFills": int(docker_sql(docker, container, "SELECT COUNT(*) FROM strategy_fills", docker_env)),
            }
            for key in ("strategySpecifications", "strategyDecisions", "authorityFills"):
                if counts[key] != int(expected[key]):
                    raise AssertionError(f"{key}: expected {expected[key]}, got {counts[key]}")
            if counts["authorityStages"] != int(expected["authorityStages"]):
                raise AssertionError(
                    "authority stage delivery was not idempotent: "
                    f"expected {expected['authorityStages']}, got {counts['authorityStages']}"
                )

            output = temp / "responses"
            output.mkdir()
            (output / "accounts.json").write_text(accounts_raw, encoding="utf-8")
            (output / "status.json").write_text(status_raw, encoding="utf-8")
            (output / "analytics.json").write_text(analytics_raw, encoding="utf-8")
            (output / "service-control.json").write_text(service_control_raw, encoding="utf-8")
            android_env = os.environ.copy()
            android_env["OPPW_CONTRACT_OUTPUT_DIR"] = str(output)
            if os.name == "nt":
                gradle = ["cmd.exe", "/d", "/c", "gradlew.bat"]
            else:
                gradle = ["./gradlew"]
            run(
                gradle + ["--no-daemon", "testDebugUnitTest", "--tests", "com.oppw.monitor.data.ContractResponseParserTest"],
                cwd=root / "Mobile", env=android_env,
            )
            print(
                "CONTRACT VALIDATION PASSED "
                f"account={expected['accountKey']} stages={counts['authorityStages']} "
                f"fills={counts['authorityFills']} decision={identities['decisionId']}"
            )
            return 0
        except Exception:
            if php_stderr.is_file():
                server_error = php_stderr.read_text(encoding="utf-8", errors="replace").strip()
                if server_error:
                    print("PHP CONTRACT SERVER LOG:\n" + server_error[-4000:], file=sys.stderr)
            raise
        finally:
            if php_process is not None:
                php_process.terminate()
                try:
                    php_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    php_process.kill()
            if stdout_handle is not None:
                stdout_handle.close()
            if stderr_handle is not None:
                stderr_handle.close()
            subprocess.run(
                [docker, "rm", "--force", container], env=docker_env,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"CONTRACT VALIDATION FAILED: {error}", file=sys.stderr)
        raise SystemExit(1)
