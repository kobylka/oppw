package com.oppw.monitor.data

import androidx.paging.PagingSource
import androidx.paging.PagingState

class EventsPagingSource(
    private val repository: StatusRepository,
    private val accountKey: String,
    private val buySellOnly: Boolean,
    private val eventName: String?,
    private val onTotalMatching: (Int) -> Unit,
) : PagingSource<Long, MonitorEvent>() {
    override suspend fun load(params: LoadParams<Long>): LoadResult<Long, MonitorEvent> = try {
        val page = repository.events(accountKey, params.key, params.loadSize, buySellOnly, eventName)
        onTotalMatching(page.totalMatching)
        LoadResult.Page(data = page.events, prevKey = null, nextKey = if (page.hasMore) page.nextBeforeId else null)
    } catch (error: Throwable) {
        LoadResult.Error(error)
    }

    override fun getRefreshKey(state: PagingState<Long, MonitorEvent>): Long? = null
}
