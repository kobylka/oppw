import MetaTrader5 as mt5

if not mt5.initialize(
    path=r"C:\Program Files\MetaTrader 5\terminal64.exe",
    login=REMOVED_DEMO_ACCOUNT_ID,
    password="REMOVED_ROTATED_MT5_PASSWORD",
    server="BOSSAFX-Demo"
):
    raise RuntimeError(f"MT5 initialization failed: {mt5.last_error()}")

positions = mt5.positions_get(symbol="US100")

print(positions)