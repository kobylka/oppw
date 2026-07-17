package com.oppw.monitor.util

import java.text.NumberFormat
import java.time.Duration
import java.time.Instant
import java.time.OffsetDateTime
import java.time.format.DateTimeFormatter
import java.util.Locale
import kotlin.math.max

private val number = NumberFormat.getNumberInstance(Locale.US).apply {
    minimumFractionDigits = 2
    maximumFractionDigits = 2
}

fun money(value: Double, currency: String): String = "${number.format(value)} $currency"
fun price(value: Double): String = if (value == 0.0) "—" else String.format(Locale.US, "%,.2f", value)
fun optionalPrice(value: Double?): String = value?.let(::price) ?: "—"
fun percent(value: Double): String = String.format(Locale.US, "%+.2f%%", value)
fun optionalPercent(value: Double?): String = value?.let(::percent) ?: "—"
fun leverage(value: Double): String = if (value <= 0) "—" else String.format(Locale.US, "%.2fx", value)
fun volume(value: Double): String = String.format(Locale.US, "%.2f", value)
fun age(value: Double?): String = value?.let { String.format(Locale.US, "%.1fs", max(0.0, it)) } ?: "—"

fun shortDateTime(value: String): String = runCatching {
    OffsetDateTime.parse(value).format(DateTimeFormatter.ofPattern("dd MMM HH:mm:ss"))
}.getOrDefault(value.ifBlank { "—" })

fun timeOnly(value: String): String = runCatching {
    OffsetDateTime.parse(value).format(DateTimeFormatter.ofPattern("HH:mm:ss.SSS"))
}.getOrDefault(value.ifBlank { "—" })

fun countdown(target: String, nowEpochMs: Long = System.currentTimeMillis()): String = runCatching {
    val seconds = Duration.between(Instant.ofEpochMilli(nowEpochMs), OffsetDateTime.parse(target).toInstant()).seconds.coerceAtLeast(0)
    val hours = seconds / 3600
    val minutes = (seconds % 3600) / 60
    val remainingSeconds = seconds % 60
    "%02d:%02d:%02d".format(hours, minutes, remainingSeconds)
}.getOrDefault("—")

fun secondsSince(timestamp: String, nowEpochMs: Long): Double? = runCatching {
    max(0.0, (nowEpochMs - OffsetDateTime.parse(timestamp).toInstant().toEpochMilli()) / 1000.0)
}.getOrNull()

fun secondsSinceEpoch(epochMs: Long, nowEpochMs: Long): Double? = if (epochMs <= 0L) null else max(0.0, (nowEpochMs - epochMs) / 1000.0)

fun liveSourceAge(baseAge: Double?, sourceTimestamp: String, nowEpochMs: Long): Double? {
    val elapsed = secondsSince(sourceTimestamp, nowEpochMs) ?: return baseAge
    return (baseAge ?: 0.0) + elapsed
}
