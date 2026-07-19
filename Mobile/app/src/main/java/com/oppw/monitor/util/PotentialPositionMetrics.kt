package com.oppw.monitor.util

fun potentialEffectiveLeverage(requiredDeposit: Double, balance: Double, fallback: Double = 0.0): Double {
    // Android cannot calculate MT5 margin. The publisher value was calculated from
    // the proposed position volume, current MT5 price and broker margin rules.
    return fallback.takeIf { it.isFinite() && it >= 0.0 } ?: 0.0
}
