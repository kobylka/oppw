package com.oppw.monitor.util

import java.text.NumberFormat
import java.time.Duration
import java.time.Instant
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale
import kotlin.math.max

private val number = NumberFormat.getNumberInstance(Locale.US).apply {
    minimumFractionDigits = 2
    maximumFractionDigits = 2
}
private val deviceZone: ZoneId get() = ZoneId.systemDefault()

fun money(value: Double, currency: String): String = "${number.format(value)} $currency".trim()
fun price(value: Double): String = if (value == 0.0) "—" else String.format(Locale.US, "%,.2f", value)
fun optionalPrice(value: Double?): String = value?.let(::price) ?: "—"
fun percent(value: Double): String = String.format(Locale.US, "%+.2f%%", value)
fun optionalPercent(value: Double?): String = value?.let(::percent) ?: "—"
fun leverage(value: Double): String = if (value <= 0) "—" else String.format(Locale.US, "%.2fx", value)
fun volume(value: Double): String = String.format(Locale.US, "%.2f", value)
fun age(value: Double?): String = value?.let { String.format(Locale.US, "%.1fs", max(0.0, it)) } ?: "—"

fun shortDateTime(value: String): String = runCatching {
    OffsetDateTime.parse(value).toInstant().atZone(deviceZone).format(DateTimeFormatter.ofPattern("dd MMM HH:mm:ss"))
}.getOrDefault(value.ifBlank { "—" })

fun dateOnly(value: String): String = runCatching {
    OffsetDateTime.parse(value).toInstant().atZone(deviceZone).format(DateTimeFormatter.ofPattern("dd MMM yy"))
}.getOrDefault(value.ifBlank { "—" })

fun timeOnly(value: String): String = runCatching {
    OffsetDateTime.parse(value).toInstant().atZone(deviceZone).format(DateTimeFormatter.ofPattern("HH:mm:ss"))
}.getOrDefault(value.ifBlank { "—" })

fun humanProtection(value: String): String {
    val normalized = value.trim()
    if (normalized.isBlank() || normalized.equals("none", true)) return "None"
    if (normalized.startsWith("EXIT_BRACKET:", true)) return "Closing position: ${humanCondition(normalized.substringAfter(':'))}"
    if (normalized.contains(' ') && !normalized.contains('_')) return normalized
    return when (normalized.uppercase(Locale.US)) {
        "TSL_0.4000%", "FRIDAY_TIGHT_SL", "THURSDAY_TIGHT_SL" -> "Tight stop loss (0.4%)"
        "TSL_0.4000%+BE_TP" -> "Tight stop loss (0.4%) + break-even exit"
        "HARD_SL" -> "Hard stop loss"
        "HARD_SL+BE_TP" -> "Hard stop loss + break-even exit"
        else -> normalized.replace('_', ' ').lowercase(Locale.US).replaceFirstChar { it.uppercase() }
    }
}

fun humanCondition(value: String): String = when (value.trim().uppercase(Locale.US)) {
    "OH" -> "open-high target"
    "CH" -> "close-high target"
    "TO" -> "weekly timed close"
    "SL" -> "hard stop loss"
    "TSL" -> "tight stop loss"
    "BE", "BH" -> "break-even exit"
    "BROKER_SL" -> "broker stop loss"
    "BROKER_TP" -> "broker take profit"
    else -> value.replace('_', ' ').lowercase(Locale.US).replaceFirstChar { it.uppercase() }
}

fun countdown(target: String, nowEpochMs: Long = System.currentTimeMillis()): String = runCatching {
    val seconds = Duration.between(Instant.ofEpochMilli(nowEpochMs), OffsetDateTime.parse(target).toInstant()).seconds.coerceAtLeast(0)
    val hours = seconds / 3600
    val minutes = (seconds % 3600) / 60
    val remainingSeconds = seconds % 60
    "%02d:%02d:%02d".format(hours, minutes, remainingSeconds)
}.getOrDefault("—")

fun duration(seconds: Long): String {
    if (seconds <= 0) return "0m"
    val days = seconds / 86_400
    val hours = (seconds % 86_400) / 3_600
    val minutes = (seconds % 3_600) / 60
    return buildList {
        if (days > 0) add("${days}d")
        if (hours > 0) add("${hours}h")
        if (minutes > 0 || isEmpty()) add("${minutes}m")
    }.joinToString(" ")
}

fun secondsSince(timestamp: String, nowEpochMs: Long): Double? = runCatching {
    max(0.0, (nowEpochMs - OffsetDateTime.parse(timestamp).toInstant().toEpochMilli()) / 1000.0)
}.getOrNull()

fun secondsSinceEpoch(epochMs: Long, nowEpochMs: Long): Double? = if (epochMs <= 0L) null else max(0.0, (nowEpochMs - epochMs) / 1000.0)

fun liveSourceAge(baseAge: Double?, sourceTimestamp: String, nowEpochMs: Long): Double? {
    val elapsed = secondsSince(sourceTimestamp, nowEpochMs) ?: return baseAge
    return (baseAge ?: 0.0) + elapsed
}
