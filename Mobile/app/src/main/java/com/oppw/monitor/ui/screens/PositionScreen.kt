package com.oppw.monitor.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.oppw.monitor.data.PriceCondition
import com.oppw.monitor.data.StrategyRuleControl
import com.oppw.monitor.data.UiState
import com.oppw.monitor.ui.components.AppCard
import com.oppw.monitor.ui.components.ErrorPanel
import com.oppw.monitor.ui.components.LoadingPanel
import com.oppw.monitor.ui.components.Metric
import com.oppw.monitor.ui.components.RiskBar
import com.oppw.monitor.ui.components.SectionTitle
import com.oppw.monitor.ui.components.StatusChip
import com.oppw.monitor.ui.theme.BrightGreen
import com.oppw.monitor.ui.theme.DangerRed
import com.oppw.monitor.ui.theme.PrimaryBlue
import com.oppw.monitor.ui.theme.TextSecondary
import com.oppw.monitor.util.age
import com.oppw.monitor.util.countdown
import com.oppw.monitor.util.effectiveStopLoss
import com.oppw.monitor.util.humanProtection
import com.oppw.monitor.util.leverage
import com.oppw.monitor.util.liveSourceAge
import com.oppw.monitor.util.money
import com.oppw.monitor.util.percent
import com.oppw.monitor.util.positionConditionDisplay
import com.oppw.monitor.util.unsignedPercent
import com.oppw.monitor.util.price
import com.oppw.monitor.util.shortDateTime
import com.oppw.monitor.util.timeOnly
import com.oppw.monitor.util.volume
import kotlin.math.abs
import java.util.Locale

@Composable
fun PositionScreen(state: UiState, onRetry: () -> Unit) {
    when {
        state.loading && state.response == null -> LoadingPanel()
        state.response == null -> ErrorPanel(state.error ?: "No data", onRetry)
        else -> {
            val snapshot = state.response!!.snapshot
            val position = snapshot.position
            if (position == null) {
                val account = snapshot.account
                val potential = snapshot.potentialPosition
                val decision = snapshot.strategyDecision
                LazyColumn(Modifier.fillMaxSize().padding(horizontal = 14.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    item {
                        AppCard(Modifier.fillMaxWidth()) {
                            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                                Column {
                                    Text("No open position", style = MaterialTheme.typography.titleLarge)
                                    Text("Waiting for the next strategy entry.", color = TextSecondary)
                                }
                                StatusChip("FLAT")
                            }
                        }
                    }
                    item {
                        AppCard(Modifier.fillMaxWidth()) {
                            SectionTitle("Pre-trade what-if ticket", if (potential?.available == true) "LIVE MT5" else "UNAVAILABLE")
                            when {
                                potential == null -> Text("The publisher has not supplied the v43 potentialPosition object.", color = TextSecondary)
                                !potential.available -> {
                                    Text("MT5 could not calculate the next trade.", color = TextSecondary)
                                    if (potential.error.isNotBlank()) Text(potential.error, color = DangerRed)
                                    Metric("Chosen strategy leverage", leverage(potential.strategyLeverage))
                                    if (potential.leverageReason.isNotBlank()) Text(potential.leverageReason)
                                }
                                else -> {
                                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                                        Column {
                                            Text("${potential.side} ${potential.symbol}", style = MaterialTheme.typography.headlineMedium)
                                            Text("Calculated at current MT5 BUY price", color = TextSecondary)
                                        }
                                        StatusChip("${potential.strategyLeverage.toInt()}x", "green")
                                    }
                                    val effectiveLeverage = if (potential.balance > 0.0 && potential.requiredDeposit > 0.0) 20.0 * potential.requiredDeposit / potential.balance else potential.effectiveLeverage
                                    MetricRow("Potential volume", volume(potential.volume), "Current price", price(potential.price), BrightGreen)
                                    MetricRow("Required deposit", money(potential.requiredDeposit, account.currency), "Effective leverage", leverage(effectiveLeverage))
                                    MetricRow("Balance", money(potential.balance, account.currency), "Equity", money(potential.equity, account.currency))
                                    MetricRow("Free margin now", money(potential.freeMargin, account.currency), "Free margin after", money(potential.freeMarginAfter, account.currency), if (potential.freeMarginAfter >= 0.0) BrightGreen else DangerRed)
                                    MetricRow("Margin usage", unsignedPercent(potential.marginUsagePercent), "Margin level after", unsignedPercent(potential.marginLevelAfterPercent))
                                    MetricRow("Potential notional", money(potential.positionNotional, account.currency), "Sizing units", potential.sizingUnits.toString())
                                    Text("Margin source: ${potential.depositSource}", color = TextSecondary, style = MaterialTheme.typography.labelMedium)
                                }
                            }
                        }
                    }
                    item {
                        LossControlCard(state, potential)
                    }
                    if (potential?.available == true) {
                        item {
                            AppCard(Modifier.fillMaxWidth()) {
                                SectionTitle("Potential hard stop loss", if (potential.accountLossCapApplied) "50% ACCOUNT CAP" else "")
                                MetricRow("Stop price", price(potential.potentialStopLossPrice), "Cash P/L at stop", money(potential.potentialStopLossCash, account.currency), DangerRed)
                                MetricRow("Account return at stop", percent(potential.accountLossPercentAtStop), "Risk cap", if (potential.accountLossCapApplied) "APPLIED" else "NOT REQUIRED", DangerRed)
                                if (potential.accountLossCapApplied) Text("The stop was moved closer so the projected account loss does not exceed 50% of balance.", color = TextSecondary)
                            }
                        }
                        item {
                            AppCard(Modifier.fillMaxWidth()) {
                                SectionTitle("What-if scenarios", potential.scenarios.size.toString())
                                potential.scenarios.forEach { scenario ->
                                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                                        Text(scenario.label, style = MaterialTheme.typography.titleMedium)
                                        Text(money(scenario.profit, account.currency), color = if (scenario.profit >= 0.0) BrightGreen else DangerRed)
                                    }
                                    Text("Price ${price(scenario.price)} · underlying ${percent(scenario.underlyingReturnPercent)} · account ${percent(scenario.accountReturnPercent)} · balance ${money(scenario.balanceAfter, account.currency)}", color = TextSecondary, style = MaterialTheme.typography.labelMedium)
                                }
                            }
                        }
                    }
                    item {
                        AppCard(Modifier.fillMaxWidth()) {
                            SectionTitle("Strategy decision recorder", decision?.outcome ?: "NO RECORD")
                            if (decision == null) {
                                Text("No structured strategy decision has been published yet.", color = TextSecondary)
                            } else {
                                val labeledTrade = snapshot.lastClosedTrade
                                val useLabeledTrade = abs(decision.previousTradeChange) <= 1e-12 && labeledTrade != null && abs(labeledTrade.preleverageReturn) > 1e-12
                                val previousTradeChange = if (useLabeledTrade) labeledTrade!!.preleverageReturn else decision.previousTradeChange
                                val previousTradeSource = if (useLabeledTrade) "publisher-labeled last trade" else decision.previousTradeSource
                                MetricRow("Selected leverage", leverage(decision.selectedLeverage), "Decision ID", decision.decisionId.take(8))
                                MetricRow("Previous full week", percent(decision.previousFullWeekChange * 100.0), "Previous trade", percent(previousTradeChange * 100.0))
                                Text(decision.leverageReason, style = MaterialTheme.typography.bodyLarge)
                                Text("Week source: ${decision.previousFullWeekSource}", color = TextSecondary, style = MaterialTheme.typography.labelMedium)
                                Text("Trade source: $previousTradeSource", color = TextSecondary, style = MaterialTheme.typography.labelMedium)
                                Text("Recorded ${shortDateTime(decision.recordedAt)} · build ${decision.build}", color = TextSecondary, style = MaterialTheme.typography.labelMedium)
                                if (decision.error.isNotBlank()) Text(decision.error, color = DangerRed)
                            }
                        }
                    }
                    snapshot.lastClosedTrade?.let { trade ->
                        item {
                            AppCard(Modifier.fillMaxWidth()) {
                                SectionTitle("Last publisher-labeled trade", "Class ${trade.tradeClass}")
                                MetricRow("Pre-leverage return", percent(trade.preleverageReturnPercent), "Exit reason", trade.exitReason)
                                Text("Closed ${shortDateTime(trade.closedAt)} · position ${trade.positionIdentifier}", color = TextSecondary)
                            }
                        }
                    }
                    state.error?.let { error -> item { ErrorPanel("Showing cached data. $error", onRetry) } }
                }
                return
            }

            val account = snapshot.account
            val ohPending = snapshot.connection.nextAction.equals("OH", true)
            val conditionDisplay = positionConditionDisplay(
                conditions = snapshot.conditions,
                reportedClosest = snapshot.closestCondition,
                ohPending = ohPending,
                snapshotAt = snapshot.connection.lastSync.ifBlank { state.response.generatedAt },
                weekOpenDate = snapshot.marketStats.currentWeek?.weekOpenDate.orEmpty(),
            )
            val visibleConditions = conditionDisplay.visible
            val conditions = conditionDisplay.others
            val closest = conditionDisplay.closest
            val minimumBalance = account.deposit * 1.765
            val exposure = position.exposure.takeIf { it > 0.0 } ?: account.deposit * 20.0
            val effectiveLeverage = position.effectiveLeverage.takeIf { it > 0.0 } ?: if (account.balance > 0.0) exposure / account.balance else 0.0
            val potentialTakeProfit = position.potentialTakeProfit.takeIf { it > 0.0 } ?: visibleConditions.firstOrNull { it.name.equals("OH", true) || it.name.equals("CH", true) }?.targetPrice ?: 0.0
            val displayedStopLoss = effectiveStopLoss(position.stopLoss, position.immutableHardStop.price, position.protectionTarget.price)
            val stopTargetPending = position.stopLoss <= 0.0 && position.protectionTarget.price > 0.0 && !position.protectionTarget.applied
            val stopMetricLabel = if (stopTargetPending) "Stop target (executor pending)" else "Stop loss"
            val liveTickAge = liveSourceAge(position.tickAgeSeconds, position.priceTime.ifBlank { snapshot.connection.lastSync }, state.nowEpochMs)
            val breakEvenCheck = position.breakEvenCheck
            val breakEvenStatus = breakEvenCheck.status.uppercase()
            val breakEvenCheckTime = when (breakEvenStatus) {
                "ARMED" -> "Already armed"
                "NO_FURTHER_CHECK" -> "None before weekly TO"
                "DUE", "DUE_SIGNAL_PENDING" -> "Due now"
                else -> shortDateTime(breakEvenCheck.nextCheckAt)
            }
            val breakEvenScheduled = breakEvenStatus == "SCHEDULED" || breakEvenStatus == "SCHEDULED_SIGNAL_PENDING"
            LazyColumn(Modifier.fillMaxSize().padding(horizontal = 14.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                item {
                    AppCard(Modifier.fillMaxWidth()) {
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                            Column {
                                Text(position.symbol, style = MaterialTheme.typography.headlineMedium)
                                Text("Ticket ${position.ticket}", color = TextSecondary)
                                Text("Opened ${shortDateTime(position.openedAt)}", color = TextSecondary)
                            }
                            StatusChip(position.side, "green")
                        }
                        MetricRow("Volume", volume(position.volume), "Open price", price(position.openPrice))
                        MetricRow(
                            "Next break-even check",
                            breakEvenCheckTime,
                            "Countdown",
                            if (breakEvenScheduled && breakEvenCheck.nextCheckAt.isNotBlank()) countdown(breakEvenCheck.nextCheckAt, state.nowEpochMs) else breakEvenStatus.replace('_', ' '),
                            if (breakEvenStatus == "ARMED") BrightGreen else PrimaryBlue,
                        )
                        if (breakEvenCheck.threshold > 0.0) {
                            Text(
                                "Arms immediately after CH if the live signal price is below ${price(breakEvenCheck.threshold)} " +
                                    "(reference ${price(breakEvenCheck.signalReference)}).",
                                color = TextSecondary,
                                style = MaterialTheme.typography.labelMedium,
                            )
                        } else if (breakEvenCheck.condition.isNotBlank()) {
                            Text(breakEvenCheck.condition, color = TextSecondary, style = MaterialTheme.typography.labelMedium)
                        }
                        MetricRow("Current bid", price(position.bid), "Current ask", price(position.ask), if (position.profit >= 0) BrightGreen else DangerRed)
                        MetricRow("Bid time", timeOnly(position.bidAt.ifBlank { position.priceTime }), "Ask time", timeOnly(position.askAt.ifBlank { position.priceTime }))
                        Text("Price age: ${age(liveTickAge)}", color = TextSecondary, style = MaterialTheme.typography.labelMedium)
                        MetricRow(stopMetricLabel, price(displayedStopLoss), "Potential OH/CH target", price(potentialTakeProfit), DangerRed)
                    }
                }
                item { PositionLossControlCard(state, position.lossControls) }
                item { ConditionCard("Closest condition", closest, true) }
                item { SectionTitle("All other conditions", conditions.size.toString()) }
                if (conditions.isEmpty()) item { AppCard(Modifier.fillMaxWidth()) { Text("No other active price conditions.", color = TextSecondary) } }
                else items(conditions.size, key = { index -> "condition-${conditions[index].name}-$index" }) { index -> ConditionCard(conditions[index].name, conditions[index], false) }
                item { AppCard(Modifier.fillMaxWidth()) { SectionTitle("Risk to stop loss"); RiskBar(displayedStopLoss, position.openPrice, position.bid) } }
                item {
                    AppCard(Modifier.fillMaxWidth()) {
                        MetricRow("Unrealized P/L", money(position.profit, account.currency), "P/L % leveraged", percent(position.leveragedProfitPercent), if (position.profit >= 0) BrightGreen else DangerRed)
                        MetricRow("Exposure", money(exposure, account.currency), "Effective leverage", leverage(effectiveLeverage))
                        MetricRow("Deposit", money(account.deposit, account.currency), "Minimum balance at 50% margin", money(minimumBalance, account.currency))
                        MetricRow("Protection", humanProtection(position.protectionRegime), "Break-even", if (position.breakEvenArmed) "ARMED" else "OFF", if (position.breakEvenArmed) BrightGreen else TextSecondary)
                    }
                }
                state.error?.let { error -> item { ErrorPanel("Showing cached data. $error", onRetry) } }
            }
        }
    }
}

@Composable
private fun PositionLossControlCard(state: UiState, live: com.oppw.monitor.data.LossControlStatus) {
    val liveByKey = live.rules.associateBy { it.key }
    val configured = state.strategyControl?.positionRules.orEmpty().ifEmpty {
        live.rules.map { StrategyRuleControl(it.key, it.key.replace('_', ' '), "", it.enabled, "OPEN_POSITION") }
    }
    AppCard(Modifier.fillMaxWidth()) {
        SectionTitle("Open-position loss protection", "REV ${state.strategyControl?.positionRevision ?: live.revision}")
        if (live.rules.isEmpty()) {
            Text("Waiting for the publisher's completed-candle position-rule evaluation.", color = TextSecondary)
            state.strategyControlError?.let { Text(it, color = DangerRed) }
            return@AppCard
        }
        MetricRow("Last completed M1 close", price(live.currentPrice), "Evaluated", shortDateTime(live.evaluatedAt))
        if (live.currentPriceUsage.isNotBlank()) Text(live.currentPriceUsage, color = TextSecondary)
        configured.forEach { control ->
            val rule = liveByKey[control.key]
            val status = when {
                rule?.status.equals("EXIT_AUTHORIZED", true) -> "EXIT_AUTHORIZED"
                !control.enabled -> "DISABLED"
                rule == null -> "WAITING"
                else -> rule.status.ifBlank { "WAITING" }
            }
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text(control.label, style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f))
                StatusChip(status.replace('_', ' '), lossControlTone(status, rule?.effect.orEmpty()))
            }
            if (control.description.isNotBlank()) Text(control.description, color = TextSecondary)
            val conditionActive = control.enabled && rule?.applicable == true
            val effect = rule?.effect.orEmpty()
            rule?.conditions.orEmpty().forEach { condition ->
                val actual = condition.actual?.let(::lossControlRatio) ?: "awaiting input"
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                    Column(Modifier.weight(1f)) {
                        Text(condition.label)
                        Text("$actual  ${condition.operator}  ${lossControlRatio(condition.threshold)}", color = TextSecondary)
                    }
                    StatusChip(
                        when (condition.met) { true -> "MET"; false -> "NOT MET"; null -> "WAITING" },
                        lossControlConditionTone(conditionActive, effect, condition.met),
                    )
                }
            }
        }
        live.error.takeIf { it.isNotBlank() }?.let { Text("Live input warning: $it", color = TextSecondary) }
    }
}

@Composable
private fun LossControlCard(state: UiState, potential: com.oppw.monitor.data.PotentialPosition?) {
    val live = potential?.lossControls
    val liveByKey = live?.rules.orEmpty().associateBy { it.key }
    val configured = state.strategyControl?.rules.orEmpty().ifEmpty {
        live?.rules.orEmpty().map { StrategyRuleControl(it.key, it.key.replace('_', ' '), "", it.enabled) }
    }
    AppCard(Modifier.fillMaxWidth()) {
        SectionTitle("Weekly entry loss controls", "REV ${state.strategyControl?.revision ?: live?.revision ?: 0}")
        if (live == null || live.rules.isEmpty()) {
            Text("Waiting for the publisher's live loss-control evaluation.", color = TextSecondary)
            state.strategyControlError?.let { Text(it, color = DangerRed) }
            return@AppCard
        }
        MetricRow("Live current price", price(live.currentPrice), "Evaluated", shortDateTime(live.evaluatedAt))
        if (live.currentPriceUsage.isNotBlank()) Text(live.currentPriceUsage, color = TextSecondary)
        configured.forEach { control ->
            val rule = liveByKey[control.key]
            val enabled = control.enabled
            val status = when {
                !enabled -> "DISABLED"
                rule == null -> "WAITING"
                !rule.applicable -> "NOT_APPLICABLE"
                rule.conditions.any { it.met == null } -> "WAITING"
                rule.conditions.all { it.met == true } -> "MATCHED"
                else -> "NOT_MATCHED"
            }
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text(control.label, style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f))
                StatusChip(status.replace('_', ' '), lossControlTone(status, rule?.effect.orEmpty()))
            }
            if (control.description.isNotBlank()) Text(control.description, color = TextSecondary)
            rule?.conditions.orEmpty().forEach { condition ->
                val actual = condition.actual?.let(::lossControlRatio) ?: "awaiting input"
                val threshold = lossControlRatio(condition.threshold)
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                    Column(Modifier.weight(1f)) {
                        Text(condition.label)
                        Text("$actual  ${condition.operator}  $threshold", color = TextSecondary)
                    }
                    StatusChip(
                        when (condition.met) { true -> "MET"; false -> "NOT MET"; null -> "WAITING" },
                        lossControlConditionTone(enabled && rule?.applicable == true, rule?.effect.orEmpty(), condition.met),
                    )
                }
            }
        }
        live.error.takeIf { it.isNotBlank() }?.let { Text("Live input warning: $it", color = TextSecondary) }
    }
}

private fun lossControlRatio(value: Double): String = String.format(Locale.US, "%+.3f%%", value * 100.0)

private fun lossControlTone(status: String, effect: String): String = when (status) {
    "DISABLED", "NOT_APPLICABLE" -> "blue"
    "WAITING" -> "amber"
    "EXIT_AUTHORIZED" -> "red"
    "MATCHED" -> if (effect == "ALLOW_TUESDAY_REENTRY") "green" else "red"
    "NOT_MATCHED" -> if (effect == "ALLOW_TUESDAY_REENTRY") "red" else "green"
    else -> "blue"
}

private fun lossControlConditionTone(active: Boolean, effect: String, met: Boolean?): String = when {
    !active -> "blue"
    met == null -> "amber"
    effect == "ALLOW_TUESDAY_REENTRY" -> if (met) "green" else "red"
    else -> if (met) "red" else "green"
}

@Composable
private fun MetricRow(firstLabel: String, firstValue: String, secondLabel: String, secondValue: String, valueColor: androidx.compose.ui.graphics.Color = MaterialTheme.colorScheme.onSurface) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(14.dp)) {
        Metric(firstLabel, firstValue, Modifier.weight(1f), valueColor)
        Metric(secondLabel, secondValue, Modifier.weight(1f), valueColor)
    }
}

@Composable
private fun ConditionCard(title: String, condition: PriceCondition?, nearest: Boolean) {
    AppCard(Modifier.fillMaxWidth()) {
        SectionTitle(title, condition?.source ?: "")
        if (condition == null) { Text("No active price condition", color = TextSecondary); return@AppCard }
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Text(condition.name, color = if (nearest) PrimaryBlue else MaterialTheme.colorScheme.onSurface, style = MaterialTheme.typography.headlineMedium)
            if (nearest) StatusChip("NEAREST")
        }
        MetricRow("Target price", price(condition.targetPrice), "Distance", "${price(condition.distancePoints)} pts\n(${String.format("%.2f", condition.distancePercent)}%)", if (nearest) PrimaryBlue else MaterialTheme.colorScheme.onSurface)
        if (condition.name.equals("PRE H", true) && condition.potentialTpPercent != null) {
            Text(
                "Current potential TP level: ${percent(condition.potentialTpPercent)}",
                color = if (nearest) PrimaryBlue else MaterialTheme.colorScheme.onSurface,
                style = MaterialTheme.typography.titleMedium,
            )
        }
        MetricRow("Current price", price(condition.currentPrice), "Direction", condition.direction.replaceFirstChar { it.uppercase() })
    }
}
