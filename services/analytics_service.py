import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class AnalyticsService:
    def __init__(self, db):
        self.db = db
        self._cache = {}
        self._cache_ttl = 300  # 5 minutes

    async def get_channel_analytics(self, chat_id):
        cache_key = f'analytics:{chat_id}'
        cached = self._cache.get(cache_key)
        if cached and (datetime.now() - cached['time']).seconds < self._cache_ttl:
            return cached['data']
        data = await self.db.get_channel_analytics(chat_id)
        self._cache[cache_key] = {'data': data, 'time': datetime.now()}
        return data

    async def get_growth_chart(self, chat_id, days=7):
        daily = await self.db.get_daily_stats_range(chat_id, days)
        if not daily:
            return 'No data yet.'
        max_val = max(d.get('requests_approved', 0) for d in daily) or 1
        chart = ''
        for d in daily:
            val = d.get('requests_approved', 0)
            bar_len = int(val / max_val * 10)
            bar = '\u2593' * bar_len + '\u2591' * (10 - bar_len)
            date_str = d['date'].strftime('%m/%d') if hasattr(d['date'], 'strftime') else str(d['date'])
            chart += f'{date_str} {bar} {val}\n'
        return chart

    async def get_peak_hours(self, chat_id):
        hours = await self.db.get_hourly_distribution(chat_id)
        if not hours:
            return 'No data yet.'
        max_hour = max(hours, key=lambda x: x.get('count', 0))
        min_hour = min(hours, key=lambda x: x.get('count', 0))
        return (
            f"\U0001f525 Most joins: {max_hour.get('hour', '?')}:00-{max_hour.get('hour', 0)+1}:00\n"
            f"\U0001f4c9 Slowest: {min_hour.get('hour', '?')}:00-{min_hour.get('hour', 0)+1}:00"
        )

    async def get_platform_overview(self):
        return await self.db.get_platform_stats()

    def clear_cache(self):
        self._cache.clear()
