import json
import logging
import os
from datetime import datetime, date, timedelta

logger = logging.getLogger(__name__)

MIGRATION_SQL_PATH = os.path.join(os.path.dirname(__file__), 'migrations', '001_initial_schema.sql')

class DatabaseModels:
    def __init__(self, pool):
        self.pool = pool

    async def setup(self):
        """Run migrations"""
        try:
            with open(MIGRATION_SQL_PATH, 'r') as f:
                sql = f.read()
            async with self.pool.acquire() as conn:
                await conn.execute(sql)
            logger.info("Database migrations completed successfully")
        except Exception as e:
            logger.error(f"Migration error: {e}")
            raise

    # ── Channel CRUD ──────────────────────────────────────────────
    async def add_channel(self, user_id, channel_id, channel_name, channel_type='channel'):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO channels (user_id, channel_id, channel_name, channel_type)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (user_id, channel_id) DO UPDATE
                SET channel_name = $3, channel_type = $4
            """, user_id, channel_id, channel_name, channel_type)

    async def remove_channel(self, user_id, channel_id):
        async with self.pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM channels WHERE user_id = $1 AND channel_id = $2",
                user_id, channel_id)

    async def get_channels(self, user_id):
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                "SELECT * FROM channels WHERE user_id = $1", user_id)

    async def get_channel(self, user_id, channel_id):
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(
                "SELECT * FROM channels WHERE user_id = $1 AND channel_id = $2",
                user_id, channel_id)

    # ── Settings ────────────────────────────────────────────────
    async def get_settings(self, user_id):
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM user_settings WHERE user_id = $1", user_id)
            if row:
                return dict(row)
            await conn.execute("""
                INSERT INTO user_settings (user_id) VALUES ($1)
                ON CONFLICT DO NOTHING
            """, user_id)
            row = await conn.fetchrow(
                "SELECT * FROM user_settings WHERE user_id = $1", user_id)
            return dict(row) if row else {}

    async def update_setting(self, user_id, key, value):
        allowed = {
            'auto_accept', 'auto_decline', 'keyword_filter',
            'welcome_message', 'language', 'min_members',
            'auto_accept_delay', 'auto_decline_delay',
            'working_hours_start', 'working_hours_end',
            'auto_accept_premium', 'block_duplicates',
            'accepted_count', 'declined_count',
            'filter_mode', 'notification_chat_id'
        }
        if key not in allowed:
            raise ValueError(f"Invalid setting: {key}")
        async with self.pool.acquire() as conn:
            await conn.execute(f"""
                INSERT INTO user_settings (user_id, {key})
                VALUES ($1, $2)
                ON CONFLICT (user_id) DO UPDATE SET {key} = $2
            """, user_id, value)

    async def increment_counter(self, user_id, counter_type):
        col = 'accepted_count' if counter_type == 'accepted' else 'declined_count'
        async with self.pool.acquire() as conn:
            await conn.execute(f"""
                INSERT INTO user_settings (user_id, {col})
                VALUES ($1, 1)
                ON CONFLICT (user_id) DO UPDATE SET {col} = user_settings.{col} + 1
            """, user_id)

    async def reset_counters(self, user_id):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE user_settings
                SET accepted_count = 0, declined_count = 0
                WHERE user_id = $1
            """, user_id)

    # ── Keywords ───────────────────────────────────────────────
    async def add_keyword(self, user_id, keyword, action='accept'):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO keywords (user_id, keyword, action)
                VALUES ($1, $2, $3)
                ON CONFLICT (user_id, keyword) DO UPDATE SET action = $3
            """, user_id, keyword.lower(), action)

    async def remove_keyword(self, user_id, keyword):
        async with self.pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM keywords WHERE user_id = $1 AND keyword = $2",
                user_id, keyword.lower())

    async def get_keywords(self, user_id, action=None):
        async with self.pool.acquire() as conn:
            if action:
                return await conn.fetch(
                    "SELECT * FROM keywords WHERE user_id = $1 AND action = $2",
                    user_id, action)
            return await conn.fetch(
                "SELECT * FROM keywords WHERE user_id = $1", user_id)

    # ── Scheduled Actions ──────────────────────────────────────
    async def add_scheduled_action(self, user_id, channel_id, action, scheduled_time, request_data=None):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO scheduled_actions (user_id, channel_id, action, scheduled_time, request_data)
                VALUES ($1, $2, $3, $4, $5)
            """, user_id, channel_id, action, scheduled_time,
                json.dumps(request_data) if request_data else None)

    async def get_pending_actions(self):
        async with self.pool.acquire() as conn:
            return await conn.fetch("""
                SELECT * FROM scheduled_actions
                WHERE status = 'pending' AND scheduled_time <= NOW()
                ORDER BY scheduled_time
            """)

    async def update_action_status(self, action_id, status):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE scheduled_actions SET status = $2 WHERE id = $1
            """, action_id, status)

    async def get_scheduled_actions(self, user_id):
        async with self.pool.acquire() as conn:
            return await conn.fetch("""
                SELECT * FROM scheduled_actions
                WHERE user_id = $1 AND status = 'pending'
                ORDER BY scheduled_time
            """, user_id)

    async def cancel_scheduled_action(self, action_id, user_id):
        async with self.pool.acquire() as conn:
            return await conn.execute("""
                UPDATE scheduled_actions
                SET status = 'cancelled'
                WHERE id = $1 AND user_id = $2 AND status = 'pending'
            """, action_id, user_id)

    # ── Request Logs ────────────────────────────────────────────
    async def log_request(self, user_id, channel_id, request_type, status, request_data=None):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO request_logs (user_id, channel_id, request_type, status, request_data)
                VALUES ($1, $2, $3, $4, $5)
            """, user_id, channel_id, request_type, status,
                json.dumps(request_data) if request_data else None)

    async def get_request_logs(self, user_id, limit=50):
        async with self.pool.acquire() as conn:
            return await conn.fetch("""
                SELECT * FROM request_logs
                WHERE user_id = $1
                ORDER BY created_at DESC
                LIMIT $2
            """, user_id, limit)

    async def get_stats(self, user_id):
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT
                    COUNT(*) FILTER (WHERE status = 'accepted') as accepted,
                    COUNT(*) FILTER (WHERE status = 'declined') as declined,
                    COUNT(*) FILTER (WHERE status = 'pending') as pending,
                    COUNT(*) as total
                FROM request_logs WHERE user_id = $1
            """, user_id)
            return dict(row) if row else {'accepted': 0, 'declined': 0, 'pending': 0, 'total': 0}

    # ── Premium / Subscription ──────────────────────────────────
    async def get_subscription(self, user_id):
        async with self.pool.acquire() as conn:
            return await conn.fetchrow("""
                SELECT * FROM subscriptions
                WHERE user_id = $1 AND status = 'active'
                AND expires_at > NOW()
                ORDER BY expires_at DESC LIMIT 1
            """, user_id)

    async def create_subscription(self, user_id, plan, duration_days, payment_id=None):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE subscriptions SET status = 'expired'
                WHERE user_id = $1 AND status = 'active'
            """, user_id)
            await conn.execute("""
                INSERT INTO subscriptions (user_id, plan, status, expires_at, payment_id)
                VALUES ($1, $2, 'active', NOW() + INTERVAL '1 day' * $3, $4)
            """, user_id, plan, duration_days, payment_id)

    async def is_premium(self, user_id):
        sub = await self.get_subscription(user_id)
        return sub is not None

    async def cancel_subscription(self, user_id):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE subscriptions SET status = 'cancelled'
                WHERE user_id = $1 AND status = 'active'
            """, user_id)

    # ── Payments ────────────────────────────────────────────────
    async def create_payment(self, user_id, amount, currency, provider, plan):
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                INSERT INTO payments (user_id, amount, currency, provider, plan, status)
                VALUES ($1, $2, $3, $4, $5, 'pending')
                RETURNING id
            """, user_id, amount, currency, provider, plan)
            return row['id'] if row else None

    async def update_payment_status(self, payment_id, status, provider_payment_id=None):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE payments
                SET status = $2, provider_payment_id = $3, updated_at = NOW()
                WHERE id = $1
            """, payment_id, status, provider_payment_id)

    async def get_payment(self, payment_id):
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(
                "SELECT * FROM payments WHERE id = $1", payment_id)

    async def get_user_payments(self, user_id):
        async with self.pool.acquire() as conn:
            return await conn.fetch("""
                SELECT * FROM payments WHERE user_id = $1
                ORDER BY created_at DESC
            """, user_id)

    # ── Referrals ───────────────────────────────────────────────
    async def create_referral_code(self, user_id, code):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO referrals (user_id, referral_code)
                VALUES ($1, $2)
                ON CONFLICT (user_id) DO UPDATE SET referral_code = $2
            """, user_id, code)

    async def get_referral_code(self, user_id):
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT referral_code FROM referrals WHERE user_id = $1", user_id)
            return row['referral_code'] if row else None

    async def use_referral(self, referral_code, referred_user_id):
        async with self.pool.acquire() as conn:
            ref = await conn.fetchrow(
                "SELECT * FROM referrals WHERE referral_code = $1", referral_code)
            if not ref:
                return False
            if ref['user_id'] == referred_user_id:
                return False
            await conn.execute("""
                UPDATE referrals
                SET referral_count = referral_count + 1
                WHERE referral_code = $1
            """, referral_code)
            return True

    async def get_referral_stats(self, user_id):
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(
                "SELECT * FROM referrals WHERE user_id = $1", user_id)

    # ── Admin helpers ───────────────────────────────────────────
    async def get_all_users(self, limit=100, offset=0):
        async with self.pool.acquire() as conn:
            return await conn.fetch("""
                SELECT DISTINCT user_id FROM user_settings
                ORDER BY user_id
                LIMIT $1 OFFSET $2
            """, limit, offset)

    async def get_user_count(self):
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT COUNT(DISTINCT user_id) as count FROM user_settings")
            return row['count'] if row else 0

    async def get_active_channels_count(self):
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT COUNT(*) as count FROM channels")
            return row['count'] if row else 0

    async def get_total_requests(self):
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT COUNT(*) as count FROM request_logs")
            return row['count'] if row else 0

    async def get_active_subscriptions(self):
        async with self.pool.acquire() as conn:
            return await conn.fetch("""
                SELECT * FROM subscriptions
                WHERE status = 'active' AND expires_at > NOW()
            """)

    async def broadcast_message(self, message):
        async with self.pool.acquire() as conn:
            users = await conn.fetch(
                "SELECT DISTINCT user_id FROM user_settings")
            return [row['user_id'] for row in users]

    async def get_revenue_stats(self):
        async with self.pool.acquire() as conn:
            return await conn.fetchrow("""
                SELECT
                    COUNT(*) FILTER (WHERE status = 'completed') as total_payments,
                    COALESCE(SUM(amount) FILTER (WHERE status = 'completed'), 0) as total_revenue,
                    COUNT(*) FILTER (WHERE status = 'completed'
                        AND created_at > NOW() - INTERVAL '30 days') as monthly_payments,
                    COALESCE(SUM(amount) FILTER (WHERE status = 'completed'
                        AND created_at > NOW() - INTERVAL '30 days'), 0) as monthly_revenue
                FROM payments
            """)

    async def get_top_referrers(self, limit=10):
        async with self.pool.acquire() as conn:
            return await conn.fetch("""
                SELECT user_id, referral_code, referral_count
                FROM referrals
                WHERE referral_count > 0
                ORDER BY referral_count DESC
                LIMIT $1
            """, limit)
