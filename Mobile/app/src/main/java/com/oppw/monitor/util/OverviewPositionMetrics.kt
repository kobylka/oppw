package com.oppw.monitor.util

import com.oppw.monitor.data.AccountStatus
import com.oppw.monitor.data.PositionStatus

data class OverviewPositionDisplay(
    val deposit: String,
    val currentProfit: String,
    val currentProfitPercent: String,
    val effectiveProfitPercent: String,
    val strategyLeverage: String,
    val leveragedProfitPercent: String,
    val effectiveLeverage: String,
    val exposure: String,
)

fun overviewPositionDisplay(
    account: AccountStatus,
    position: PositionStatus?,
): OverviewPositionDisplay {
    if (position == null) {
        return OverviewPositionDisplay(
            deposit = "—",
            currentProfit = "—",
            currentProfitPercent = "—",
            effectiveProfitPercent = "—",
            strategyLeverage = "—",
            leveragedProfitPercent = "—",
            effectiveLeverage = "—",
            exposure = "—",
        )
    }

    val effectiveProfitPercent =
        if (account.balance != 0.0) position.profit / account.balance * 100.0 else 0.0
    val exposure = position.exposure.takeIf { it > 0.0 } ?: account.deposit * 20.0
    val effectiveLeverage = position.effectiveLeverage.takeIf { it > 0.0 }
        ?: if (account.balance > 0.0) exposure / account.balance else 0.0

    return OverviewPositionDisplay(
        deposit = money(account.deposit, account.currency),
        currentProfit = money(position.profit, account.currency),
        currentProfitPercent = percent(position.profitPercent),
        effectiveProfitPercent = percent(effectiveProfitPercent),
        strategyLeverage = "${position.strategyLeverage.toInt()}x",
        leveragedProfitPercent = percent(position.leveragedProfitPercent),
        effectiveLeverage = leverage(effectiveLeverage),
        exposure = money(exposure, account.currency),
    )
}
