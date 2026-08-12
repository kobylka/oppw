package com.oppw.monitor.util

data class MarketReferenceDisplay(val label: String, val value: Double?)

fun marketReferenceDisplay(positionOpenPrice: Double?, weekOpen: Double?): MarketReferenceDisplay =
    if (positionOpenPrice != null && positionOpenPrice > 0.0) {
        MarketReferenceDisplay("Position open", positionOpenPrice)
    } else {
        MarketReferenceDisplay("Week open", weekOpen)
    }
