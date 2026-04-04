import io
import csv
from database.models import get_daily_stats, get_channel_analytics
import logging

logger = logging.getLogger(__name__)


async def generate_analytics_report(db, owner_id, channel_id=None, days=7):
    try:
        stats = await get_daily_stats(db, owner_id, channel_id, days)
        if not stats:
            return None, 'No data available for the selected period.'

        total_joins = sum(s.get('joins', 0) for s in stats)
        total_leaves = sum(s.get('leaves', 0) for s in stats)
        total_requests = sum(s.get('requests', 0) for s in stats)
        net_growth = total_joins - total_leaves
        approval_rate = (total_joins / total_requests * 100) if total_requests > 0 else 0

        report = f"""📊 *Analytics Report ({days} days)*

👥 Total Join Requests: {total_requests}
✅ Approved: {total_joins}
❌ Left: {total_leaves}
📈 Net Growth: {net_growth:+d}
🎯 Approval Rate: {approval_rate:.1f}%

*Daily Breakdown:*
"""
        for s in stats[-7:]:
            day = s.get('date', 'N/A')
            j = s.get('joins', 0)
            l = s.get('leaves', 0)
            report += f"  {day}: +{j} / -{l} (net {j-l:+d})\n"

        return report, None
    except Exception as e:
        logger.error(f'Analytics error: {e}')
        return None, str(e)


async def export_analytics_csv(db, owner_id, channel_id=None, days=30):
    stats = await get_daily_stats(db, owner_id, channel_id, days)
    if not stats:
        return None

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Date', 'Joins', 'Leaves', 'Net', 'Requests'])
    for s in stats:
        writer.writerow([
            s.get('date', ''),
            s.get('joins', 0),
            s.get('leaves', 0),
            s.get('joins', 0) - s.get('leaves', 0),
            s.get('requests', 0),
        ])
    output.seek(0)
    return output.getvalue()
