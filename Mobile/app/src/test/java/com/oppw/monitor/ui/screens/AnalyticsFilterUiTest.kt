package com.oppw.monitor.ui.screens

import com.oppw.monitor.data.AnalyticsFilters
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class AnalyticsFilterUiTest {
    @Test
    fun allHistoryShowsMaximumAndAllowsSelectingShorterRollingWindow() {
        val filters = AnalyticsFilters(rollingWeeks = 4, allHistory = true)

        assertEquals("83", analyticsRollingWeeksInput(filters, availableWeeks = 83))
        assertFalse(analyticsRollingWeeksCanApply("83", filters, availableWeeks = 83))
        assertTrue(analyticsRollingWeeksCanApply("4", filters, availableWeeks = 83))
    }

    @Test
    fun rollingWindowKeepsItsRequestedValue() {
        val filters = AnalyticsFilters(rollingWeeks = 12, allHistory = false)

        assertEquals("12", analyticsRollingWeeksInput(filters, availableWeeks = 83))
        assertFalse(analyticsRollingWeeksCanApply("12", filters, availableWeeks = 83))
        assertTrue(analyticsRollingWeeksCanApply("8", filters, availableWeeks = 83))
    }

    @Test
    fun rollingWindowDateRoundTripsThroughTheDatePicker() {
        val date = "2026-05-17"

        assertEquals(date, analyticsDatePickerValue(analyticsDatePickerMillis(date)!!))
        assertEquals(null, analyticsDatePickerMillis("2026-02-30"))
    }
}
