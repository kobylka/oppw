"""Fail-safe supervisor for the four canonical OPPW MT5 process roles."""

from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ACCOUNTS = ("DEMO", "REAL")
ROLES = ("EXECUTOR", "PUBLISHER")
STARTUP_ORDER = (
    ("DEMO", "EXECUTOR"),
    ("REAL", "EXECUTOR"),
    ("DEMO", "PUBLISHER"),
    ("REAL", "PUBLISHER"),
)


def assignments_fresh(last_assignment_at: float, ttl_seconds: float, now: float | None = None) -> bool:
    current = time.monotonic() if now is None else now
    return last_assignment_at > 0 and current - last_assignment_at < ttl_seconds


def next_start_key(
    assignments: dict[tuple[str, str], bool],
    states: dict[tuple[str, str], tuple[bool, bool]],
    eligible: dict[tuple[str, str], bool] | None = None,
) -> tuple[str, str] | None:
    for key in STARTUP_ORDER:
        if assignments.get(key, False) and states[key] == (True, False):
            return None
    for key in STARTUP_ORDER:
        if not assignments.get(key, False):
            continue
        running, ready = states[key]
        if not running and (eligible is None or eligible.get(key, False)):
            return key
    return None


def utc_text() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_config(path: Path) -> dict[str, Any]:
    values = json.loads(path.read_text(encoding="utf-8"))
    required = ("nodeId", "nodeRole", "repoRoot", "pythonPath", "controlUrl", "writeToken")
    missing = [name for name in required if not str(values.get(name, "")).strip()]
    if missing:
        raise RuntimeError("Supervisor configuration is missing: " + ", ".join(missing))
    values["nodeId"] = str(values["nodeId"]).strip().lower()
    values["nodeRole"] = str(values["nodeRole"]).strip().upper()
    if len(values["nodeId"]) != 32 or any(ch not in "0123456789abcdef" for ch in values["nodeId"]):
        raise RuntimeError("nodeId must contain 32 lowercase hexadecimal characters")
    if values["nodeRole"] not in ("MASTER", "BACKUP"):
        raise RuntimeError("nodeRole must be MASTER or BACKUP")
    if not str(values["controlUrl"]).lower().startswith("https://"):
        raise RuntimeError("controlUrl must use HTTPS")
    return values


@dataclass
class ManagedProcess:
    account: str
    role: str
    stop_file: Path
    ready_file: Path
    process: subprocess.Popen[bytes] | None = None
    output: Any = None
    started_at: str = ""
    restart_count: int = 0
    last_exit_code: int | None = None
    last_start_monotonic: float = 0.0
    next_start_monotonic: float = 0.0
    startup_failed: bool = False
    ready_reported: bool = False

    def refresh(self) -> None:
        if self.process is None:
            return
        code = self.process.poll()
        if code is None:
            return
        self.last_exit_code = code
        if not self.ready_file.is_file():
            self.startup_failed = True
        self.process = None
        if self.output is not None:
            self.output.close()
            self.output = None

    def status(self) -> dict[str, Any]:
        self.refresh()
        return {
            "account": self.account,
            "role": self.role,
            "running": self.process is not None,
            "pid": self.process.pid if self.process is not None else 0,
            "startedAt": self.started_at,
            "restartCount": self.restart_count,
            "lastExitCode": self.last_exit_code,
        }


class Supervisor:
    def __init__(self, config_path: Path):
        self.config_path = config_path.resolve()
        self.cfg = load_config(self.config_path)
        self.root = Path(str(self.cfg["repoRoot"])).resolve()
        self.python = Path(str(self.cfg["pythonPath"])).resolve()
        self.entrypoint = self.root / "mt5" / "oppw_mt5_continuous.py"
        self.version = (self.root / "VERSION").read_text(encoding="utf-8").strip()
        self.build = "oppw-" + self.version
        if not self.python.is_file() or not self.entrypoint.is_file():
            raise RuntimeError("pythonPath or canonical MT5 entrypoint does not exist")
        self.runtime_dir = Path(str(self.cfg.get("runtimeDir") or self.config_path.parent / "runtime"))
        self.log_dir = Path(str(self.cfg.get("logDir") or self.config_path.parent / "logs"))
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.service_stop_file = Path(str(self.cfg.get("serviceStopFile") or (str(self.config_path) + ".stop")))
        self.poll_seconds = max(1.0, min(15.0, float(self.cfg.get("pollSeconds", 3.0))))
        self.assignment_ttl = max(5.0, min(60.0, float(self.cfg.get("assignmentTtlSeconds", 15.0))))
        self.stop_grace = max(3.0, min(60.0, float(self.cfg.get("stopGraceSeconds", 15.0))))
        self.restart_delay = max(1.0, min(30.0, float(self.cfg.get("restartDelaySeconds", 5.0))))
        self.startup_ready_timeout = max(
            30.0, min(180.0, float(self.cfg.get("startupReadyTimeoutSeconds", 90.0)))
        )
        self.startup_failure_backoff = max(
            15.0, min(300.0, float(self.cfg.get("startupFailureBackoffSeconds", 60.0)))
        )
        self.started_at = utc_text()
        self.shutdown = threading.Event()
        self.last_assignment_at = 0.0
        self.assignments: dict[tuple[str, str], bool] = {}
        self.processes = {
            (account, role): ManagedProcess(
                account,
                role,
                self.runtime_dir / f"stop-{account.lower()}-{role.lower()}.signal",
                self.runtime_dir / f"ready-{account.lower()}-{role.lower()}.json",
            )
            for account in ACCOUNTS for role in ROLES
        }

    def log(self, message: str) -> None:
        rendered = f"{utc_text()} {message}"
        print(rendered, flush=True)
        with (self.log_dir / "supervisor.log").open("a", encoding="utf-8") as handle:
            handle.write(rendered + "\n")

    def heartbeat(self) -> dict[tuple[str, str], bool]:
        payload = {
            "action": "heartbeat",
            "nodeId": self.cfg["nodeId"],
            "nodeRole": self.cfg["nodeRole"],
            "hostname": socket.gethostname()[:120],
            "pid": os.getpid(),
            "build": self.build,
            "startedAt": self.started_at,
            "processes": [item.status() for item in self.processes.values()],
        }
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        request = urllib.request.Request(
            str(self.cfg["controlUrl"]), data=body, method="POST",
            headers={
                "Authorization": "Bearer " + str(self.cfg["writeToken"]),
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "OPPW-Windows-Supervisor/" + self.build,
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=float(self.cfg.get("requestTimeoutSeconds", 8.0))) as response:
                decoded = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
            raise RuntimeError(f"control HTTP {exc.code}: {detail}") from exc
        if not isinstance(decoded, dict) or not decoded.get("ok"):
            raise RuntimeError(str(decoded.get("error", "invalid control response")))
        result: dict[tuple[str, str], bool] = {}
        for assignment in decoded.get("assignments", []):
            account = str(assignment.get("account", "")).upper()
            role = str(assignment.get("role", "")).upper()
            if account in ACCOUNTS and role in ROLES:
                result[(account, role)] = bool(assignment.get("assigned", False))
        if set(result) != set(self.processes):
            raise RuntimeError("control response did not assign all four managed roles")
        return result

    def start_process(self, item: ManagedProcess) -> None:
        now = time.monotonic()
        if now - item.last_start_monotonic < self.restart_delay:
            return
        if now < item.next_start_monotonic:
            return
        item.stop_file.unlink(missing_ok=True)
        item.ready_file.unlink(missing_ok=True)
        item.ready_reported = False
        output_path = self.log_dir / f"{item.account.lower()}-{item.role.lower()}.console.log"
        item.output = output_path.open("ab", buffering=0)
        command = [
            str(self.python), str(self.entrypoint), "--account", item.account.lower(),
            "--mode", item.role.lower(), "--service-stop-file", str(item.stop_file),
            "--service-ready-file", str(item.ready_file),
        ]
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            item.process = subprocess.Popen(
                command, cwd=str(self.root), stdin=subprocess.DEVNULL,
                stdout=item.output, stderr=subprocess.STDOUT, creationflags=creation_flags,
            )
        except Exception:
            item.output.close()
            item.output = None
            raise
        item.started_at = utc_text()
        item.restart_count += 1
        item.last_start_monotonic = now
        self.log(f"PROCESS_STARTED account={item.account} role={item.role} pid={item.process.pid}")

    def stop_process(self, item: ManagedProcess) -> None:
        item.refresh()
        if item.process is None:
            item.stop_file.unlink(missing_ok=True)
            item.ready_file.unlink(missing_ok=True)
            item.ready_reported = False
            return
        item.stop_file.write_text(utc_text(), encoding="utf-8")
        deadline = time.monotonic() + self.stop_grace
        while item.process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.2)
        if item.process.poll() is None:
            item.process.terminate()
            try:
                item.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                item.process.kill()
                item.process.wait(timeout=5)
        self.log(f"PROCESS_STOPPED account={item.account} role={item.role} exit={item.process.returncode}")
        item.refresh()
        item.stop_file.unlink(missing_ok=True)
        item.ready_file.unlink(missing_ok=True)
        item.ready_reported = False

    def reconcile(self, allow_start: bool) -> None:
        now = time.monotonic()
        for item in self.processes.values():
            item.refresh()
            if item.startup_failed:
                item.startup_failed = False
                item.next_start_monotonic = max(
                    item.next_start_monotonic, now + self.startup_failure_backoff
                )
                self.log(
                    f"PROCESS_START_FAILED account={item.account} role={item.role} "
                    f"exit={item.last_exit_code} retryIn={self.startup_failure_backoff:.0f}s"
                )
            if item.process is not None and item.ready_file.is_file() and not item.ready_reported:
                item.ready_reported = True
                self.log(f"PROCESS_READY account={item.account} role={item.role} pid={item.process.pid}")
            if (
                item.process is not None
                and not item.ready_file.is_file()
                and now - item.last_start_monotonic >= self.startup_ready_timeout
            ):
                self.log(
                    f"PROCESS_READY_TIMEOUT account={item.account} role={item.role} "
                    f"timeout={self.startup_ready_timeout:.0f}s"
                )
                self.stop_process(item)
                item.next_start_monotonic = now + self.startup_failure_backoff
        for key, item in self.processes.items():
            should_run = allow_start and self.assignments.get(key, False)
            if not should_run and item.process is not None:
                self.stop_process(item)
        if not allow_start:
            return
        states = {
            key: (item.process is not None, item.ready_file.is_file())
            for key, item in self.processes.items()
        }
        eligible = {
            key: now >= item.next_start_monotonic
            for key, item in self.processes.items()
        }
        key_to_start = next_start_key(self.assignments, states, eligible)
        if key_to_start is not None:
            self.start_process(self.processes[key_to_start])

    def stop_all(self) -> None:
        for item in self.processes.values():
            self.stop_process(item)

    def run(self) -> int:
        self.service_stop_file.unlink(missing_ok=True)
        self.log(f"SUPERVISOR_STARTED nodeRole={self.cfg['nodeRole']} nodeId={self.cfg['nodeId']} build={self.build}")
        while not self.shutdown.is_set() and not self.service_stop_file.exists():
            try:
                self.assignments = self.heartbeat()
                self.last_assignment_at = time.monotonic()
                self.reconcile(allow_start=True)
            except Exception as exc:
                self.log(f"CONTROL_UNAVAILABLE error={exc}")
                valid = assignments_fresh(self.last_assignment_at, self.assignment_ttl)
                self.reconcile(allow_start=valid)
            self.shutdown.wait(self.poll_seconds)
        self.stop_all()
        self.log("SUPERVISOR_STOPPED")
        return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="OPPW Windows process supervisor")
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args(argv)
    supervisor = Supervisor(args.config)
    for name in ("SIGINT", "SIGTERM", "SIGBREAK"):
        value = getattr(signal, name, None)
        if value is not None:
            signal.signal(value, lambda *_: supervisor.shutdown.set())
    return supervisor.run()


if __name__ == "__main__":
    raise SystemExit(main())
