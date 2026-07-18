from __future__ import annotations

import argparse
import ast
from pathlib import Path

V40_BUILD = 'BUILD_ID = "2026-07-18-dual-role-multi-account-v40"'
V41_BUILD = 'BUILD_ID = "2026-07-18-flat-position-preview-v41"'

HELPERS = r'''
    def leverage_decision(self) -> tuple[int, str]:
        previous_full_week = float(self.state.prev_full_week_change)
        previous_trade = float(self.state.prev_change)
        if self.cfg.base_leverage == 8:
            triggers: list[str] = []
            if previous_full_week < -0.025:
                triggers.append(f"previous full-week change {previous_full_week:.4%} < -2.5000%")
            if previous_trade < -0.007:
                triggers.append(f"previous trade change {previous_trade:.4%} < -0.7000%")
            if triggers:
                return self.cfg.loss_leverage, f"{self.cfg.loss_leverage}x because " + " and ".join(triggers)
            return self.cfg.base_leverage, (
                f"{self.cfg.base_leverage}x because previous full-week change {previous_full_week:.4%} >= -2.5000% "
                f"and previous trade change {previous_trade:.4%} >= -0.7000%"
            )
        return self.cfg.base_leverage, f"{self.cfg.base_leverage}x because base leverage is configured as {self.cfg.base_leverage}x"

    def potential_position_preview(self) -> dict[str, Any]:
        leverage, leverage_reason = self.leverage_decision()
        result: dict[str, Any] = {
            "available": False,
            "symbol": self.cfg.trade_symbol,
            "side": "BUY",
            "price": 0.0,
            "volume": 0.0,
            "requiredDeposit": 0.0,
            "balance": 0.0,
            "effectiveLeverage": 0.0,
            "strategyLeverage": float(leverage),
            "leverageReason": leverage_reason,
            "positionNotional": 0.0,
            "sizingUnits": 0,
            "error": "",
        }
        try:
            account = mt5.account_info()
            info = mt5.symbol_info(self.cfg.trade_symbol)
            tick = self.latest_tick(self.cfg.trade_symbol)
            if account is None or info is None:
                raise RuntimeError(f"Cannot obtain account/symbol data: {mt5.last_error()}")

            balance = float(getattr(account, "balance", 0.0) or 0.0)
            ask = float(getattr(tick, "ask", 0.0) or 0.0)
            bid = float(getattr(tick, "bid", 0.0) or 0.0)
            last = float(getattr(tick, "last", 0.0) or 0.0)
            price = ask if ask > 0 else last if last > 0 else bid
            if price <= 0:
                raise RuntimeError(f"No usable current price for {self.cfg.trade_symbol}")

            minimum_volume_notional = self.minimum_volume_notional(info, price)
            _, _, sizing_units = self.target_notional(balance, leverage, minimum_volume_notional)
            volume = self.normalized_volume(sizing_units, info)
            if volume <= 0:
                raise RuntimeError("Calculated potential volume is below the broker minimum")

            required_deposit_raw = mt5.order_calc_margin(mt5.ORDER_TYPE_BUY, self.cfg.trade_symbol, volume, price)
            if required_deposit_raw is None:
                raise RuntimeError(f"order_calc_margin failed: {mt5.last_error()}")
            required_deposit = float(required_deposit_raw)
            effective_leverage = required_deposit / balance if balance > 0 else 0.0

            result.update({
                "available": True,
                "price": price,
                "volume": volume,
                "requiredDeposit": required_deposit,
                "balance": balance,
                "effectiveLeverage": effective_leverage,
                "positionNotional": sizing_units * minimum_volume_notional,
                "sizingUnits": sizing_units,
            })
        except Exception as exc:
            result["error"] = str(exc)
        return result

'''

FLAT_BLOCK = r'''        if position is None:
            preview = self.potential_position_preview()
            leverage = int(preview["strategyLeverage"])
            leverage_reason = str(preview["leverageReason"])
            if bool(preview["available"]):
                potential_lines = [
                    f"next potential position: BUY {float(preview['volume']):.2f} lot {preview['symbol']} @ {float(preview['price']):.5f}",
                    f"required deposit: {float(preview['requiredDeposit']):.2f}{currency_suffix}",
                    f"effective leverage: {float(preview['effectiveLeverage']):.4f}x (required deposit / balance)",
                    f"potential notional: {float(preview['positionNotional']):.2f}{currency_suffix}",
                ]
            else:
                potential_lines = [
                    "next potential position: unavailable",
                    f"potential position error: {preview['error'] or 'unknown'}",
                ]
            lines = [
                f"==================== TRADE STATUS - {reason} ====================",
                f"phase: {phase} protection regime: {regime}",
                f"time: {now:%Y-%m-%d %H:%M:%S %Z} week: {iso_week_key(now.date())}",
                "closest condition: none — no open position",
                "position: FLAT",
                *potential_lines,
                f"chosen leverage: {leverage}x",
                f"leverage reason: {leverage_reason}",
                f"current P/L: 0.00{currency_suffix}",
                "current P/L %: 0.0000%",
                "current P/L % leveraged: 0.0000%",
                f"equity: {equity:.2f}{currency_suffix} deposit: {deposit:.2f}{currency_suffix}",
                f"final trading day: {final_day or '-'}",
                f"weekly exit: {due_reason} (due={due})",
                f"last exit: {self.state.last_exit_reason or '-'}",
                f"build: {BUILD_ID}",
                "======================================================",
            ]
            return "\n" + "\n".join(lines) + "\n"

'''

CHOOSE_LEVERAGE = r'''    def choose_leverage(self) -> int:
        return self.leverage_decision()[0]

'''


def replace_function(text: str, function_name: str, next_function_name: str, replacement: str) -> str:
    start_marker = f"    def {function_name}("
    end_marker = f"    def {next_function_name}("
    start = text.find(start_marker)
    if start < 0:
        raise RuntimeError(f"Could not find {start_marker.strip()}")
    end = text.find(end_marker, start)
    if end < 0:
        raise RuntimeError(f"Could not find following {end_marker.strip()}")
    return text[:start] + replacement + text[end:]


def patch(source: str) -> str:
    if V40_BUILD not in source:
        raise RuntimeError("Input is not the expected v40 file; BUILD_ID was not found")
    if "def potential_position_preview(" in source:
        raise RuntimeError("Input already contains the v41 potential-position preview")

    source = source.replace(V40_BUILD, V41_BUILD, 1)
    source = source.replace('User-Agent": "OPPW-MT5-Publisher/40"', 'User-Agent": "OPPW-MT5-Publisher/41"')
    source = source.replace("* EXECUTOR automatically publishes when no PUBLISHER heartbeat is active.\n", "* EXECUTOR automatically publishes when no PUBLISHER heartbeat is active.\n* Flat status reports the next potential volume, required margin deposit and leverage decision.\n", 1)

    format_start = source.find("    def format_status(")
    if format_start < 0:
        raise RuntimeError("Could not find format_status")
    source = source[:format_start] + HELPERS + source[format_start:]

    format_start = source.find("    def format_status(")
    emit_start = source.find("    def emit_status(", format_start)
    if emit_start < 0:
        raise RuntimeError("Could not find emit_status after format_status")
    segment = source[format_start:emit_start]
    flat_start = segment.find("        if position is None:\n")
    try_start = segment.find("        try:\n", flat_start)
    if flat_start < 0 or try_start < 0:
        raise RuntimeError("Could not locate the flat-position block inside format_status")
    segment = segment[:flat_start] + FLAT_BLOCK + segment[try_start:]
    source = source[:format_start] + segment + source[emit_start:]

    source = replace_function(source, "choose_leverage", "hard_sl_ratio", CHOOSE_LEVERAGE)

    mobile_anchor = '            "position": position_payload,\n            "conditions": conditions,'
    mobile_replacement = '            "position": position_payload,\n            "potentialPosition": self.potential_position_preview() if position is None else None,\n            "conditions": conditions,'
    if mobile_anchor not in source:
        raise RuntimeError("Could not find mobile snapshot position anchor")
    source = source.replace(mobile_anchor, mobile_replacement, 1)

    ast.parse(source)
    return source


def main() -> int:
    parser = argparse.ArgumentParser(description="Build full OPPW MT5 v41 from the exact v40 source")
    parser.add_argument("input", nargs="?", default="oppw_mt5_continuous.py", help="Path to the existing v40 script")
    parser.add_argument("output", nargs="?", default="oppw_mt5_continuous_v41.py", help="Path for the generated full v41 script")
    args = parser.parse_args()

    input_path = Path(args.input).resolve()
    output_path = Path(args.output).resolve()
    source = input_path.read_text(encoding="utf-8")
    result = patch(source)
    output_path.write_text(result, encoding="utf-8")
    print(f"Created {output_path}")
    print("Validated with Python ast.parse()")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
