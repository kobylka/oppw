"""Shared causal loss-control decisions for OPPW research backtests."""

LOSS_CONTROL_ENTER = "ENTER"
LOSS_CONTROL_SKIP_ARITHMETIC = "SKIP_ARITHMETIC"
LOSS_CONTROL_DEFER_TUESDAY = "DEFER_TUESDAY"
LOSS_CONTROL_SKIP_GAP_MOMENTUM = "SKIP_GAP_MOMENTUM"
LOSS_CONTROL_SKIP_PREMARKET_LOW = "SKIP_PREMARKET_LOW"


def arithmetic_loss_control_trigger(outcomes, lookback, threshold=0.02):
    """Return whether the arithmetic sum of the latest outcomes breached."""
    if lookback is None:
        return False
    if lookback <= 0:
        raise ValueError("lookback must be positive")
    if threshold <= 0:
        raise ValueError("threshold must be positive")
    return (
        len(outcomes) >= lookback
        and sum(outcomes[-lookback:]) <= -threshold + 1e-12
    )


def opening_gap_momentum_trigger(
    cash_open,
    previous_cash_close,
    momentum20,
    gap_threshold=0.01,
    momentum_threshold=-0.005,
):
    """Return whether the causal cash-gap and prior-momentum gate fired."""
    if previous_cash_close <= 0 or momentum20 is None:
        return False
    gap = cash_open / previous_cash_close - 1.0
    return (
        gap >= gap_threshold - 1e-12
        and momentum20 <= momentum_threshold + 1e-12
    )


def normalized_tuesday_reentry(
    friday_close,
    tuesday_daily_open,
    tolerance=0.005,
):
    """Return whether Tuesday's adjusted open is within tolerance of Friday."""
    if friday_close <= 0:
        return False
    return abs(tuesday_daily_open / friday_close - 1.0) <= tolerance + 1e-12


def premarket_closes_near_low(
    premarket_open,
    premarket_high,
    premarket_low,
    premarket_close,
    minimum_range=0.008,
    maximum_close_location=0.15,
):
    """Return whether a sufficiently wide premarket closes near its low."""
    if premarket_open <= 0 or premarket_high <= premarket_low:
        return False
    premarket_range = (premarket_high - premarket_low) / premarket_open
    close_location = (
        (premarket_close - premarket_low)
        / (premarket_high - premarket_low)
    )
    return (
        premarket_range >= minimum_range - 1e-12
        and close_location <= maximum_close_location + 1e-12
    )


def loss_control_entry_decision(
    outcomes,
    lookback,
    cash_open,
    previous_cash_close,
    momentum20,
    is_monday,
    arithmetic_threshold=0.02,
    gap_threshold=0.01,
    momentum_threshold=-0.005,
    premarket_low=False,
    gap_momentum_enabled=None,
):
    """Apply arithmetic, premarket-low, then gap/momentum priorities."""
    if arithmetic_loss_control_trigger(outcomes, lookback, arithmetic_threshold):
        return LOSS_CONTROL_SKIP_ARITHMETIC
    if premarket_low:
        return LOSS_CONTROL_SKIP_PREMARKET_LOW
    if gap_momentum_enabled is None:
        gap_momentum_enabled = lookback is not None
    if not gap_momentum_enabled:
        return LOSS_CONTROL_ENTER
    if opening_gap_momentum_trigger(
        cash_open,
        previous_cash_close,
        momentum20,
        gap_threshold,
        momentum_threshold,
    ):
        if is_monday:
            return LOSS_CONTROL_DEFER_TUESDAY
        return LOSS_CONTROL_SKIP_GAP_MOMENTUM
    return LOSS_CONTROL_ENTER
