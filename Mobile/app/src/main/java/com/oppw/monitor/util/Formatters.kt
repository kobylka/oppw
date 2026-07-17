package com.oppw.monitor.util

import java.text.NumberFormat
import java.time.Duration
import java.time.OffsetDateTime
import java.time.format.DateTimeFormatter
import java.util.Locale

private val number = NumberFormat.getNumberInstance(Locale.US).apply {
    minimumFractionDigits = 2
    maximumFractionDigits = 2
}

fun money(value: Double, currency: String): String = "${number.format(value)} $currency"
fun price(value: Double): String = if (value == 0.0) "—" else String.format(Locale.US, "%,.2f", value)
fun percent(value: Double): String = String.format(Locale.US, "%+.2f%%", value)
fun leverage(value: Double): String = if (value <= 0) "—" else String.format(Locale.US, "%.2fx", value)
fun volume(value: Double): String = String.format(Locale.US, "%.2f", value)
fun age(value: Double?): String = value?.let { String.format(Locale.US, "%.1fs", it) } ?: "—"

fun shortDateTime(value: String): String = runCatching {
    OffsetDateTime.parse(value).format(DateTimeFormatter.ofPattern("dd MMM HH:mm:ss"))
}.getOrDefault(value)

fun timeOnly(value: String): String = runCatching {
    OffsetDateTime.parse(value).format(DateTimeFormatter.ofPattern("HH:mm:ss"))
}.getOrDefault(value)

fun countdown(target: String): String = runCatching {
    val seconds = Duration.between(OffsetDateTime.now(), OffsetDateTime.parse(target)).seconds.coerceAtLeast(0)
    val hours = seconds / 3600
    val minutes = (seconds % 3600) / 60
    val remainingSeconds = seconds % 60
    "%02d:%02d:%02d".format(hours, minutes, remainingSeconds)
}.getOrDefault("—")
