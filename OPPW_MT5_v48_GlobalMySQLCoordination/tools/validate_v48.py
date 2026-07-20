"""Offline structural validation for the OPPW MT5 v48 package."""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOOP = ROOT / "mt5" / "oppw_mt5_continuous_v48.py"
CONFIGS = [
    ROOT / "mt5" / "oppw_mt5_config.example.py",
    ROOT / "mt5" / "demo" / "oppw_mt5_config.example.py",
    ROOT / "mt5" / "real" / "oppw_mt5_config.example.py",
]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


for path in [LOOP, *CONFIGS]:
    compile(path.read_text(encoding="utf-8-sig"), str(path), "exec")

loop_text = LOOP.read_text(encoding="utf-8-sig")
require("--conservative-multiplier" in loop_text, "v48.2 conservative CLI flag missing")
require("--legacy-balance-multiplier" not in loop_text, "obsolete legacy CLI flag remains")
for forbidden in (
    "InterProcessFileLock",
    "PublisherPresence",
    "SharedEventSpool",
    "lock_file",
    "event_spool_lock_timeout_seconds",
    "publisher_heartbeat_interval_seconds",
):
    require(forbidden not in loop_text, f"obsolete filesystem coordination remains: {forbidden}")

tree = ast.parse(loop_text)
order_send_calls = [
    node
    for node in ast.walk(tree)
    if isinstance(node, ast.Call)
    and isinstance(node.func, ast.Attribute)
    and isinstance(node.func.value, ast.Name)
    and node.func.value.id == "mt5"
    and node.func.attr == "order_send"
]
require(len(order_send_calls) == 3, f"expected 3 order_send surfaces, found {len(order_send_calls)}")

functions = {
    node.name: ast.get_source_segment(loop_text, node) or ""
    for node in ast.walk(tree)
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
}
for function_name in ("send_buy", "modify_sltp", "close_position_market"):
    source = functions.get(function_name, "")
    require("acquire_trade_gate" in source, f"{function_name} does not acquire the trade gate")
    require("validate_trade_gate" in source, f"{function_name} does not validate the trade gate")
    require("mt5.order_send" in source, f"{function_name} has no MT5 send")

send_buy = functions["send_buy"]
require("claim_weekly_entry" in send_buy, "BUY has no durable weekly claim")
require('"UNKNOWN" if order_send_started else "REJECTED"' in send_buy, "BUY ambiguity policy missing")

worker_node = next(
    node for node in ast.walk(tree)
    if isinstance(node, ast.FunctionDef) and node.name == "worker"
)
for node in ast.walk(worker_node):
    if not isinstance(node, (ast.With, ast.AsyncWith)):
        continue
    is_condition_lock = any(
        isinstance(item.context_expr, ast.Attribute)
        and isinstance(item.context_expr.value, ast.Name)
        and item.context_expr.value.id == "self"
        and item.context_expr.attr == "condition"
        for item in node.items
    )
    if not is_condition_lock:
        continue
    require(
        not any(
            isinstance(child, ast.Call)
            and isinstance(child.func, ast.Attribute)
            and child.func.attr == "allowed_to_publish"
            for child in ast.walk(node)
        ),
        "publisher ownership check/logging occurs while the event condition lock is held",
    )

for function_name in ("startup_reconcile", "log_status_if_needed"):
    source = functions.get(function_name, "")
    require(
        "print_autotrading_banner" in source and "print_live_enabled_banner" in source,
        f"{function_name} is missing AutoTrading/LIVE banners",
    )
    require(
        source.index("print_autotrading_banner") < source.index("print_live_enabled_banner"),
        f"{function_name} prints LIVE before AutoTrading",
    )

required_config_names = {
    "coordination_url",
    "events_ingest_url",
    "coordination_timeout_seconds",
    "role_lease_ttl_seconds",
    "role_lease_heartbeat_seconds",
    "role_lease_safety_margin_seconds",
    "publisher_presence_check_interval_seconds",
    "trade_gate_ttl_seconds",
    "trade_gate_max_hold_seconds",
}
for config_path in CONFIGS:
    config_text = config_path.read_text(encoding="utf-8")
    config_tree = ast.parse(config_text)
    config_class = next(
        node for node in config_tree.body if isinstance(node, ast.ClassDef) and node.name == "Config"
    )
    fields = {
        node.target.id
        for node in config_class.body
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
    }
    require(required_config_names <= fields, f"{config_path.name} lacks v48 fields")
    require("lock_file" not in fields, f"{config_path.name} still defines lock_file")

backend_requirements = {
    ROOT / "Mobile" / "backend" / "coordination.php": (
        "acquireLease",
        "renewLease",
        "acquireTradeGate",
        "validateTradeGate",
        "claimWeeklyEntry",
        "completeWeeklyEntry",
    ),
    ROOT / "Mobile" / "backend" / "events-ingest.php": (
        "require_coordination_actor",
        "strategy_events",
    ),
    ROOT / "Mobile" / "backend" / "ingest.php": ("require_coordination_actor",),
    ROOT / "Mobile" / "backend" / "lib.php": ("strategy_runtime_leases",),
}
for path, markers in backend_requirements.items():
    text = path.read_text(encoding="utf-8")
    require(text.lstrip().startswith("<?php"), f"{path.name} is not a PHP endpoint")
    for marker in markers:
        require(marker in text, f"{path.name} lacks {marker}")

migration = (ROOT / "Mobile" / "backend" / "sql" / "migrate_v48_global_leases.sql").read_text(encoding="utf-8")
for marker in ("strategy_runtime_leases", "strategy_weekly_entries", "uq_weekly_entry_execution"):
    require(marker in migration, f"migration lacks {marker}")

print("OPPW v48 structural validation passed")
