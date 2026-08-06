#!/usr/bin/env python3

import argparse
import csv
import math
import random
import statistics
from pathlib import Path


DEFAULT_INITIAL_BALANCE = 10_000.0
DEFAULT_BLOCK_SIZE = 8
DEFAULT_SIM_WEEKS = 367
DEFAULT_SIMULATIONS = 100_000
DEFAULT_TOPUP_AMOUNT = 0.0
DEFAULT_TOPUP_INTERVAL = 4
DEFAULT_TOPUP_STOP_BALANCE = 1_000_000.0
DEFAULT_TAX_RATE = 19.0
DEFAULT_TARGET_BALANCE = 10_000_000.0
DEFAULT_TARGET_WEEKLY_GROWTH = 0.01
DEFAULT_LEVERAGE = 1.0

TARGETS = [
    100_000,
    250_000,
    500_000,
    1_000_000,
    2_000_000,
    5_000_000,
    10_000_000,
    20_000_000,
    50_000_000,
    100_000_000,
]


def parse_arguments():
    parser = argparse.ArgumentParser(
        description=(
            "Monte Carlo simulator using a circular moving-block bootstrap "
            "of historical weekly decimal returns."
        )
    )

    parser.add_argument(
        "input",
        help=(
            "Text file containing one weekly decimal return per line. "
            "Example: 0.01 means +1%."
        ),
    )

    parser.add_argument(
        "--block",
        type=int,
        default=DEFAULT_BLOCK_SIZE,
        help=f"Block size in weeks, default: {DEFAULT_BLOCK_SIZE}",
    )

    parser.add_argument(
        "--weeks",
        type=int,
        default=DEFAULT_SIM_WEEKS,
        help=f"Weeks per simulation, default: {DEFAULT_SIM_WEEKS}",
    )

    parser.add_argument(
        "--simulations",
        type=int,
        default=DEFAULT_SIMULATIONS,
        help=f"Number of simulations, default: {DEFAULT_SIMULATIONS}",
    )

    parser.add_argument(
        "--initial",
        type=float,
        default=DEFAULT_INITIAL_BALANCE,
        help=f"Initial balance, default: {DEFAULT_INITIAL_BALANCE}",
    )

    parser.add_argument(
        "--topup",
        type=float,
        default=DEFAULT_TOPUP_AMOUNT,
        help=f"Periodic top-up amount, default: {DEFAULT_TOPUP_AMOUNT}",
    )

    parser.add_argument(
        "--topup-interval",
        type=int,
        default=DEFAULT_TOPUP_INTERVAL,
        help=f"Top-up every N weeks, default: {DEFAULT_TOPUP_INTERVAL}",
    )

    parser.add_argument(
        "--topup-stop-balance",
        type=float,
        default=DEFAULT_TOPUP_STOP_BALANCE,
        help=(
            "Only apply periodic top-ups while the current balance is below "
            f"this value, default: {DEFAULT_TOPUP_STOP_BALANCE}"
        ),
    )

    parser.add_argument(
        "--tax",
        type=float,
        default=DEFAULT_TAX_RATE,
        help=f"Annual tax rate in percent, default: {DEFAULT_TAX_RATE}",
    )

    parser.add_argument(
        "--leverage",
        type=float,
        default=DEFAULT_LEVERAGE,
        help=(
            "Multiplier applied to every decimal weekly return. "
            f"Default: {DEFAULT_LEVERAGE}"
        ),
    )

    parser.add_argument(
        "--bayesian-parameters",
        action="store_true",
        help=(
            "Draw one posterior weekly mean and standard deviation "
            "for each simulation path"
        ),
    )

    parser.add_argument(
        "--target",
        type=float,
        default=DEFAULT_TARGET_BALANCE,
        help=f"Target balance for OPI, default: {DEFAULT_TARGET_BALANCE}",
    )

    parser.add_argument(
        "--target-weekly-growth",
        type=float,
        default=DEFAULT_TARGET_WEEKLY_GROWTH * 100.0,
        help=(
            "Weekly target-path growth in percent. "
            f"Default: {DEFAULT_TARGET_WEEKLY_GROWTH * 100.0}"
        ),
    )

    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Optional random seed for reproducible results",
    )

    parser.add_argument(
        "--export",
        action="store_true",
        help="Export simulation data to CSV files",
    )

    parser.add_argument(
        "--output-dir",
        default="monte_carlo_output",
        help="CSV output directory, default: monte_carlo_output",
    )

    parser.add_argument(
        "--no-final-tax",
        action="store_true",
        help=(
            "Do not apply tax to the unfinished final tax year. "
            "By default, the final partial-year gain is realized and taxed."
        ),
    )

    return parser.parse_args()


def validate_arguments(args):
    if args.block < 1:
        raise ValueError("--block must be at least 1")

    if args.weeks < 1:
        raise ValueError("--weeks must be at least 1")

    if args.simulations < 1:
        raise ValueError("--simulations must be at least 1")

    if args.initial <= 0:
        raise ValueError("--initial must be greater than 0")

    if args.topup < 0:
        raise ValueError("--topup cannot be negative")

    if args.topup > 0 and args.topup_interval < 1:
        raise ValueError(
            "--topup-interval must be at least 1 when top-ups are enabled"
        )

    if args.topup_stop_balance < 0:
        raise ValueError("--topup-stop-balance cannot be negative")

    if args.tax < 0:
        raise ValueError("--tax cannot be negative")

    if args.leverage <= 0:
        raise ValueError("--leverage must be greater than 0")

    if args.target <= 0:
        raise ValueError("--target must be greater than 0")

    if args.target_weekly_growth <= -100:
        raise ValueError(
            "--target-weekly-growth must be greater than -100%"
        )


def load_returns(filename):
    """
    Load decimal weekly returns.

    Examples:
        0.01   means +1%
        -0.02  means -2%
        0.5312 means +53.12%

    Empty lines and lines beginning with # are ignored.
    """

    path = Path(filename)

    if not path.exists():
        raise FileNotFoundError(
            f"Input file does not exist: {path}"
        )

    if not path.is_file():
        raise ValueError(
            f"Input path is not a file: {path}"
        )

    returns = []

    with path.open("r", encoding="utf-8-sig") as file:
        for line_number, raw_line in enumerate(
            file,
            start=1,
        ):
            line = raw_line.strip()

            if not line or line.startswith("#"):
                continue

            if line.endswith("%"):
                raise ValueError(
                    f"Line {line_number} contains a percent sign. "
                    "This script expects decimal returns, where 0.01 means 1%."
                )

            line = line.replace(",", ".")

            try:
                value = float(line)
            except ValueError as exc:
                raise ValueError(
                    f"Invalid return on line {line_number}: "
                    f"{raw_line.rstrip()!r}"
                ) from exc

            if not math.isfinite(value):
                raise ValueError(
                    f"Non-finite return on line {line_number}: {value}"
                )

            if value <= -1.0:
                raise ValueError(
                    f"Weekly return must be greater than -1.0 "
                    f"(-100%) on line {line_number}"
                )

            returns.append(value)

    if not returns:
        raise ValueError(
            "The input file contains no valid weekly returns"
        )

    return returns


def build_circular_blocks(returns, block_size):
    """
    Build circular sliding blocks.

    For:
        A B C D E

    With block size 3:
        A B C
        B C D
        C D E
        D E A
        E A B
    """

    if block_size < 1:
        raise ValueError(
            "Block size must be at least 1"
        )

    if block_size > len(returns):
        raise ValueError(
            f"Block size {block_size} exceeds history length "
            f"{len(returns)}"
        )

    history_length = len(returns)
    blocks = []

    for start in range(history_length):
        block = [
            returns[(start + offset) % history_length]
            for offset in range(block_size)
        ]

        blocks.append(block)

    return blocks


def geometric_mean_return(returns):
    growth_product = math.prod(
        1.0 + weekly_return
        for weekly_return in returns
    )

    return (
        growth_product ** (1.0 / len(returns))
        - 1.0
    )


def print_dataset_information(
    returns,
    blocks,
    block_size,
    leverage,
):
    positive_weeks = sum(
        1
        for value in returns
        if value > 0
    )

    negative_weeks = sum(
        1
        for value in returns
        if value < 0
    )

    flat_weeks = (
        len(returns)
        - positive_weeks
        - negative_weeks
    )

    leveraged_returns = [
        value * leverage
        for value in returns
    ]

    print()
    print("=" * 60)
    print("DATASET")
    print("=" * 60)

    print(f"Weeks in history          : {len(returns):,}")
    print(f"Block size                : {block_size}")
    print(f"Blocks created            : {len(blocks):,}")

    print(
        f"Raw arithmetic mean       : "
        f"{statistics.mean(returns) * 100:+.4f}%"
    )

    print(
        f"Raw geometric mean        : "
        f"{geometric_mean_return(returns) * 100:+.4f}%"
    )

    print(
        f"Raw median week           : "
        f"{statistics.median(returns) * 100:+.4f}%"
    )

    print(
        f"Raw best week             : "
        f"{max(returns) * 100:+.4f}%"
    )

    print(
        f"Raw worst week            : "
        f"{min(returns) * 100:+.4f}%"
    )

    if len(returns) >= 2:
        print(
            f"Raw weekly stdev          : "
            f"{statistics.stdev(returns) * 100:.4f}%"
        )
    else:
        print("Raw weekly stdev          : N/A")

    if leverage != 1.0:
        print()
        print(f"Return leverage           : {leverage:.4f}x")

        print(
            f"Leveraged arithmetic mean : "
            f"{statistics.mean(leveraged_returns) * 100:+.4f}%"
        )

        print(
            f"Leveraged median week     : "
            f"{statistics.median(leveraged_returns) * 100:+.4f}%"
        )

        print(
            f"Leveraged best week       : "
            f"{max(leveraged_returns) * 100:+.4f}%"
        )

        print(
            f"Leveraged worst week      : "
            f"{min(leveraged_returns) * 100:+.4f}%"
        )

        if len(leveraged_returns) >= 2:
            print(
                f"Leveraged weekly stdev    : "
                f"{statistics.stdev(leveraged_returns) * 100:.4f}%"
            )

    print()
    print(f"Positive weeks            : {positive_weeks:,}")
    print(f"Negative weeks            : {negative_weeks:,}")
    print(f"Flat weeks                : {flat_weeks:,}")


def apply_topup(balance, amount):
    if amount > 0:
        balance += amount

    return balance


def apply_tax(
    balance,
    year_start_balance,
    year_topups,
    tax_rate,
):
    """
    Apply tax only to strategy-generated profit.

    Top-ups are excluded from taxable profit.
    """

    taxable_profit = (
        balance
        - year_start_balance
        - year_topups
    )

    if taxable_profit <= 0 or tax_rate <= 0:
        return balance, 0.0, balance, 0.0

    tax_paid = (
        taxable_profit
        * tax_rate
        / 100.0
    )

    balance -= tax_paid

    return balance, tax_paid, balance, 0.0


def calculate_drawdown(balance, equity_high):
    if balance > equity_high:
        equity_high = balance

    if equity_high <= 0:
        return 0.0, equity_high

    drawdown = (
        1.0
        - balance / equity_high
    )

    return drawdown, equity_high


def update_underwater_stats(
    current_drawdown,
    underwater_weeks,
    longest_underwater,
):
    if current_drawdown > 0:
        underwater_weeks += 1
    else:
        longest_underwater = max(
            longest_underwater,
            underwater_weeks,
        )

        underwater_weeks = 0

    return underwater_weeks, longest_underwater


def percentile(values, p):
    if not values:
        raise ValueError(
            "Cannot calculate percentile of an empty sequence"
        )

    if not 0 <= p <= 100:
        raise ValueError(
            "Percentile must be between 0 and 100"
        )

    if len(values) == 1:
        return values[0]

    sorted_values = sorted(values)

    position = (
        (len(sorted_values) - 1)
        * p
        / 100.0
    )

    lower_index = math.floor(position)
    upper_index = math.ceil(position)

    if lower_index == upper_index:
        return sorted_values[lower_index]

    lower_value = sorted_values[lower_index]
    upper_value = sorted_values[upper_index]
    weight = position - lower_index

    return (
        lower_value
        + (upper_value - lower_value)
        * weight
    )


def cagr(
    initial_balance,
    final_balance,
    weeks,
):
    years = weeks / 52.0

    if years <= 0:
        return float("nan")

    if initial_balance <= 0:
        return float("nan")

    if final_balance <= 0:
        return -1.0

    return (
        (final_balance / initial_balance)
        ** (1.0 / years)
        - 1.0
    )


def probability(values, threshold):
    if not values:
        return 0.0

    hits = sum(
        1
        for value in values
        if value >= threshold
    )

    return (
        100.0
        * hits
        / len(values)
    )


def rolling_statistics(values):
    if not values:
        raise ValueError(
            "Cannot calculate statistics for an empty sequence"
        )

    return {
        "mean": statistics.mean(values),
        "median": statistics.median(values),
        "stdev": (
            statistics.stdev(values)
            if len(values) >= 2
            else 0.0
        ),
        "min": min(values),
        "max": max(values),
        "p01": percentile(values, 0.1),
        "p1": percentile(values, 1),
        "p5": percentile(values, 5),
        "p10": percentile(values, 10),
        "p25": percentile(values, 25),
        "p50": percentile(values, 50),
        "p75": percentile(values, 75),
        "p90": percentile(values, 90),
        "p95": percentile(values, 95),
        "p99": percentile(values, 99),
        "p999": percentile(values, 99.9),
    }


def print_progress(current, total):
    percent = (
        100.0
        * current
        / total
    )

    print(
        f"\r{current:,}/{total:,} "
        f"({percent:6.2f}%)",
        end="",
        flush=True,
    )


def finish_progress():
    print()


def required_balance(
    target_balance,
    weeks_remaining,
    weekly_growth=0.01,
):
    if target_balance <= 0:
        raise ValueError(
            "Target balance must be greater than 0"
        )

    if weeks_remaining < 0:
        raise ValueError(
            "Weeks remaining cannot be negative"
        )

    if weekly_growth <= -1.0:
        raise ValueError(
            "Weekly growth must be greater than -100%"
        )

    return (
        target_balance
        / (
            (1.0 + weekly_growth)
            ** weeks_remaining
        )
    )


def calculate_ulcer_index(drawdown_curve):
    if not drawdown_curve:
        return 0.0

    mean_squared_drawdown = statistics.mean(
        drawdown * drawdown
        for drawdown in drawdown_curve
    )

    return math.sqrt(
        mean_squared_drawdown
    )


def apply_final_partial_year_tax(
    balance,
    year_start_balance,
    year_topups,
    tax_rate,
    taxes_paid,
):
    """
    Realize and tax profit from an unfinished final tax year.
    """

    (
        balance,
        final_tax_paid,
        year_start_balance,
        year_topups,
    ) = apply_tax(
        balance=balance,
        year_start_balance=year_start_balance,
        year_topups=year_topups,
        tax_rate=tax_rate,
    )

    taxes_paid += final_tax_paid

    return (
        balance,
        taxes_paid,
        year_start_balance,
        year_topups,
        final_tax_paid,
    )


def sample_posterior_mean_stdev(
    historical_mean,
    historical_stdev,
    sample_size,
):
    """
    Draw one plausible true weekly mean and standard deviation.

    Uses the Normal-Inverse-Chi-Squared posterior corresponding
    to a weak/reference prior.
    """

    if sample_size < 2:
        raise ValueError(
            "At least 2 historical returns are required"
        )

    if historical_stdev < 0:
        raise ValueError(
            "Historical standard deviation cannot be negative"
        )

    if historical_stdev == 0:
        return historical_mean, 0.0

    degrees_of_freedom = sample_size - 1

    chi_square_draw = random.gammavariate(
        degrees_of_freedom / 2.0,
        2.0,
    )

    sampled_variance = (
        degrees_of_freedom
        * historical_stdev ** 2
        / chi_square_draw
    )

    sampled_stdev = math.sqrt(
        sampled_variance
    )

    sampled_mean = random.gauss(
        historical_mean,
        sampled_stdev / math.sqrt(sample_size),
    )

    return sampled_mean, sampled_stdev


def adjust_return_for_posterior(
    raw_return,
    historical_mean,
    historical_stdev,
    sampled_mean,
    sampled_stdev,
):
    """
    Preserve the standardized shape of the historical return
    while replacing its mean and standard deviation with one
    posterior draw.
    """

    if historical_stdev == 0:
        return sampled_mean

    z_score = (
        raw_return
        - historical_mean
    ) / historical_stdev

    return (
        sampled_mean
        + z_score * sampled_stdev
    )


def simulate_one_path(
    blocks,
    simulation_weeks,
    initial_balance,
    tax_rate,
    topup_amount,
    topup_interval,
    topup_stop_balance,
    leverage,
    apply_final_tax,
    bayesian_parameters,
    historical_mean,
    historical_stdev,
    historical_sample_size,
):
    balance = initial_balance

    equity_curve = [balance]
    drawdown_curve = [0.0]
    simulated_returns = []

    year_start_balance = balance
    year_topups = 0.0
    taxes_paid = 0.0
    total_topups = 0.0

    equity_high = balance
    current_drawdown = 0.0
    max_drawdown = 0.0

    underwater_weeks = 0
    longest_underwater = 0

    weeks_generated = 0
    block_size = len(blocks[0])
    account_ruined = False

    first_target_hit_week = {
        target: None
        for target in TARGETS
    }

    if bayesian_parameters:
        sampled_mean, sampled_stdev = (
            sample_posterior_mean_stdev(
                historical_mean=historical_mean,
                historical_stdev=historical_stdev,
                sample_size=historical_sample_size,
            )
        )
    else:
        sampled_mean = historical_mean
        sampled_stdev = historical_stdev

    while weeks_generated < simulation_weeks:
        block = random.choice(blocks)

        remaining = (
            simulation_weeks
            - weeks_generated
        )

        weeks_to_use = min(
            block_size,
            remaining,
        )

        for raw_weekly_return in block[:weeks_to_use]:
            posterior_adjusted_return = (
                adjust_return_for_posterior(
                    raw_return=raw_weekly_return,
                    historical_mean=historical_mean,
                    historical_stdev=historical_stdev,
                    sampled_mean=sampled_mean,
                    sampled_stdev=sampled_stdev,
                )
            )

            leveraged_return = (
                posterior_adjusted_return
                * leverage
            )

            simulated_returns.append(
                leveraged_return
            )

            weeks_generated += 1

            if leveraged_return <= -1.0:
                balance = 0.0
                account_ruined = True
            elif not account_ruined:
                balance *= (
                    1.0
                    + leveraged_return
                )

            if (
                topup_amount > 0
                and topup_interval > 0
                and weeks_generated % topup_interval == 0
                and balance < topup_stop_balance
            ):
                balance = apply_topup(
                    balance,
                    topup_amount,
                )

                year_topups += topup_amount
                total_topups += topup_amount

                if balance > 0:
                    account_ruined = False

            if weeks_generated % 52 == 0:
                (
                    balance,
                    tax_paid,
                    year_start_balance,
                    year_topups,
                ) = apply_tax(
                    balance=balance,
                    year_start_balance=year_start_balance,
                    year_topups=year_topups,
                    tax_rate=tax_rate,
                )

                taxes_paid += tax_paid

            (
                current_drawdown,
                equity_high,
            ) = calculate_drawdown(
                balance,
                equity_high,
            )

            max_drawdown = max(
                max_drawdown,
                current_drawdown,
            )

            (
                underwater_weeks,
                longest_underwater,
            ) = update_underwater_stats(
                current_drawdown,
                underwater_weeks,
                longest_underwater,
            )

            equity_curve.append(balance)
            drawdown_curve.append(
                current_drawdown
            )

            for target in TARGETS:
                if (
                    first_target_hit_week[target] is None
                    and balance >= target
                ):
                    first_target_hit_week[target] = (
                        weeks_generated
                    )

    final_partial_tax_paid = 0.0

    if (
        apply_final_tax
        and simulation_weeks % 52 != 0
    ):
        (
            balance,
            taxes_paid,
            year_start_balance,
            year_topups,
            final_partial_tax_paid,
        ) = apply_final_partial_year_tax(
            balance=balance,
            year_start_balance=year_start_balance,
            year_topups=year_topups,
            tax_rate=tax_rate,
            taxes_paid=taxes_paid,
        )

        equity_curve[-1] = balance

        (
            current_drawdown,
            equity_high,
        ) = calculate_drawdown(
            balance,
            equity_high,
        )

        drawdown_curve[-1] = current_drawdown

        max_drawdown = max(
            max_drawdown,
            current_drawdown,
        )

    longest_underwater = max(
        longest_underwater,
        underwater_weeks,
    )

    total_return = (
        balance / initial_balance
        - 1.0
    ) * 100.0

    annual_cagr = (
        cagr(
            initial_balance=initial_balance,
            final_balance=balance,
            weeks=simulation_weeks,
        )
        * 100.0
    )

    ulcer_index = calculate_ulcer_index(
        drawdown_curve
    )

    return {
        "final_balance": balance,
        "total_return": total_return,
        "cagr": annual_cagr,
        "max_drawdown": max_drawdown,
        "longest_underwater": longest_underwater,
        "taxes_paid": taxes_paid,
        "final_partial_tax_paid": final_partial_tax_paid,
        "total_topups": total_topups,
        "ulcer_index": ulcer_index,
        "equity_curve": equity_curve,
        "drawdown_curve": drawdown_curve,
        "simulated_returns": simulated_returns,
        "first_target_hit_week": first_target_hit_week,
        "account_ruined": account_ruined,
        "sampled_mean": sampled_mean,
        "sampled_stdev": sampled_stdev,
        "weeks": simulation_weeks,
    }


def run_monte_carlo(
    blocks,
    simulations,
    simulation_weeks,
    initial_balance,
    tax_rate,
    topup_amount,
    topup_interval,
    topup_stop_balance,
    leverage,
    apply_final_tax,
    bayesian_parameters,
    historical_mean,
    historical_stdev,
    historical_sample_size,
):
    final_balances = []
    cagrs = []
    total_returns = []
    max_drawdowns = []
    longest_underwater = []
    taxes_paid = []
    final_partial_taxes_paid = []
    total_topups = []
    ulcer_indexes = []
    account_ruined_flags = []
    sampled_means = []
    sampled_stdevs = []

    equity_curves = []
    drawdown_curves = []
    simulated_returns = []
    first_target_hit_weeks = []

    print()
    print("=" * 60)
    print("RUNNING MONTE CARLO")
    print("=" * 60)

    progress_interval = max(
        1,
        simulations // 100,
    )

    for simulation_index in range(simulations):
        result = simulate_one_path(
            blocks=blocks,
            simulation_weeks=simulation_weeks,
            initial_balance=initial_balance,
            tax_rate=tax_rate,
            topup_amount=topup_amount,
            topup_interval=topup_interval,
            topup_stop_balance=topup_stop_balance,
            leverage=leverage,
            apply_final_tax=apply_final_tax,
            bayesian_parameters=bayesian_parameters,
            historical_mean=historical_mean,
            historical_stdev=historical_stdev,
            historical_sample_size=historical_sample_size,
        )

        final_balances.append(
            result["final_balance"]
        )

        cagrs.append(
            result["cagr"]
        )

        total_returns.append(
            result["total_return"]
        )

        max_drawdowns.append(
            result["max_drawdown"]
        )

        longest_underwater.append(
            result["longest_underwater"]
        )

        taxes_paid.append(
            result["taxes_paid"]
        )

        final_partial_taxes_paid.append(
            result["final_partial_tax_paid"]
        )

        total_topups.append(
            result["total_topups"]
        )

        ulcer_indexes.append(
            result["ulcer_index"]
        )

        account_ruined_flags.append(
            result["account_ruined"]
        )

        sampled_means.append(
            result["sampled_mean"]
        )

        sampled_stdevs.append(
            result["sampled_stdev"]
        )

        equity_curves.append(
            result["equity_curve"]
        )

        drawdown_curves.append(
            result["drawdown_curve"]
        )

        simulated_returns.append(
            result["simulated_returns"]
        )

        first_target_hit_weeks.append(
            result["first_target_hit_week"]
        )

        completed = simulation_index + 1

        if (
            completed % progress_interval == 0
            or completed == simulations
        ):
            print_progress(
                completed,
                simulations,
            )

    finish_progress()

    return {
        "final_balances": final_balances,
        "cagrs": cagrs,
        "total_returns": total_returns,
        "max_drawdowns": max_drawdowns,
        "longest_underwater": longest_underwater,
        "taxes_paid": taxes_paid,
        "final_partial_taxes_paid": final_partial_taxes_paid,
        "total_topups": total_topups,
        "ulcer_indexes": ulcer_indexes,
        "account_ruined_flags": account_ruined_flags,
        "sampled_means": sampled_means,
        "sampled_stdevs": sampled_stdevs,
        "equity_curves": equity_curves,
        "drawdown_curves": drawdown_curves,
        "simulated_returns": simulated_returns,
        "first_target_hit_weeks": first_target_hit_weeks,
    }


def print_percentile_section(
    title,
    stats,
    suffix="",
    multiplier=1.0,
):
    print()
    print(title)
    print("-" * 60)

    print(
        f"Mean        : "
        f"{stats['mean'] * multiplier:,.2f}{suffix}"
    )

    print(
        f"Median      : "
        f"{stats['median'] * multiplier:,.2f}{suffix}"
    )

    print(
        f"Std Dev     : "
        f"{stats['stdev'] * multiplier:,.2f}{suffix}"
    )

    print(
        f"Minimum     : "
        f"{stats['min'] * multiplier:,.2f}{suffix}"
    )

    print(
        f"P0.1        : "
        f"{stats['p01'] * multiplier:,.2f}{suffix}"
    )

    print(
        f"P1          : "
        f"{stats['p1'] * multiplier:,.2f}{suffix}"
    )

    print(
        f"P5          : "
        f"{stats['p5'] * multiplier:,.2f}{suffix}"
    )

    print(
        f"P10         : "
        f"{stats['p10'] * multiplier:,.2f}{suffix}"
    )

    print(
        f"P25         : "
        f"{stats['p25'] * multiplier:,.2f}{suffix}"
    )

    print(
        f"P50         : "
        f"{stats['p50'] * multiplier:,.2f}{suffix}"
    )

    print(
        f"P75         : "
        f"{stats['p75'] * multiplier:,.2f}{suffix}"
    )

    print(
        f"P90         : "
        f"{stats['p90'] * multiplier:,.2f}{suffix}"
    )

    print(
        f"P95         : "
        f"{stats['p95'] * multiplier:,.2f}{suffix}"
    )

    print(
        f"P99         : "
        f"{stats['p99'] * multiplier:,.2f}{suffix}"
    )

    print(
        f"P99.9       : "
        f"{stats['p999'] * multiplier:,.2f}{suffix}"
    )

    print(
        f"Maximum     : "
        f"{stats['max'] * multiplier:,.2f}{suffix}"
    )


def print_target_hit_statistics(results):
    hit_data = results["first_target_hit_weeks"]
    simulation_count = len(hit_data)

    print()
    print("TARGET-HIT STATISTICS")
    print("-" * 60)

    for target in TARGETS:
        hit_weeks = [
            item[target]
            for item in hit_data
            if item[target] is not None
        ]

        hit_probability = (
            100.0
            * len(hit_weeks)
            / simulation_count
        )

        if hit_weeks:
            print(
                f"{target:>14,.0f} | "
                f"hit: {hit_probability:6.2f}% | "
                f"median week: "
                f"{statistics.median(hit_weeks):7.1f} | "
                f"P10: {percentile(hit_weeks, 10):7.1f} | "
                f"P90: {percentile(hit_weeks, 90):7.1f}"
            )
        else:
            print(
                f"{target:>14,.0f} | "
                f"hit: {hit_probability:6.2f}% | "
                f"never reached"
            )


def print_statistics(results):
    print()
    print("=" * 60)
    print("MONTE CARLO SUMMARY")
    print("=" * 60)

    print_percentile_section(
        title="FINAL BALANCE",
        stats=rolling_statistics(
            results["final_balances"]
        ),
    )

    print_percentile_section(
        title="CAGR",
        stats=rolling_statistics(
            results["cagrs"]
        ),
        suffix="%",
    )

    print_percentile_section(
        title="TOTAL RETURN",
        stats=rolling_statistics(
            results["total_returns"]
        ),
        suffix="%",
    )

    print_percentile_section(
        title="MAXIMUM DRAWDOWN",
        stats=rolling_statistics(
            results["max_drawdowns"]
        ),
        suffix="%",
        multiplier=100.0,
    )

    print_percentile_section(
        title="LONGEST UNDERWATER PERIOD",
        stats=rolling_statistics(
            results["longest_underwater"]
        ),
        suffix=" weeks",
    )

    print_percentile_section(
        title="ULCER INDEX",
        stats=rolling_statistics(
            results["ulcer_indexes"]
        ),
        suffix="%",
        multiplier=100.0,
    )

    print_percentile_section(
        title="TOTAL TAXES PAID",
        stats=rolling_statistics(
            results["taxes_paid"]
        ),
    )

    print_percentile_section(
        title="FINAL PARTIAL-YEAR TAX",
        stats=rolling_statistics(
            results["final_partial_taxes_paid"]
        ),
    )

    print_percentile_section(
        title="POSTERIOR WEEKLY MEAN",
        stats=rolling_statistics(
            results["sampled_means"]
        ),
        suffix="%",
        multiplier=100.0,
    )

    print_percentile_section(
        title="POSTERIOR WEEKLY STANDARD DEVIATION",
        stats=rolling_statistics(
            results["sampled_stdevs"]
        ),
        suffix="%",
        multiplier=100.0,
    )

    ruined_count = sum(
        1
        for ruined in results["account_ruined_flags"]
        if ruined
    )

    ruined_probability = (
        100.0
        * ruined_count
        / len(results["account_ruined_flags"])
    )

    print()
    print("ACCOUNT RUIN")
    print("-" * 60)

    print(
        f"Paths ending ruined : "
        f"{ruined_count:,} / "
        f"{len(results['account_ruined_flags']):,}"
    )

    print(
        f"Probability         : "
        f"{ruined_probability:.2f}%"
    )

    print()
    print("FINAL-BALANCE TARGET PROBABILITIES")
    print("-" * 60)

    for target in TARGETS:
        target_probability = probability(
            results["final_balances"],
            target,
        )

        print(
            f"{target:>14,.0f} : "
            f"{target_probability:6.2f}%"
        )

    print_target_hit_statistics(results)


def calculate_weekly_statistics(
    results,
    target_balance=DEFAULT_TARGET_BALANCE,
    weekly_growth=DEFAULT_TARGET_WEEKLY_GROWTH,
):
    equity_curves = results["equity_curves"]
    drawdown_curves = results["drawdown_curves"]

    if not equity_curves:
        raise ValueError(
            "No equity curves available"
        )

    curve_length = len(equity_curves[0])

    if any(
        len(curve) != curve_length
        for curve in equity_curves
    ):
        raise ValueError(
            "Equity curves do not all have the same length"
        )

    if any(
        len(curve) != curve_length
        for curve in drawdown_curves
    ):
        raise ValueError(
            "Drawdown curves do not all have the same length"
        )

    weekly_statistics = []

    print()
    print("=" * 60)
    print("CALCULATING WEEKLY STATISTICS")
    print("=" * 60)

    progress_interval = max(
        1,
        curve_length // 100,
    )

    for week in range(curve_length):
        balances = [
            curve[week]
            for curve in equity_curves
        ]

        drawdowns = [
            curve[week]
            for curve in drawdown_curves
        ]

        balance_stats = rolling_statistics(
            balances
        )

        drawdown_stats = rolling_statistics(
            drawdowns
        )

        weeks_remaining = (
            curve_length
            - week
            - 1
        )

        required = required_balance(
            target_balance=target_balance,
            weeks_remaining=weeks_remaining,
            weekly_growth=weekly_growth,
        )

        on_track_count = sum(
            1
            for balance in balances
            if balance >= required
        )

        weekly_statistics.append(
            {
                "week": week,
                "weeks_remaining": weeks_remaining,
                "required_balance": required,
                "mean_balance": balance_stats["mean"],
                "median_balance": balance_stats["median"],
                "min_balance": balance_stats["min"],
                "p01_balance": balance_stats["p01"],
                "p1_balance": balance_stats["p1"],
                "p5_balance": balance_stats["p5"],
                "p10_balance": balance_stats["p10"],
                "p25_balance": balance_stats["p25"],
                "p50_balance": balance_stats["p50"],
                "p75_balance": balance_stats["p75"],
                "p90_balance": balance_stats["p90"],
                "p95_balance": balance_stats["p95"],
                "p99_balance": balance_stats["p99"],
                "p999_balance": balance_stats["p999"],
                "max_balance": balance_stats["max"],
                "mean_drawdown": drawdown_stats["mean"],
                "median_drawdown": drawdown_stats["median"],
                "p95_drawdown": drawdown_stats["p95"],
                "p99_drawdown": drawdown_stats["p99"],
                "mean_opi": balance_stats["mean"] / required,
                "median_opi": balance_stats["median"] / required,
                "p5_opi": balance_stats["p5"] / required,
                "p95_opi": balance_stats["p95"] / required,
                "probability_on_track": (
                    100.0
                    * on_track_count
                    / len(balances)
                ),
            }
        )

        completed = week + 1

        if (
            completed % progress_interval == 0
            or completed == curve_length
        ):
            print_progress(
                completed,
                curve_length,
            )

    finish_progress()

    return weekly_statistics


def ensure_output_directory(output_directory):
    path = Path(output_directory)

    path.mkdir(
        parents=True,
        exist_ok=True,
    )

    return path


def export_weekly_statistics(
    weekly_statistics,
    filename,
):
    fieldnames = [
        "week",
        "weeks_remaining",
        "required_balance",
        "mean_balance",
        "median_balance",
        "min_balance",
        "p01_balance",
        "p1_balance",
        "p5_balance",
        "p10_balance",
        "p25_balance",
        "p50_balance",
        "p75_balance",
        "p90_balance",
        "p95_balance",
        "p99_balance",
        "p999_balance",
        "max_balance",
        "mean_drawdown",
        "median_drawdown",
        "p95_drawdown",
        "p99_drawdown",
        "mean_opi",
        "median_opi",
        "p5_opi",
        "p95_opi",
        "probability_on_track",
    ]

    print(f"Writing {filename}...")

    with Path(filename).open(
        "w",
        newline="",
        encoding="utf-8",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames,
        )

        writer.writeheader()
        writer.writerows(
            weekly_statistics
        )


def export_equity_curves(results, filename):
    curves = results["equity_curves"]
    weeks = len(curves[0])

    print(f"Writing {filename}...")

    with Path(filename).open(
        "w",
        newline="",
        encoding="utf-8",
    ) as file:
        writer = csv.writer(file)

        writer.writerow(
            ["simulation"]
            + [
                f"week_{week}"
                for week in range(weeks)
            ]
        )

        for simulation_index, curve in enumerate(
            curves,
            start=1,
        ):
            writer.writerow(
                [simulation_index]
                + curve
            )


def export_drawdown_curves(results, filename):
    curves = results["drawdown_curves"]
    weeks = len(curves[0])

    print(f"Writing {filename}...")

    with Path(filename).open(
        "w",
        newline="",
        encoding="utf-8",
    ) as file:
        writer = csv.writer(file)

        writer.writerow(
            ["simulation"]
            + [
                f"week_{week}"
                for week in range(weeks)
            ]
        )

        for simulation_index, curve in enumerate(
            curves,
            start=1,
        ):
            writer.writerow(
                [simulation_index]
                + curve
            )


def export_simulated_returns(results, filename):
    paths = results["simulated_returns"]
    weeks = len(paths[0])

    print(f"Writing {filename}...")

    with Path(filename).open(
        "w",
        newline="",
        encoding="utf-8",
    ) as file:
        writer = csv.writer(file)

        writer.writerow(
            ["simulation"]
            + [
                f"week_{week}"
                for week in range(
                    1,
                    weeks + 1,
                )
            ]
        )

        for simulation_index, path in enumerate(
            paths,
            start=1,
        ):
            writer.writerow(
                [simulation_index]
                + path
            )


def export_simulation_summary(results, filename):
    print(f"Writing {filename}...")

    with Path(filename).open(
        "w",
        newline="",
        encoding="utf-8",
    ) as file:
        writer = csv.writer(file)

        header = [
            "simulation",
            "final_balance",
            "total_return_percent",
            "cagr_percent",
            "max_drawdown_decimal",
            "max_drawdown_percent",
            "longest_underwater_weeks",
            "ulcer_index_decimal",
            "ulcer_index_percent",
            "taxes_paid",
            "final_partial_tax_paid",
            "total_topups",
            "account_ruined",
            "sampled_weekly_mean_decimal",
            "sampled_weekly_mean_percent",
            "sampled_weekly_stdev_decimal",
            "sampled_weekly_stdev_percent",
        ]

        for target in TARGETS:
            header.append(
                f"first_week_at_{int(target)}"
            )

        writer.writerow(header)

        for simulation_index in range(
            len(results["final_balances"])
        ):
            target_hit_data = (
                results["first_target_hit_weeks"][
                    simulation_index
                ]
            )

            row = [
                simulation_index + 1,
                results["final_balances"][
                    simulation_index
                ],
                results["total_returns"][
                    simulation_index
                ],
                results["cagrs"][
                    simulation_index
                ],
                results["max_drawdowns"][
                    simulation_index
                ],
                results["max_drawdowns"][
                    simulation_index
                ] * 100.0,
                results["longest_underwater"][
                    simulation_index
                ],
                results["ulcer_indexes"][
                    simulation_index
                ],
                results["ulcer_indexes"][
                    simulation_index
                ] * 100.0,
                results["taxes_paid"][
                    simulation_index
                ],
                results["final_partial_taxes_paid"][
                    simulation_index
                ],
                results["total_topups"][
                    simulation_index
                ],
                results["account_ruined_flags"][
                    simulation_index
                ],
                results["sampled_means"][
                    simulation_index
                ],
                results["sampled_means"][
                    simulation_index
                ] * 100.0,
                results["sampled_stdevs"][
                    simulation_index
                ],
                results["sampled_stdevs"][
                    simulation_index
                ] * 100.0,
            ]

            for target in TARGETS:
                row.append(
                    target_hit_data[target]
                )

            writer.writerow(row)


def export_all_results(
    results,
    weekly_statistics,
    output_directory,
):
    output_path = ensure_output_directory(
        output_directory
    )

    print()
    print("=" * 60)
    print("EXPORTING CSV FILES")
    print("=" * 60)

    export_weekly_statistics(
        weekly_statistics=weekly_statistics,
        filename=output_path
        / "weekly_statistics.csv",
    )

    export_simulation_summary(
        results=results,
        filename=output_path
        / "simulation_summary.csv",
    )

    export_equity_curves(
        results=results,
        filename=output_path
        / "equity_curves.csv",
    )

    export_drawdown_curves(
        results=results,
        filename=output_path
        / "drawdown_curves.csv",
    )

    export_simulated_returns(
        results=results,
        filename=output_path
        / "simulated_returns.csv",
    )

    print()
    print(
        f"CSV exports completed: "
        f"{output_path.resolve()}"
    )


def print_configuration(
    args,
    weekly_growth_decimal,
    apply_final_tax,
):
    print()
    print("=" * 60)
    print("CONFIGURATION")
    print("=" * 60)

    print(
        f"Input file          : "
        f"{Path(args.input).resolve()}"
    )

    print(
        f"Return format       : "
        f"decimal (0.01 = 1%)"
    )

    print(
        f"Simulations         : "
        f"{args.simulations:,}"
    )

    print(
        f"Simulation weeks    : "
        f"{args.weeks:,}"
    )

    print(
        f"Block size          : "
        f"{args.block}"
    )

    print(
        f"Return leverage     : "
        f"{args.leverage:.4f}x"
    )

    print(
        f"Initial balance     : "
        f"{args.initial:,.2f}"
    )

    print(
        f"Top-up amount       : "
        f"{args.topup:,.2f}"
    )

    print(
        f"Top-up interval     : "
        f"{args.topup_interval} weeks"
    )

    print(
        f"Top-up stop balance : "
        f"{args.topup_stop_balance:,.2f}"
    )

    print(
        f"Annual tax rate     : "
        f"{args.tax:.2f}%"
    )

    print(
        f"Final partial tax   : "
        f"{'yes' if apply_final_tax else 'no'}"
    )

    print(
        f"Bayesian parameters : "
        f"{'yes' if args.bayesian_parameters else 'no'}"
    )

    print(
        f"Target balance      : "
        f"{args.target:,.2f}"
    )

    print(
        f"Target weekly growth: "
        f"{weekly_growth_decimal * 100.0:.4f}%"
    )

    print(
        f"Random seed         : "
        f"{args.seed if args.seed is not None else 'system random'}"
    )

    print(
        f"CSV export          : "
        f"{'yes' if args.export else 'no'}"
    )


def main():
    args = parse_arguments()
    validate_arguments(args)

    if args.seed is not None:
        random.seed(args.seed)

    weekly_growth_decimal = (
        args.target_weekly_growth
        / 100.0
    )

    apply_final_tax = (
        not args.no_final_tax
    )

    historical_returns = load_returns(
        args.input
    )

    if args.block > len(historical_returns):
        raise ValueError(
            f"--block={args.block} exceeds "
            f"the number of historical weeks "
            f"({len(historical_returns)})"
        )

    historical_mean = statistics.mean(
        historical_returns
    )

    historical_stdev = statistics.stdev(
        historical_returns
    )

    historical_sample_size = len(
        historical_returns
    )

    minimum_leveraged_return = (
        min(historical_returns)
        * args.leverage
    )

    if minimum_leveraged_return <= -1.0:
        print()
        print(
            "WARNING: At least one leveraged historical "
            "weekly return is <= -100%."
        )
        print(
            "Such a week will reduce the account to zero "
            "in any simulated path containing it."
        )

    blocks = build_circular_blocks(
        returns=historical_returns,
        block_size=args.block,
    )

    print_configuration(
        args=args,
        weekly_growth_decimal=weekly_growth_decimal,
        apply_final_tax=apply_final_tax,
    )

    print_dataset_information(
        returns=historical_returns,
        blocks=blocks,
        block_size=args.block,
        leverage=args.leverage,
    )

    results = run_monte_carlo(
        blocks=blocks,
        simulations=args.simulations,
        simulation_weeks=args.weeks,
        initial_balance=args.initial,
        tax_rate=args.tax,
        topup_amount=args.topup,
        topup_interval=args.topup_interval,
        topup_stop_balance=args.topup_stop_balance,
        leverage=args.leverage,
        apply_final_tax=apply_final_tax,
        bayesian_parameters=args.bayesian_parameters,
        historical_mean=historical_mean,
        historical_stdev=historical_stdev,
        historical_sample_size=historical_sample_size,
    )

    print_statistics(results)

    weekly_statistics = calculate_weekly_statistics(
        results=results,
        target_balance=args.target,
        weekly_growth=weekly_growth_decimal,
    )

    if args.export:
        export_all_results(
            results=results,
            weekly_statistics=weekly_statistics,
            output_directory=args.output_dir,
        )


if __name__ == "__main__":
    try:
        main()

    except KeyboardInterrupt:
        print()
        print("Simulation interrupted by user.")
        raise SystemExit(130)

    except Exception as exc:
        print()
        print(f"ERROR: {exc}")
        raise SystemExit(1)
