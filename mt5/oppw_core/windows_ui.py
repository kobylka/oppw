"""Narrow Windows UI automation used only during opted-in MT5 startup."""

from __future__ import annotations

import ctypes
import os
import threading
import time
from ctypes import wintypes
from pathlib import Path
from typing import Callable, Protocol


HIGH_RISK_WARNING_TITLE = "Ostrzeżenie O Wysokim Ryzyku Inwestycyjnym"
HIGH_RISK_WARNING_CHECKBOX = (
    "Zapoznałem się z komunikatem i chcę handlować na instrumentach o wysokim ryzyku"
)
HIGH_RISK_WARNING_OK = "OK"


class WindowBackend(Protocol):
    def top_windows(self, title: str) -> list[int]: ...
    def process_path(self, window: int) -> Path | None: ...
    def child_windows(self, parent: int) -> list[int]: ...
    def class_name(self, window: int) -> str: ...
    def text(self, window: int) -> str: ...
    def is_checked(self, window: int) -> bool: ...
    def is_enabled(self, window: int) -> bool: ...
    def click(self, window: int) -> bool: ...
    def keyboard_acknowledge(self, window: int) -> bool: ...
    def window_exists(self, window: int) -> bool: ...


def normalized_executable_path(path: str | Path) -> str:
    return os.path.normcase(os.path.realpath(os.path.abspath(str(path))))


def acknowledge_high_risk_warning_once(backend: WindowBackend, terminal_path: str | Path) -> bool:
    """Acknowledge only the exact warning owned by the exact configured terminal."""
    expected_path = normalized_executable_path(terminal_path)
    for dialog in backend.top_windows(HIGH_RISK_WARNING_TITLE):
        owner_path = backend.process_path(dialog)
        if owner_path is None or normalized_executable_path(owner_path) != expected_path:
            continue
        checkbox = None
        ok_button = None
        for child in backend.child_windows(dialog):
            if backend.class_name(child) != "Button":
                continue
            text = backend.text(child)
            if text == HIGH_RISK_WARNING_CHECKBOX:
                checkbox = child
            elif text == HIGH_RISK_WARNING_OK:
                ok_button = child
        if checkbox is None or ok_button is None:
            if backend.keyboard_acknowledge(dialog):
                deadline = time.monotonic() + 2.0
                while time.monotonic() < deadline:
                    if not backend.window_exists(dialog):
                        return True
                    time.sleep(0.05)
            continue
        if not backend.is_checked(checkbox):
            if not backend.click(checkbox) or not backend.is_checked(checkbox):
                continue
        if backend.is_enabled(ok_button) and backend.click(ok_button):
            return True
    return False


class Win32WindowBackend:
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    BM_GETCHECK = 0x00F0
    BM_CLICK = 0x00F5
    BST_CHECKED = 1
    SMTO_ABORTIFHUNG = 0x0002
    INPUT_KEYBOARD = 1
    KEYEVENTF_KEYUP = 0x0002
    VK_SHIFT = 0x10
    VK_TAB = 0x09
    VK_SPACE = 0x20
    VK_RETURN = 0x0D

    def __init__(self) -> None:
        if os.name != "nt":
            raise RuntimeError("Windows dialog automation is available only on Windows")
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        self.kernel32.OpenProcess.restype = wintypes.HANDLE
        self.kernel32.QueryFullProcessImageNameW.argtypes = [
            wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)
        ]
        self.kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
        self.kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel32.CloseHandle.restype = wintypes.BOOL
        self.user32.GetWindowThreadProcessId.argtypes = [
            wintypes.HWND, ctypes.POINTER(wintypes.DWORD)
        ]
        self.user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        self.user32.SendMessageTimeoutW.restype = wintypes.LPARAM

        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [
                ("wVk", wintypes.WORD),
                ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.c_size_t),
            ]

        class INPUT_UNION(ctypes.Union):
            _fields_ = [("ki", KEYBDINPUT)]

        class INPUT(ctypes.Structure):
            _anonymous_ = ("value",)
            _fields_ = [("type", wintypes.DWORD), ("value", INPUT_UNION)]

        self.KEYBDINPUT = KEYBDINPUT
        self.INPUT = INPUT
        self.user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
        self.user32.SendInput.restype = wintypes.UINT

    def _text_value(self, window: int, class_name: bool = False) -> str:
        if class_name:
            buffer = ctypes.create_unicode_buffer(256)
            self.user32.GetClassNameW(wintypes.HWND(window), buffer, len(buffer))
            return buffer.value
        length = self.user32.GetWindowTextLengthW(wintypes.HWND(window))
        buffer = ctypes.create_unicode_buffer(max(1, length + 1))
        self.user32.GetWindowTextW(wintypes.HWND(window), buffer, len(buffer))
        return buffer.value

    def top_windows(self, title: str) -> list[int]:
        found: list[int] = []
        callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        @callback_type
        def callback(window, _parameter):
            if self.user32.IsWindowVisible(window) and self._text_value(window) == title:
                found.append(int(window))
            return True

        self.user32.EnumWindows(callback, 0)
        return found

    def process_path(self, window: int) -> Path | None:
        process_id = wintypes.DWORD()
        self.user32.GetWindowThreadProcessId(wintypes.HWND(window), ctypes.byref(process_id))
        if not process_id.value:
            return None
        process = self.kernel32.OpenProcess(
            self.PROCESS_QUERY_LIMITED_INFORMATION, False, process_id.value
        )
        if not process:
            return None
        try:
            size = wintypes.DWORD(32768)
            buffer = ctypes.create_unicode_buffer(size.value)
            if not self.kernel32.QueryFullProcessImageNameW(process, 0, buffer, ctypes.byref(size)):
                return None
            return Path(buffer.value)
        finally:
            self.kernel32.CloseHandle(process)

    def child_windows(self, parent: int) -> list[int]:
        found: list[int] = []
        callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        @callback_type
        def callback(window, _parameter):
            found.append(int(window))
            return True

        self.user32.EnumChildWindows(wintypes.HWND(parent), callback, 0)
        return found

    def class_name(self, window: int) -> str:
        return self._text_value(window, class_name=True)

    def text(self, window: int) -> str:
        return self._text_value(window)

    def _message(self, window: int, message: int) -> tuple[bool, int]:
        result = ctypes.c_size_t()
        sent = self.user32.SendMessageTimeoutW(
            wintypes.HWND(window), message, 0, 0, self.SMTO_ABORTIFHUNG, 2000,
            ctypes.byref(result),
        )
        return bool(sent), int(result.value)

    def is_checked(self, window: int) -> bool:
        sent, result = self._message(window, self.BM_GETCHECK)
        return sent and result == self.BST_CHECKED

    def is_enabled(self, window: int) -> bool:
        return bool(self.user32.IsWindowEnabled(wintypes.HWND(window)))

    def click(self, window: int) -> bool:
        sent, _result = self._message(window, self.BM_CLICK)
        return sent

    def keyboard_acknowledge(self, window: int) -> bool:
        """Use the dialog's keyboard order when MT5 exposes no native child controls."""
        if not self.user32.SetForegroundWindow(wintypes.HWND(window)):
            return False
        sequence = (
            (self.VK_SHIFT, 0),
            (self.VK_TAB, 0),
            (self.VK_TAB, self.KEYEVENTF_KEYUP),
            (self.VK_SHIFT, self.KEYEVENTF_KEYUP),
            (self.VK_SPACE, 0),
            (self.VK_SPACE, self.KEYEVENTF_KEYUP),
            (self.VK_TAB, 0),
            (self.VK_TAB, self.KEYEVENTF_KEYUP),
            (self.VK_RETURN, 0),
            (self.VK_RETURN, self.KEYEVENTF_KEYUP),
        )
        inputs = (self.INPUT * len(sequence))(
            *(
                self.INPUT(
                    type=self.INPUT_KEYBOARD,
                    ki=self.KEYBDINPUT(key, 0, flags, 0, 0),
                )
                for key, flags in sequence
            )
        )
        return self.user32.SendInput(len(inputs), inputs, ctypes.sizeof(self.INPUT)) == len(inputs)

    def window_exists(self, window: int) -> bool:
        return bool(self.user32.IsWindow(wintypes.HWND(window)))


class HighRiskWarningAcknowledger:
    """Bounded background watcher active only around ``mt5.initialize``."""

    def __init__(
        self,
        terminal_path: str | Path,
        timeout_seconds: float,
        on_acknowledged: Callable[[], None],
        on_error: Callable[[Exception], None],
        on_timeout: Callable[[], None] | None = None,
        backend: WindowBackend | None = None,
    ) -> None:
        self.terminal_path = Path(terminal_path)
        self.timeout_seconds = max(1.0, float(timeout_seconds))
        self.on_acknowledged = on_acknowledged
        self.on_error = on_error
        self.on_timeout = on_timeout
        self.backend = backend
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None

    def start(self) -> None:
        self.thread = threading.Thread(
            target=self._run,
            name="oppw-mt5-risk-warning-acknowledger",
            daemon=True,
        )
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        if self.thread is not None:
            self.thread.join(timeout=3.0)

    def _run(self) -> None:
        try:
            backend = self.backend or Win32WindowBackend()
            deadline = time.monotonic() + self.timeout_seconds
            while not self.stop_event.is_set() and time.monotonic() < deadline:
                if acknowledge_high_risk_warning_once(backend, self.terminal_path):
                    self.on_acknowledged()
                    return
                self.stop_event.wait(0.25)
            if not self.stop_event.is_set() and self.on_timeout is not None:
                self.on_timeout()
        except Exception as exc:
            self.on_error(exc)
