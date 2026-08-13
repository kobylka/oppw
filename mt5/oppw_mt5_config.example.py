"""Private OPPW MT5 account credentials and explicit overrides.

Copy this file to an ignored account-specific path:

DEMO: mt5/demo/demo_mt5_config.py
REAL: mt5/real/real_mt5_config.py
Named examples: mt5/demo/demo_alpha_mt5_config.py or mt5/real/real_prop_mt5_config.py

Canonical configuration fields and defaults live in oppw_core/settings.py.
Only credentials and values that intentionally differ from those defaults
belong here. OPPW_* environment variables take precedence over this file.
"""

from __future__ import annotations


# Required private connection and publishing credentials. Keep real values out
# of Git; the committed template must retain placeholders only.
MT5_TERMINAL_PATH = r"C:\Program Files\MetaTrader 5\terminal64.exe"
MT5_LOGIN = 0
MT5_PASSWORD = ""
MT5_SERVER = ""
MONITOR_WRITE_TOKEN = ""


# Optional account-specific differences from oppw_core.settings.Config.
# Field names are validated strictly; unknown names stop startup.
OVERRIDES = {
    # "live_enabled": True,
    # "entry_action_lead_seconds": 3.0,
    # "monitor_enabled": True,
}
