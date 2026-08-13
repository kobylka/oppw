# ADR 0033: Scoped MT5 risk-warning acknowledgement

- Status: Accepted
- Date: 2026-08-13
- Extends: ADR 0010 cohesive MT5 runtime modules

## Context

The TMS MetaTrader terminals display a modal Polish high-risk-investment warning after broker login. The modal can block the official MetaTrader5 Python bridge during `mt5.initialize`, so readiness-gated service startup times out for both TMS accounts even when their credentials, account types, and terminal paths are correct. Each account uses its own terminal installation and the service already launches the canonical loop in the terminal owner's interactive Windows session.

The official bridge defaults `initialize()` to 60 seconds. TMS can acknowledge the warning yet finish broker authorization only after that deadline, leaving a logged-in terminal but a failed Python child.

## Decision

Add a bounded `oppw_core.windows_ui` module and an operational configuration field named `auto_acknowledge_high_risk_warning`, disabled by default. When an account explicitly opts in, the canonical loop starts a background watcher immediately before `mt5.initialize`. Broker authorization may create the modal after the Python bridge returns, so the watcher continues independently until it acknowledges the dialog or reaches its configured timeout.

Make the official bridge timeout a validated per-account setting expressed in seconds and forwarded to `mt5.initialize` in milliseconds. TMS uses 120 seconds, Bossa retains 60 seconds, and the service readiness deadline is 150 seconds so post-connect validation has a bounded margin.

TMS also opts into a two-phase official API sequence: attach IPC with `initialize(path, timeout)` and only then authorize through `login(account, password, server, timeout)`. The canonical runtime still validates the returned login, Demo/Real trade mode, configured symbols, and executor AutoTrading before publishing readiness. Other accounts retain the combined initialization call by default.

The watcher uses only standard Win32 APIs. It acts only when all of these values match exactly:

- the top-level Polish high-risk-warning title;
- the configured account's resolved `terminal64.exe` process path;
- the full acknowledgement checkbox text;
- the enabled `OK` button.

It first uses exact native controls: check the checkbox, verify its state, and click `OK`. Some MT5 builds draw the dialog without exposing those child controls. For that exact title and exact owning executable only, the fallback activates the dialog and applies its deterministic keyboard order (back-tab from Cancel to the checkbox, Space, Tab to OK, Enter); success is recorded only after that same dialog closes. A different executable, translated or changed title, non-Windows host, or Win32 error fails without input. No coordinate-based input, broad title pattern, third-party UI package, or persistent background automation is used.

## Consequences

- Authorized TMS startup can pass the broker modal without weakening the readiness gate.
- Bossa and every future account remain unaffected unless their private configuration explicitly opts in.
- The acknowledgement is a legal/operational authorization and remains separate from strategy specification identity and trading logic.
- Broker dialog changes fail closed and require deliberate review rather than silently clicking an unknown control.
- Repository validation includes the new cohesive module in the fixed canonical package set.
