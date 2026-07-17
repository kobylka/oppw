from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class PublisherConfig:
    endpoint: str = os.getenv("OPPW_MONITOR_INGEST_URL", "https://example.com/oppw-api/ingest.php")
    token: str = os.getenv("OPPW_MONITOR_WRITE_TOKEN", "")
    account_key: str = os.getenv("OPPW_MONITOR_ACCOUNT_KEY", "DEMO")
    timeout_seconds: float = 8.0


class StatusPublisher:
    def __init__(self, config: PublisherConfig | None = None) -> None:
        self.config = config or PublisherConfig()

    def publish(self, snapshot: dict[str, Any], events: list[dict[str, Any]] | None = None) -> None:
        if not self.config.endpoint.startswith("https://"):
            raise ValueError("Ingest endpoint must use HTTPS")
        if not self.config.token:
            raise ValueError("OPPW_MONITOR_WRITE_TOKEN is empty")
        if not self.config.account_key:
            raise ValueError("OPPW_MONITOR_ACCOUNT_KEY is empty")

        payload = {
            "accountKey": self.config.account_key,
            "capturedAt": datetime.now(timezone.utc).isoformat(),
            "snapshot": snapshot,
            "events": events or [],
        }
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        request = urllib.request.Request(
            self.config.endpoint,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.config.token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "OPPW-MT5-Publisher/2.0",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.config.timeout_seconds) as response:
                if response.status not in (200, 201):
                    raise RuntimeError(f"Publisher HTTP status {response.status}")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Publisher rejected: HTTP {exc.code}: {detail[:300]}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Publisher connection failed: {exc.reason}") from exc


if __name__ == "__main__":
    sample = {
        "connection": {
            "connected": True,
            "lastSync": datetime.now(timezone.utc).isoformat(),
            "accountId": os.getenv("OPPW_MONITOR_ACCOUNT_KEY", "DEMO"),
            "week": "2026-W29",
            "health": "OK",
            "phase": "Regular session",
            "nextAction": "CH / TO",
            "nextActionAt": "2026-07-16T19:59:57+00:00",
            "us100AgeSeconds": 0.3,
            "qqqAgeSeconds": 0.5,
        },
        "account": {"currency": "PLN", "strategyCapital": 30000.0, "deposit": 111.12, "balance": 30000.0, "equity": 29632.5},
        "position": None,
        "closestCondition": None,
        "equityHistory": [],
    }
    StatusPublisher().publish(sample, [{"level": "INFO", "name": "PUBLISHER_TEST", "result": True, "message": "Test snapshot uploaded."}])
