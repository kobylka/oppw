from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path
import sys


MT5_DIR = Path(__file__).resolve().parents[1]
if str(MT5_DIR) not in sys.path:
    sys.path.insert(0, str(MT5_DIR))

from oppw_core.windows_ui import (
    HIGH_RISK_WARNING_CHECKBOX,
    HIGH_RISK_WARNING_OK,
    HIGH_RISK_WARNING_TITLE,
    HighRiskWarningAcknowledger,
    acknowledge_high_risk_warning_once,
)


class FakeBackend:
    def __init__(
        self,
        owner: Path,
        title: str = HIGH_RISK_WARNING_TITLE,
        native_controls: bool = True,
    ) -> None:
        self.owner = owner
        self.title = title
        self.checked = False
        self.ok_enabled = False
        self.clicks: list[int] = []
        self.native_controls = native_controls
        self.keyboard_attempts: list[int] = []
        self.open = True

    def top_windows(self, title: str) -> list[int]:
        return [1] if self.open and title == self.title else []

    def process_path(self, window: int) -> Path | None:
        return self.owner if window == 1 else None

    def child_windows(self, parent: int) -> list[int]:
        return [2, 3] if self.native_controls and parent == 1 else []

    def class_name(self, window: int) -> str:
        return "Button"

    def text(self, window: int) -> str:
        return {2: HIGH_RISK_WARNING_CHECKBOX, 3: HIGH_RISK_WARNING_OK}[window]

    def is_checked(self, window: int) -> bool:
        return window == 2 and self.checked

    def is_enabled(self, window: int) -> bool:
        return window == 3 and self.ok_enabled

    def click(self, window: int) -> bool:
        self.clicks.append(window)
        if window == 2:
            self.checked = True
            self.ok_enabled = True
        return True

    def keyboard_acknowledge(self, window: int) -> bool:
        self.keyboard_attempts.append(window)
        self.open = False
        return True

    def window_exists(self, window: int) -> bool:
        return self.open


class RiskAcknowledgementTests(unittest.TestCase):
    def test_exact_dialog_for_exact_terminal_is_checked_then_confirmed(self):
        with tempfile.TemporaryDirectory() as directory:
            terminal = Path(directory) / "terminal64.exe"
            backend = FakeBackend(terminal)

            acknowledged = acknowledge_high_risk_warning_once(backend, terminal)

            self.assertTrue(acknowledged)
            self.assertEqual([2, 3], backend.clicks)
            self.assertEqual([], backend.keyboard_attempts)

    def test_custom_control_dialog_uses_scoped_keyboard_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            terminal = Path(directory) / "terminal64.exe"
            backend = FakeBackend(terminal, native_controls=False)

            acknowledged = acknowledge_high_risk_warning_once(backend, terminal)

            self.assertTrue(acknowledged)
            self.assertEqual([], backend.clicks)
            self.assertEqual([1], backend.keyboard_attempts)

    def test_different_terminal_owner_is_never_clicked(self):
        with tempfile.TemporaryDirectory() as directory:
            expected = Path(directory) / "tms" / "terminal64.exe"
            other = Path(directory) / "other" / "terminal64.exe"
            backend = FakeBackend(other)

            acknowledged = acknowledge_high_risk_warning_once(backend, expected)

            self.assertFalse(acknowledged)
            self.assertEqual([], backend.clicks)
            self.assertEqual([], backend.keyboard_attempts)

    def test_similar_but_non_exact_dialog_is_never_clicked(self):
        with tempfile.TemporaryDirectory() as directory:
            terminal = Path(directory) / "terminal64.exe"
            backend = FakeBackend(terminal, title=HIGH_RISK_WARNING_TITLE + "!")

            acknowledged = acknowledge_high_risk_warning_once(backend, terminal)

            self.assertFalse(acknowledged)
            self.assertEqual([], backend.clicks)

    def test_bounded_watcher_reports_one_acknowledgement(self):
        with tempfile.TemporaryDirectory() as directory:
            terminal = Path(directory) / "terminal64.exe"
            backend = FakeBackend(terminal)
            acknowledged = threading.Event()
            errors: list[Exception] = []
            watcher = HighRiskWarningAcknowledger(
                terminal,
                timeout_seconds=1,
                on_acknowledged=acknowledged.set,
                on_error=errors.append,
                backend=backend,
            )

            watcher.start()
            self.assertTrue(acknowledged.wait(1))
            watcher.stop()

            self.assertEqual([2, 3], backend.clicks)
            self.assertEqual([], errors)

    def test_watcher_reports_timeout_when_dialog_never_appears(self):
        with tempfile.TemporaryDirectory() as directory:
            terminal = Path(directory) / "terminal64.exe"
            backend = FakeBackend(terminal, title="different title")
            timed_out = threading.Event()
            errors: list[Exception] = []
            watcher = HighRiskWarningAcknowledger(
                terminal,
                timeout_seconds=0.01,
                on_acknowledged=lambda: self.fail("unexpected acknowledgement"),
                on_error=errors.append,
                on_timeout=timed_out.set,
                backend=backend,
            )

            watcher.start()
            self.assertTrue(timed_out.wait(2))
            watcher.stop()

            self.assertEqual([], errors)


if __name__ == "__main__":
    unittest.main()
