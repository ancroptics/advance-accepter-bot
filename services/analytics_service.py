import io
import csv
import logging

logger = logging.getLogger(__name__)


async def generate_analytics_report(db, chat_id, days=7):
    """Generate analytics report for a channel."""
    try:
        stats = await db.get_channel_analytics(chat_id, days)
        if not stats:
            return None, 'No data available for the selected period.'

        event_counts = {}
        for row in stats:
            evt = row['event_type']
            event_counts[evt] = event_counts.get(evt, 0) + row['cnt']

        total_joins = event_counts.get('join_request', 0)
        total_approved = event_counts.get('approved', 0)
        total_dms = event_counts.get('dm_sent', 0)

        report = f"\ud83d\udcca *Analytics Report ({days} days)*\n\n\ud83d\udc65 Join Requests: {total_joins}\n\u2705 Approved: {total_approved}\n\ud83d\udce9 DMs Sent: {total_dms}\n"
        return report, None
    except Exception as e:
        logger.error(f'Analytics error: {e}')
        return None, str(e)


async def export_analytics_csv(db, chat_id):
    """Export channel join request data as CSV."""
    try:
        data = await db.get_channel_export_data(chat_id)
        if not data:
            return None

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['User ID', 'Username', 'First Name', 'Status', 'Request Time', 'Processed At', 'DM Sent'])
        for row in data:
            writer.writerow([
                row['user_id'], row.get('username', ''), row.get('first_name', ''),
                row.get('status', ''), row.get('request_time', ''),
                row.get('processed_at', ''), row.get('dm_sent', False),
            ])
        output.seek(0)
        return output.getvalue()
    except Exception as e:
        logger.error(f'Export error: {e}')
        return None
