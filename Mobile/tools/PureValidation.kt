import com.oppw.monitor.data.ClosedTrade
import com.oppw.monitor.data.ConnectionStatus
import com.oppw.monitor.data.MonitorEvent
import com.oppw.monitor.data.PriceCondition
import com.oppw.monitor.util.MarketClock
import com.oppw.monitor.util.TradeMetrics
import com.oppw.monitor.util.isRoutineConditionCheck
import com.oppw.monitor.util.normalizedTimePosition
import com.oppw.monitor.util.otherConditions
import java.time.ZoneId
import java.time.ZonedDateTime

fun main() {
    val saturday = ZonedDateTime.of(2026, 7, 18, 12, 0, 0, 0, ZoneId.of("Europe/Warsaw")).toInstant().toEpochMilli()
    val weekend = MarketClock.display(ConnectionStatus(phase = "REGULAR", nextAction = "OH", nextActionAt = "future"), true, saturday)
    check(weekend.marketClosed && weekend.phase == "Weekend" && weekend.nextAction == "None" && weekend.nextActionAt.isBlank())
    check(normalizedTimePosition(86_400_000L, 0L, 172_800_000L) == 0.5)
    val metrics = TradeMetrics.fromClosedTrades(listOf(ClosedTrade(closed = true, profit = 100.0, balanceBefore = 1000.0), ClosedTrade(closed = true, profit = -50.0, balanceBefore = 1000.0), ClosedTrade(closed = false, profit = 900.0, balanceBefore = 1000.0)))
    check(metrics.sample == 2 && metrics.returns == listOf(0.1, -0.05) && metrics.sharpe != null && metrics.sortino != null)
    check(isRoutineConditionCheck(MonitorEvent(1, "", "OH", "", false)))
    check(!isRoutineConditionCheck(MonitorEvent(2, "", "POSITION_CLOSED", "", true)))
    val closest = PriceCondition("SL", 100.0, 101.0, 1.0, 1.0, "below", true, "US100")
    val different = closest.copy(targetPrice = 99.0)
    check(otherConditions(closest, listOf(closest, different)) == listOf(different))
    println("Pure v10 behavior validation passed")
}
