"""Non-blocking mobile snapshot and diagnostic-event publication."""

from __future__ import annotations

import json
import logging
import os
import shlex
import threading
import time as time_module
import urllib.error
import urllib.request
import uuid
from collections import deque
from datetime import UTC, datetime
from typing import Any, Optional
from zoneinfo import ZoneInfo

from .coordination import BackendLeaseCoordinator
from .versioning import BUILD_ID, INSTANCE_MODE_PUBLISHER

SNAPSHOT_EQUITY_HISTORY_FALLBACK_POINTS = 144


class MobileMonitorPublisher:
    """Asynchronous publisher coordinated exclusively by global MySQL leases."""

    def __init__(self, config, logger: logging.Logger, timezone: ZoneInfo, role: str, coordinator: BackendLeaseCoordinator):
        self.cfg = config
        self.log = logger
        self.timezone = timezone
        self.role = role
        self.coordinator = coordinator
        self.enabled = bool(config.monitor_enabled)
        self.ready = self.enabled and bool(
            config.monitor_ingest_url
            and config.events_ingest_url
            and config.monitor_write_token
            and config.monitor_account_key
        )
        self.condition = threading.Condition()
        self.guaranteed_snapshots: deque[dict[str, Any]] = deque(
            maxlen=max(1, config.monitor_minute_snapshot_buffer_size)
        )
        self.latest_snapshot: Optional[dict[str, Any]] = None
        self.events: deque[dict[str, Any]] = deque(maxlen=max(1, config.monitor_event_buffer_size))
        self.publish_requested = False
        self.stopping = False
        self.thread: Optional[threading.Thread] = None
        self.last_error_log_monotonic = 0.0
        self.last_success_utc = ""
        self.equity_history = self.load_equity_history()
        self.last_publish_permission: Optional[bool] = None
        self.weekend_idle = False
        self.published_execution_ids: set[str] = set()
        self.acknowledged_strategy_decision_ids: set[str] = set()
        self.acknowledged_strategy_decision_order: deque[str] = deque()
        self.acknowledged_strategy_decision_limit = 256
        self.acknowledged_strategy_specification_ids: set[str] = set()
        self.canonical_strategy_specification: Optional[dict[str, Any]] = None

        if self.enabled and not self.ready:
            self.local_log(
                logging.WARNING,
                "EVENT MONITOR_DISABLED reason=missing_configuration "
                "required=OPPW_MONITOR_INGEST_URL,OPPW_EVENTS_INGEST_URL,"
                "OPPW_MONITOR_WRITE_TOKEN,OPPW_MONITOR_ACCOUNT_KEY",
            )
        elif self.ready and (
            not config.monitor_ingest_url.lower().startswith("https://")
            or not config.events_ingest_url.lower().startswith("https://")
        ):
            self.ready = False
            self.local_log(logging.ERROR, "EVENT MONITOR_DISABLED reason=endpoints_must_use_https")

    def local_log(self, level: int, message: str, *args: Any) -> None:
        self.log.log(level, message, *args, extra={"skip_mobile_publish": True})

    def allowed_to_publish(self) -> bool:
        if not self.coordinator.role_lease_valid():
            allowed = False
            reason = "role_lease_invalid"
        else:
            dedicated_active = self.coordinator.dedicated_publisher_active()
            allowed = self.role == INSTANCE_MODE_PUBLISHER or not dedicated_active
            reason = "dedicated_publisher" if dedicated_active else "executor_fallback"
        if self.last_publish_permission is None or self.last_publish_permission != allowed:
            self.last_publish_permission = allowed
            self.local_log(
                logging.INFO,
                "EVENT BACKEND_PUBLISHING_STATE role=%s active=%s reason=%s fencing_token=%s",
                self.role, allowed, reason, self.coordinator.fencing_token,
            )
        return allowed

    def load_equity_history(self) -> list[dict[str, Any]]:
        try:
            if not self.cfg.monitor_history_file.exists():
                return []
            raw = json.loads(self.cfg.monitor_history_file.read_text(encoding="utf-8"))
            if not isinstance(raw, list):
                return []
            result: list[dict[str, Any]] = []
            for item in raw[-max(1, self.cfg.monitor_equity_history_points):]:
                if (
                    isinstance(item, dict)
                    and isinstance(item.get("time"), str)
                    and isinstance(item.get("value"), (int, float))
                ):
                    result.append({"time": item["time"], "value": float(item["value"])})
            return result
        except Exception:
            return []

    def save_equity_history(self) -> None:
        try:
            path = self.cfg.monitor_history_file
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
            temporary.write_text(
                json.dumps(self.equity_history, separators=(",", ":")),
                encoding="utf-8",
            )
            os.replace(temporary, path)
        except Exception as exc:
            self.rate_limited_error("EVENT MONITOR_HISTORY_SAVE_FAILED error=%s", exc)

    def set_weekend_idle(self, active: bool) -> None:
        with self.condition:
            self.weekend_idle = bool(active)
            if self.weekend_idle:
                self.guaranteed_snapshots = deque(
                    (
                        snapshot
                        for snapshot in self.guaranteed_snapshots
                        if str(snapshot.get("statusUpdate", {}).get("kind", ""))
                        in {"WEEKEND_STARTUP", "ACCOUNT_FUNDING_CHANGE"}
                    ),
                    maxlen=max(1, self.cfg.monitor_minute_snapshot_buffer_size),
                )
                if (
                    self.latest_snapshot is not None
                    and str(self.latest_snapshot.get("statusUpdate", {}).get("kind", ""))
                    not in {"WEEKEND_STARTUP", "ACCOUNT_FUNDING_CHANGE"}
                ):
                    self.latest_snapshot = None
            self.publish_requested = bool(
                self.guaranteed_snapshots or self.latest_snapshot is not None or self.events
            )
            self.condition.notify_all()

    def start(self) -> None:
        with self.condition:
            if not self.ready or self.stopping:
                return
            if self.thread is not None and self.thread.is_alive():
                return
            restarting = self.thread is not None
            worker = threading.Thread(
                target=self.worker,
                name=f"oppw-monitor-{self.role.lower()}",
                daemon=True,
            )
            self.thread = worker
            worker.start()
        if restarting:
            self.local_log(
                logging.WARNING,
                "EVENT MONITOR_PUBLISHER_RESTARTED role=%s account_key=%s interval=%.1fs endpoint=%s "
                "coordination=mysql fencing_token=%s",
                self.role,
                self.cfg.monitor_account_key,
                self.cfg.monitor_publish_interval_seconds,
                self.cfg.monitor_ingest_url,
                self.coordinator.fencing_token,
            )
        else:
            self.local_log(
                logging.INFO,
                "EVENT MONITOR_PUBLISHER_STARTED role=%s account_key=%s interval=%.1fs endpoint=%s "
                "coordination=mysql fencing_token=%s",
                self.role,
                self.cfg.monitor_account_key,
                self.cfg.monitor_publish_interval_seconds,
                self.cfg.monitor_ingest_url,
                self.coordinator.fencing_token,
            )

    def stop(self) -> None:
        if self.thread is None:
            return
        with self.condition:
            self.stopping = True
            self.publish_requested = bool(
                self.latest_snapshot is not None or self.guaranteed_snapshots or self.events
            )
            self.condition.notify_all()
            worker = self.thread
        worker.join(timeout=max(1.0, self.cfg.monitor_timeout_seconds + 2.0))
        with self.condition:
            if self.thread is worker:
                self.thread = None

    def enqueue_event(self, event: dict[str, Any]) -> None:
        if not self.ready:
            return
        item = dict(event)
        item.setdefault("_eventId", uuid.uuid4().hex)
        item.setdefault("_sourceOwnerId", self.coordinator.owner_id)
        with self.condition:
            self.events.append(item)
            self.publish_requested = True
            self.condition.notify_all()

    def submit_snapshot(self, snapshot: dict[str, Any], guaranteed: bool = False) -> None:
        if not self.ready:
            return
        kind = str(snapshot.get("statusUpdate", {}).get("kind", ""))
        if self.weekend_idle and kind not in {"WEEKEND_STARTUP", "ACCOUNT_FUNDING_CHANGE"}:
            return
        with self.condition:
            if guaranteed:
                self.guaranteed_snapshots.append(snapshot)
            else:
                self.latest_snapshot = snapshot
            self.publish_requested = True
            self.condition.notify_all()

    def rate_limited_error(self, message: str, *args: Any) -> None:
        now = time_module.monotonic()
        if now - self.last_error_log_monotonic >= max(
            5.0, self.cfg.monitor_error_log_interval_seconds
        ):
            self.last_error_log_monotonic = now
            self.local_log(logging.ERROR, message, *args)

    def strategy_decision_for_persistence(
        self, snapshot: dict[str, Any]
    ) -> Optional[dict[str, Any]]:
        decision = (
            snapshot.get("strategyDecision")
            if isinstance(snapshot.get("strategyDecision"), dict)
            else None
        )
        if decision is None:
            return None
        decision_id = str(decision.get("decisionId", "")).strip()
        if not decision_id or decision_id in self.acknowledged_strategy_decision_ids:
            return None
        return decision

    def strategy_specification_for_persistence(
        self, snapshot: dict[str, Any]
    ) -> Optional[dict[str, Any]]:
        specification = snapshot.get("strategySpecification")
        if not isinstance(specification, dict):
            return None
        spec_id = str(specification.get("specId", "")).strip()
        if not spec_id or spec_id in self.acknowledged_strategy_specification_ids:
            return None
        return specification

    def remember_acknowledged_strategy_decision(self, decision_id: str) -> bool:
        decision_id = str(decision_id).strip()
        if not decision_id or decision_id in self.acknowledged_strategy_decision_ids:
            return False
        while (
            len(self.acknowledged_strategy_decision_order)
            >= self.acknowledged_strategy_decision_limit
        ):
            expired = self.acknowledged_strategy_decision_order.popleft()
            self.acknowledged_strategy_decision_ids.discard(expired)
        self.acknowledged_strategy_decision_order.append(decision_id)
        self.acknowledged_strategy_decision_ids.add(decision_id)
        return True

    def update_equity_history(self, snapshot: dict[str, Any], captured_at: str) -> None:
        self.equity_history = self.load_equity_history()
        account = snapshot.get("account")
        if not isinstance(account, dict):
            return
        equity = account.get("equity")
        if not isinstance(equity, (int, float)):
            return
        should_append = not self.equity_history
        if self.equity_history:
            try:
                previous = datetime.fromisoformat(
                    str(self.equity_history[-1]["time"]).replace("Z", "+00:00")
                )
                current = datetime.fromisoformat(captured_at.replace("Z", "+00:00"))
                should_append = (
                    current - previous
                ).total_seconds() >= self.cfg.monitor_equity_sample_seconds
            except Exception:
                should_append = True
        if should_append:
            self.equity_history.append({"time": captured_at, "value": float(equity)})
            self.equity_history = self.equity_history[
                -max(1, self.cfg.monitor_equity_history_points):
            ]
            self.save_equity_history()
        # The backend constructs authoritative daily, weekly, and all-time
        # curves from strategy_equity_points. Keep only a bounded compatibility
        # fallback in the snapshot; embedding the full 10,080-point local
        # history can exceed ingest.php's deliberate 512 KiB request limit.
        snapshot["equityHistory"] = list(
            self.equity_history[-SNAPSHOT_EQUITY_HISTORY_FALLBACK_POINTS:]
        )

    @staticmethod
    def public_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                key: value
                for key, value in event.items()
                if not key.startswith("_")
            }
            for event in events
        ]

    def _post_json(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(
            payload, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.cfg.monitor_write_token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": f"OPPW-MT5-Publisher/{BUILD_ID}",
            },
        )
        try:
            with urllib.request.urlopen(
                request, timeout=self.cfg.monitor_timeout_seconds
            ) as response:
                response_text = response.read().decode("utf-8", errors="replace")
                if int(response.status) not in (200, 201):
                    raise RuntimeError(f"HTTP {response.status}")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"connection failed: {exc.reason}") from exc
        try:
            decoded = json.loads(response_text) if response_text.strip() else {}
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"Backend response was not JSON: {response_text[:200]}"
            ) from exc
        if not isinstance(decoded, dict) or not bool(decoded.get("ok", False)):
            raise RuntimeError(
                str(decoded.get("error", "backend rejected request"))
                if isinstance(decoded, dict)
                else "backend rejected request"
            )
        return decoded

    def send(self, snapshot: dict[str, Any], events: list[dict[str, Any]]) -> None:
        captured_at = datetime.now(UTC).isoformat()
        snapshot_copy = json.loads(json.dumps(snapshot, separators=(",", ":")))
        self.update_equity_history(snapshot_copy, captured_at)
        strategy_specification = self.strategy_specification_for_persistence(snapshot_copy)
        strategy_decision = self.strategy_decision_for_persistence(snapshot_copy)
        execution = (
            snapshot_copy.get("execution")
            if isinstance(snapshot_copy.get("execution"), dict)
            else {}
        )
        execution_id = str(execution.get("executionId", ""))
        publication_event: Optional[dict[str, Any]] = None
        outbound_events = list(events)
        if execution_id and execution_id not in self.published_execution_ids:
            publication_event = {
                "time": captured_at,
                "level": "INFO",
                "name": "EXECUTION_STAGE",
                "result": True,
                "message": (
                    f"EVENT EXECUTION_STAGE execution_id={execution_id} "
                    "stage=PUBLISHED"
                ),
                "details": {
                    "execution_id": execution_id,
                    "decision_id": str(execution.get("decisionId", "")),
                    "position_ticket": int(execution.get("positionTicket", 0) or 0),
                    "stage": "PUBLISHED",
                    "event_at": captured_at,
                    "reason": "snapshot_persisted",
                    "strategy_spec_id": str(execution.get("strategySpecId", "")),
                    "strategy_spec_hash": str(execution.get("strategySpecHash", "")),
                },
            }
            outbound_events.append(publication_event)
        payload: dict[str, Any] = {
            "accountKey": self.cfg.monitor_account_key,
            "capturedAt": captured_at,
            "snapshot": snapshot_copy,
            "events": self.public_events(outbound_events),
            "coordination": self.coordinator.actor_payload(),
        }
        if strategy_decision is not None:
            payload["strategyDecision"] = strategy_decision
        if strategy_specification is not None:
            payload["strategySpecification"] = strategy_specification
        response_payload = self._post_json(self.cfg.monitor_ingest_url, payload)
        if strategy_specification is not None:
            expected_spec_id = str(strategy_specification.get("specId", ""))
            expected_spec_hash = str(strategy_specification.get("specHash", ""))
            stored = bool(response_payload.get("strategySpecificationStored", False))
            stored_id = str(response_payload.get("strategySpecificationId", ""))
            stored_hash = str(response_payload.get("strategySpecificationHash", ""))
            if not stored or stored_id != expected_spec_id or stored_hash != expected_spec_hash:
                raise RuntimeError(
                    "Backend did not acknowledge immutable strategy specification "
                    f"(expected={expected_spec_id or 'none'} stored={stored_id or 'none'})"
                )
            self.acknowledged_strategy_specification_ids.add(stored_id)
            self.local_log(
                logging.INFO,
                "EVENT STRATEGY_SPECIFICATION_PERSISTED spec_id=%s spec_hash=%s backend=%s",
                stored_id, stored_hash, self.cfg.monitor_ingest_url,
            )
        if strategy_decision is not None:
            expected_decision_id = str(strategy_decision.get("decisionId", ""))
            stored = bool(response_payload.get("strategyDecisionStored", False))
            stored_id = str(response_payload.get("strategyDecisionId", ""))
            if not stored or stored_id != expected_decision_id:
                raise RuntimeError(
                    "Backend did not acknowledge strategy_decisions persistence "
                    f"(expected={expected_decision_id or 'none'} stored={stored_id or 'none'})"
                )
            if self.remember_acknowledged_strategy_decision(stored_id):
                self.local_log(
                    logging.INFO,
                    "EVENT STRATEGY_DECISION_PERSISTED decision_id=%s backend=%s",
                    stored_id,
                    self.cfg.monitor_ingest_url,
                )
        if publication_event is not None:
            self.published_execution_ids.add(execution_id)

    def send_events_only(self, events: list[dict[str, Any]]) -> None:
        if not events:
            return
        payload = {
            "accountKey": self.cfg.monitor_account_key,
            "events": self.public_events(events),
            "coordination": self.coordinator.actor_payload(),
        }
        specification = self.canonical_strategy_specification
        if isinstance(specification, dict) and str(specification.get("specId", "")) not in self.acknowledged_strategy_specification_ids:
            payload["strategySpecification"] = specification
        response = self._post_json(self.cfg.events_ingest_url, payload)
        if "strategySpecification" in payload:
            expected_id = str(specification.get("specId", ""))
            expected_hash = str(specification.get("specHash", ""))
            if (
                not bool(response.get("strategySpecificationStored", False))
                or str(response.get("strategySpecificationId", "")) != expected_id
                or str(response.get("strategySpecificationHash", "")) != expected_hash
            ):
                raise RuntimeError("Events backend did not acknowledge immutable strategy specification")
            self.acknowledged_strategy_specification_ids.add(expected_id)

    def _take_events(self) -> list[dict[str, Any]]:
        maximum = max(1, self.cfg.monitor_event_buffer_size)
        result: list[dict[str, Any]] = []
        while self.events and len(result) < maximum:
            result.append(self.events.popleft())
        return result

    def _requeue_events(self, events: list[dict[str, Any]]) -> None:
        if not events:
            return
        existing_ids = {
            str(item.get("_eventId", ""))
            for item in self.events
            if str(item.get("_eventId", ""))
        }
        for item in reversed(events):
            event_id = str(item.get("_eventId", ""))
            if event_id and event_id in existing_ids:
                continue
            self.events.appendleft(item)
            if event_id:
                existing_ids.add(event_id)

    def worker(self) -> None:
        paused_for_lease = False
        while True:
            with self.condition:
                while (
                    not self.publish_requested
                    and not self.events
                    and not self.stopping
                ):
                    self.condition.wait(timeout=0.5)
                if (
                    self.stopping
                    and not self.publish_requested
                    and not self.guaranteed_snapshots
                    and not self.events
                ):
                    return

            # This may perform an HTTPS lease-status request and may log a
            # BACKEND_PUBLISHING_STATE transition. It must remain outside the
            # condition lock: logging handlers enqueue mobile events and would
            # otherwise invert the logger/queue lock order with another thread.
            allowed = self.allowed_to_publish()

            if not self.coordinator.role_lease_valid():
                if not paused_for_lease:
                    paused_for_lease = True
                    self.local_log(
                        logging.WARNING,
                        "EVENT MONITOR_PUBLISH_PAUSED role=%s account_key=%s "
                        "reason=role_lease_invalid fencing_token=%s",
                        self.role,
                        self.cfg.monitor_account_key,
                        self.coordinator.fencing_token,
                    )
                with self.condition:
                    if self.stopping:
                        return
                    self.condition.wait(timeout=0.25)
                continue

            if paused_for_lease:
                paused_for_lease = False
                self.local_log(
                    logging.INFO,
                    "EVENT MONITOR_PUBLISH_RESUMED role=%s account_key=%s "
                    "reason=role_lease_valid fencing_token=%s",
                    self.role,
                    self.cfg.monitor_account_key,
                    self.coordinator.fencing_token,
                )

            with self.condition:
                guaranteed = bool(self.guaranteed_snapshots)
                snapshot: Optional[dict[str, Any]] = None
                if allowed:
                    if guaranteed:
                        snapshot = self.guaranteed_snapshots.popleft()
                    elif self.latest_snapshot is not None:
                        snapshot = self.latest_snapshot
                        self.latest_snapshot = None
                events = self._take_events()
                self.publish_requested = bool(
                    self.guaranteed_snapshots
                    or self.latest_snapshot is not None
                    or self.events
                )

            if (
                snapshot is not None
                and self.weekend_idle
                and str(snapshot.get("statusUpdate", {}).get("kind", ""))
                not in {"WEEKEND_STARTUP", "ACCOUNT_FUNDING_CHANGE"}
            ):
                snapshot = None

            succeeded = False
            try:
                if snapshot is not None:
                    self.send(snapshot, events)
                elif events:
                    # Executor events are persisted even while a dedicated
                    # publisher owns snapshot publication.
                    self.send_events_only(events)
                else:
                    if self.stopping:
                        return
                    time_module.sleep(0.2)
                    continue
                succeeded = True
                self.last_success_utc = datetime.now(UTC).isoformat()
            except Exception as exc:
                with self.condition:
                    self._requeue_events(events)
                    if snapshot is not None:
                        if guaranteed:
                            self.guaranteed_snapshots.appendleft(snapshot)
                        else:
                            self.latest_snapshot = snapshot
                    self.publish_requested = True
                self.rate_limited_error(
                    "EVENT MONITOR_PUBLISH_FAILED error=%s queued_events=%s",
                    exc,
                    len(events),
                )
                if self.stopping:
                    return
                time_module.sleep(0.5)

            if self.stopping and succeeded:
                with self.condition:
                    if (
                        not self.guaranteed_snapshots
                        and self.latest_snapshot is None
                        and not self.events
                    ):
                        return
                    self.publish_requested = True


class MobileEventHandler(logging.Handler):
    def __init__(self, publisher: MobileMonitorPublisher):
        super().__init__(logging.INFO)
        self.publisher = publisher

    @staticmethod
    def parse_value(value: str) -> Any:
        lowered = value.lower()
        if lowered in {"true", "false"}:
            return lowered == "true"
        try:
            return int(value)
        except ValueError:
            try:
                return float(value)
            except ValueError:
                return value

    @classmethod
    def parse_details(cls, tokens: list[str]) -> dict[str, Any]:
        details: dict[str, Any] = {}
        for token in tokens:
            if "=" not in token:
                continue
            key, value = token.split("=", 1)
            if key:
                details[key] = cls.parse_value(value)
        return details

    @staticmethod
    def inferred_result(name: str) -> Optional[bool]:
        positive = ("_ACCEPTED", "_CONNECTED", "_RECOVERED", "_CAPTURED", "_ARMED", "_UPDATED", "_PROCESSED", "_STARTED")
        negative = ("_REJECTED", "_FAILED", "_LOST", "_SKIPPED", "_DISAPPEARED")
        if name.endswith(positive):
            return True
        if name.endswith(negative):
            return False
        return None

    def emit(self, record: logging.LogRecord) -> None:
        if getattr(record, "skip_mobile_publish", False) or not self.publisher.ready:
            return
        try:
            message = record.getMessage()
            if not (message.startswith("EVENT ") or message.startswith("CHECK ")):
                return
            tokens = shlex.split(message)
            if len(tokens) < 2:
                return

            kind = tokens[0]
            details = self.parse_details(tokens[2:] if kind == "EVENT" else tokens[1:])
            if kind == "CHECK":
                name = str(details.get("name", "CHECK"))
                result_value = details.get("result")
                result = result_value if isinstance(result_value, bool) else str(result_value).upper() == "TRUE" if result_value is not None else None
            else:
                name = tokens[1]
                if name == "SCHEDULED_CHECK" and details.get("name"):
                    name = str(details["name"])
                result_value = details.get("result")
                result = result_value if isinstance(result_value, bool) else self.inferred_result(name)

            event = {
                "time": datetime.fromtimestamp(record.created, UTC).isoformat(),
                "level": record.levelname,
                "name": name[:100],
                "result": result,
                "message": message[:1000],
                "details": details,
            }
            self.publisher.enqueue_event(event)
        except Exception:
            self.handleError(record)
