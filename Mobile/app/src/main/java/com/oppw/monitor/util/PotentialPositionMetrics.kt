package com.oppw.monitor.util

fun potentialEffectiveLeverage(requiredDeposit: Double, balance: Double, fallback: Double = 0.0): Double {
    if (!requiredDeposit.isFinite() || requiredDeposit < 0.0) return fallback.takeIf { it.isFinite() && it >= 0.0 } ?: 0.0
    return if (balance.isFinite() && balance > 0.0) requiredDeposit / balance else fallback.takeIf { it.isFinite() && it >= 0.0 } ?: 0.0
}
