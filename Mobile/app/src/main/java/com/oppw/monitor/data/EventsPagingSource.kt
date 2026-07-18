package com.oppw.monitor.data

import androidx.paging.PagingSource
import androidx.paging.PagingState
import com.oppw.monitor.util.isRoutineEvent

class EventsPagingSource(
    private val repository: StatusRepository,
    private val accountKey: String,
    private val buySellOnly: Boolean,
    private val hideRoutine: Boolean,
    private val eventName: String?,
    private val onTotalMatching: (Int) -> Unit,
) : PagingSource<Long, MonitorEvent>() {
    override suspend fun load(params: LoadParams<Long>): LoadResult<Long, MonitorEvent> = try {
        val requested = params.loadSize.coerceAtLeast(1)
        val visible = mutableListOf<MonitorEvent>()
        var cursor = params.key
        var nextKey: Long? = null
        var totalMatching = 0
        var pagesRead = 0
        var hasMore = true

        while (visible.size < requested && hasMore && pagesRead < MAX_BACKFILL_PAGES) {
            val limit = (requested - visible.size).coerceAtLeast(1)
            val page = repository.events(accountKey, cursor, limit, buySellOnly, hideRoutine, eventName)
            totalMatching = page.totalMatching
            val filtered = if (hideRoutine) page.events.filterNot(::isRoutineEvent) else page.events
            visible += filtered

            val candidate = page.nextBeforeId
            hasMore = page.hasMore && candidate != null && candidate != cursor
            nextKey = if (hasMore) candidate else null
            cursor = candidate
            pagesRead++
        }

        onTotalMatching(totalMatching)
        LoadResult.Page(data = visible, prevKey = null, nextKey = nextKey)
    } catch (error: Throwable) {
        LoadResult.Error(error)
    }

    override fun getRefreshKey(state: PagingState<Long, MonitorEvent>): Long? = null

    companion object {
        private const val MAX_BACKFILL_PAGES = 20
    }
}
