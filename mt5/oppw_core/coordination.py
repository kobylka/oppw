"""Global MySQL lease, fencing, trade-gate, and weekly-entry coordination."""

from __future__ import annotations

import json
import logging
import os
import socket
import sys
import threading
import time as time_module
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from typing import Any, Optional

from .versioning import BUILD_ID, INSTANCE_MODE_EXECUTOR, INSTANCE_MODE_PUBLISHER

class CoordinationError(RuntimeError):
    pass


class LeaseLostError(CoordinationError):
    pass


@dataclass(frozen=True)
class TradeExecutionGate:
    owner_id: str
    fencing_token: int
    operation_id: str
    operation_kind: str
    acquired_monotonic: float
    ttl_seconds: float


class BackendLeaseCoordinator:
    """Global MySQL-backed leadership, fencing, and trade idempotency client."""

    def __init__(self, config, role: str, account: str):
        self.cfg = config
        self.role = role
        self.account = account.upper()
        self.owner_id = uuid.uuid4().hex
        self.hostname = socket.gethostname()[:120]
        self.pid = os.getpid()
        self.fencing_token = 0
        self.valid_until_monotonic = 0.0
        self.stop_event = threading.Event()
        self.lease_lost_event = threading.Event()
        self.thread: Optional[threading.Thread] = None
        self.logger: Optional[logging.Logger] = None
        self.last_publisher_check_monotonic = 0.0
        self.cached_publisher_active = False
        self.last_error_log_monotonic = 0.0

    def set_logger(self, logger: logging.Logger) -> None:
        self.logger = logger

    def log(self, level: int, message: str, *args: Any) -> None:
        if self.logger is not None:
            self.logger.log(level, message, *args, extra={"skip_mobile_publish": True})
        else:
            rendered = message % args if args else message
            print(rendered, file=sys.stderr if level >= logging.ERROR else sys.stdout, flush=True)

    def _request(self, action: str, **values: Any) -> dict[str, Any]:
        payload = {
            "action": action,
            "accountKey": self.cfg.monitor_account_key,
            "role": self.role,
            "ownerId": self.owner_id,
            "hostname": self.hostname,
            "pid": self.pid,
            "build": BUILD_ID,
            **values,
        }
        body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            self.cfg.coordination_url,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.cfg.monitor_write_token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": f"OPPW-MT5-Coordination/{BUILD_ID}",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=float(self.cfg.coordination_timeout_seconds)) as response:
                response_text = response.read().decode("utf-8", errors="replace")
                if int(response.status) not in (200, 201):
                    raise CoordinationError(f"coordination HTTP {response.status}")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise CoordinationError(f"coordination HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise CoordinationError(f"coordination connection failed: {exc.reason}") from exc
        try:
            decoded = json.loads(response_text) if response_text.strip() else {}
        except json.JSONDecodeError as exc:
            raise CoordinationError(f"coordination response was not JSON: {response_text[:200]}") from exc
        if not isinstance(decoded, dict) or not bool(decoded.get("ok", False)):
            raise CoordinationError(str(decoded.get("error", "coordination request failed")) if isinstance(decoded, dict) else "coordination request failed")
        return decoded

    def start(self) -> None:
        if not self.cfg.monitor_write_token or not str(self.cfg.coordination_url).lower().startswith("https://"):
            raise CoordinationError("Global coordination requires monitor_write_token and an HTTPS coordination_url")
        result = self._request(
            "acquireLease",
            leaseName=self.role,
            ttlSeconds=float(self.cfg.role_lease_ttl_seconds),
        )
        if not bool(result.get("acquired", False)):
            holder = result.get("holder") if isinstance(result.get("holder"), dict) else {}
            raise CoordinationError(
                f"Global {self.role} lease is already held for {self.account}: "
                f"owner={holder.get('ownerId', 'unknown')} host={holder.get('hostname', 'unknown')} "
                f"pid={holder.get('pid', 'unknown')} expiresAt={holder.get('expiresAt', 'unknown')}"
            )
        self._activate_acquired_lease(result)
        self.log(
            logging.INFO,
            "EVENT GLOBAL_LEASE_ACQUIRED role=%s account=%s owner_id=%s fencing_token=%s host=%s pid=%s",
            self.role, self.account, self.owner_id, self.fencing_token, self.hostname, self.pid,
        )

    def _activate_acquired_lease(self, result: dict[str, Any]) -> None:
        fencing_token = int(result.get("fencingToken", 0) or 0)
        if fencing_token <= 0:
            raise CoordinationError("Backend returned an invalid role fencing token")
        self.fencing_token = fencing_token
        self.valid_until_monotonic = time_module.monotonic() + float(
            result.get("ttlSeconds", self.cfg.role_lease_ttl_seconds)
        )
        self.lease_lost_event.clear()
        self.thread = threading.Thread(
            target=self._renew_worker,
            name=f"oppw-{self.role.lower()}-lease",
            daemon=True,
        )
        self.thread.start()

    def _mark_role_lease_lost(self, error: Exception) -> None:
        if self.lease_lost_event.is_set():
            return
        self.lease_lost_event.set()
        self.log(
            logging.CRITICAL,
            "EVENT GLOBAL_LEASE_LOST role=%s account=%s owner_id=%s fencing_token=%s error=%s",
            self.role, self.account, self.owner_id, self.fencing_token, error,
        )

    def _renew_worker(self) -> None:
        interval = max(0.25, float(self.cfg.role_lease_heartbeat_seconds))
        retry_interval = max(0.10, min(0.50, interval / 4.0))
        next_delay = interval
        while not self.stop_event.wait(next_delay):
            next_delay = interval
            try:
                result = self._request(
                    "renewLease",
                    leaseName=self.role,
                    fencingToken=self.fencing_token,
                    ttlSeconds=float(self.cfg.role_lease_ttl_seconds),
                )
                if not bool(result.get("renewed", False)):
                    raise LeaseLostError("backend rejected role lease renewal")
                returned_token = int(result.get("fencingToken", 0) or 0)
                if returned_token != self.fencing_token:
                    raise LeaseLostError(
                        f"role fencing token changed from {self.fencing_token} to {returned_token}"
                    )
                self.valid_until_monotonic = time_module.monotonic() + float(
                    result.get("ttlSeconds", self.cfg.role_lease_ttl_seconds)
                )
            except LeaseLostError as exc:
                # An explicit backend rejection or changed fencing token is
                # authoritative and must stop role activity immediately.
                self._mark_role_lease_lost(exc)
                return
            except Exception as exc:
                now = time_module.monotonic()
                if now >= self.valid_until_monotonic - float(self.cfg.role_lease_safety_margin_seconds):
                    self._mark_role_lease_lost(exc)
                    return
                # Retry quickly after a transport timeout. Waiting another
                # complete heartbeat here can consume the remaining TTL even
                # when the backend has already recovered.
                next_delay = retry_interval
                if now - self.last_error_log_monotonic >= max(1.0, interval):
                    self.last_error_log_monotonic = now
                    remaining = max(
                        0.0,
                        self.valid_until_monotonic
                        - float(self.cfg.role_lease_safety_margin_seconds)
                        - now,
                    )
                    self.log(
                        logging.WARNING,
                        "EVENT GLOBAL_LEASE_RENEW_DEFERRED role=%s account=%s fencing_token=%s "
                        "retry_in=%.2fs safe_for=%.2fs error=%s",
                        self.role, self.account, self.fencing_token, next_delay, remaining, exc,
                    )

    def recover_role_lease(self, retry_seconds: float) -> bool:
        """Suspend role work and reacquire global ownership without local locks."""
        retry_delay = max(0.50, float(retry_seconds))
        last_log = 0.0
        while not self.stop_event.is_set():
            if self.role_lease_valid():
                return True

            # A renewal request may still be in flight when the main loop
            # reaches the safety boundary. Let it finish before attempting a
            # second acquisition from this process.
            if self.thread is not None and self.thread.is_alive():
                self.thread.join(timeout=min(0.25, retry_delay))
                continue
            self.thread = None

            try:
                result = self._request(
                    "acquireLease",
                    leaseName=self.role,
                    ttlSeconds=float(self.cfg.role_lease_ttl_seconds),
                )
                if bool(result.get("acquired", False)):
                    old_token = self.fencing_token
                    self._activate_acquired_lease(result)
                    self.log(
                        logging.INFO,
                        "EVENT GLOBAL_LEASE_REACQUIRED role=%s account=%s owner_id=%s "
                        "old_fencing_token=%s fencing_token=%s",
                        self.role, self.account, self.owner_id, old_token, self.fencing_token,
                    )
                    return True
                holder = result.get("holder") if isinstance(result.get("holder"), dict) else {}
                detail = (
                    f"held by owner={holder.get('ownerId', 'unknown')} "
                    f"host={holder.get('hostname', 'unknown')} pid={holder.get('pid', 'unknown')} "
                    f"expiresAt={holder.get('expiresAt', 'unknown')}"
                )
            except Exception as exc:
                detail = str(exc)

            now = time_module.monotonic()
            if now - last_log >= max(5.0, retry_delay):
                last_log = now
                self.log(
                    logging.WARNING,
                    "EVENT GLOBAL_LEASE_REACQUIRE_WAIT role=%s account=%s retry_in=%.2fs reason=%s",
                    self.role, self.account, retry_delay, detail,
                )
            if self.stop_event.wait(retry_delay):
                break
        return False

    def stop(self) -> None:
        self.stop_event.set()
        if self.thread is not None:
            self.thread.join(timeout=max(1.0, float(self.cfg.coordination_timeout_seconds) + 1.0))
            self.thread = None
        if self.fencing_token > 0:
            try:
                self._request("releaseLease", leaseName=self.role, fencingToken=self.fencing_token)
            except Exception:
                pass

    def role_lease_valid(self) -> bool:
        return (
            self.fencing_token > 0
            and not self.lease_lost_event.is_set()
            and time_module.monotonic()
            < self.valid_until_monotonic - float(self.cfg.role_lease_safety_margin_seconds)
        )

    def require_role_lease(self) -> None:
        if not self.role_lease_valid():
            raise LeaseLostError(
                f"Global {self.role} lease is not valid for {self.account}; all role activity is disabled"
            )

    def actor_payload(self) -> dict[str, Any]:
        self.require_role_lease()
        return {
            "role": self.role,
            "ownerId": self.owner_id,
            "fencingToken": self.fencing_token,
        }

    def dedicated_publisher_active(self, force: bool = False) -> bool:
        if self.role == INSTANCE_MODE_PUBLISHER:
            return self.role_lease_valid()
        now = time_module.monotonic()
        if not force and now - self.last_publisher_check_monotonic < float(self.cfg.publisher_presence_check_interval_seconds):
            return self.cached_publisher_active
        self.last_publisher_check_monotonic = now
        try:
            result = self._request("leaseStatus", leaseName=INSTANCE_MODE_PUBLISHER)
            self.cached_publisher_active = bool(result.get("active", False))
        except Exception as exc:
            # Fail closed for snapshot publication while the global state is unknown.
            self.cached_publisher_active = True
            if now - self.last_error_log_monotonic >= max(1.0, float(self.cfg.monitor_error_log_interval_seconds)):
                self.last_error_log_monotonic = now
                self.log(logging.WARNING, "EVENT PUBLISHER_LEASE_STATUS_UNKNOWN account=%s error=%s", self.account, exc)
        return self.cached_publisher_active

    def acquire_trade_gate(self, operation_kind: str, operation_id: str) -> TradeExecutionGate:
        if self.role != INSTANCE_MODE_EXECUTOR:
            raise LeaseLostError("Only the EXECUTOR role may acquire the global trade-execution gate")
        self.require_role_lease()
        result = self._request(
            "acquireTradeGate",
            executorFencingToken=self.fencing_token,
            operationKind=operation_kind,
            operationId=operation_id,
            ttlSeconds=float(self.cfg.trade_gate_ttl_seconds),
        )
        if not bool(result.get("acquired", False)):
            holder = result.get("holder") if isinstance(result.get("holder"), dict) else {}
            raise CoordinationError(
                f"Global trade gate is busy: owner={holder.get('ownerId', 'unknown')} "
                f"operation={holder.get('operationKind', 'unknown')} expiresAt={holder.get('expiresAt', 'unknown')}"
            )
        gate_token = int(result.get("fencingToken", 0) or 0)
        if gate_token <= 0:
            raise CoordinationError("Backend returned an invalid trade-gate fencing token")
        return TradeExecutionGate(
            owner_id=self.owner_id,
            fencing_token=gate_token,
            operation_id=operation_id,
            operation_kind=operation_kind,
            acquired_monotonic=time_module.monotonic(),
            ttl_seconds=float(result.get("ttlSeconds", self.cfg.trade_gate_ttl_seconds)),
        )

    def validate_trade_gate(self, gate: TradeExecutionGate) -> None:
        self.require_role_lease()
        held = time_module.monotonic() - gate.acquired_monotonic
        if held > min(gate.ttl_seconds, float(self.cfg.trade_gate_max_hold_seconds)):
            raise LeaseLostError(
                f"Trade gate for {gate.operation_kind} exceeded its safe local hold time ({held:.3f}s)"
            )
        result = self._request(
            "validateTradeGate",
            executorFencingToken=self.fencing_token,
            gateFencingToken=gate.fencing_token,
            operationKind=gate.operation_kind,
            operationId=gate.operation_id,
        )
        if not bool(result.get("valid", False)):
            raise LeaseLostError(f"Global trade gate is no longer valid for {gate.operation_kind}")

    def release_trade_gate(self, gate: TradeExecutionGate) -> None:
        try:
            self._request(
                "releaseTradeGate",
                executorFencingToken=self.fencing_token,
                gateFencingToken=gate.fencing_token,
                operationKind=gate.operation_kind,
                operationId=gate.operation_id,
            )
        except Exception as exc:
            self.log(
                logging.WARNING,
                "EVENT TRADE_GATE_RELEASE_DEFERRED operation=%s operation_id=%s error=%s",
                gate.operation_kind, gate.operation_id, exc,
            )

    def claim_weekly_entry(self, week_key: str, execution_id: str, decision_id: str, gate: TradeExecutionGate) -> dict[str, Any]:
        self.validate_trade_gate(gate)
        return self._request(
            "claimWeeklyEntry",
            executorFencingToken=self.fencing_token,
            gateFencingToken=gate.fencing_token,
            gateOperationId=gate.operation_id,
            weekKey=week_key,
            executionId=execution_id,
            decisionId=decision_id,
        )

    def complete_weekly_entry(
        self,
        week_key: str,
        execution_id: str,
        status: str,
        result: Any = None,
        error: str = "",
    ) -> None:
        try:
            self._request(
                "completeWeeklyEntry",
                executorFencingToken=self.fencing_token,
                weekKey=week_key,
                executionId=execution_id,
                status=status,
                orderTicket=int(getattr(result, "order", 0) or 0) if result is not None else 0,
                dealTicket=int(getattr(result, "deal", 0) or 0) if result is not None else 0,
                retcode=int(getattr(result, "retcode", -1)) if result is not None else -1,
                error=error[:500],
            )
        except Exception as exc:
            self.log(
                logging.CRITICAL,
                "EVENT WEEKLY_ENTRY_RESULT_PERSIST_FAILED week=%s execution_id=%s status=%s error=%s",
                week_key, execution_id, status, exc,
            )
