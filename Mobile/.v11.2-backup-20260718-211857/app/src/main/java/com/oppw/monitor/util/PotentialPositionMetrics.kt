package com.oppw.monitor.util

fun potentialEffectiveLeverage(requiredDeposit: Double, balance: Double, fallback: Double = 0.0): Double {
    val validFallback = fallback.takeIf { it.isFinite() && it >= 0.0 } ?: 0.0
    if (!requiredDeposit.isFinite() || requiredDeposit < 0.0) return validFallback
    return if (balance.isFinite() && balance > 0.0) BROKER_MARGIN_LEVERAGE * requiredDeposit / balance else validFallback
}
