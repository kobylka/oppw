package com.oppw.monitor.util

fun effectiveStopLoss(brokerStopLoss: Double, immutableHardStop: Double, protectionTarget: Double = 0.0): Double =
    brokerStopLoss.takeIf { it > 0.0 }
        ?: immutableHardStop.takeIf { it > 0.0 }
        ?: protectionTarget.takeIf { it > 0.0 }
        ?: 0.0
