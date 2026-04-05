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
                ON CONFLICT (channel_id) DO UPDATE SET
                    channel_name = $3,
                    channel_type = $4,
                    is_active = TRUE
            """, user_id, channel_id, channel_name, channel_type)

    async def remove_channel(self, channel_id):
        async with self.pool.acquire() as conn:
            await conn.execute("UPDATE channels SET is_active = FALSE WHERE channel_id = $1", channel_id)

    async def get_user_channels(self, user_id):
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                "SELECT * FROM channels WHERE user_id = $1 AND is_active = TRUE ORDER BY added_at DESC",
                user_id
            )

    async def get_channel(self, channel_id):
        async with self.pool.acquire() as conn:
            return await conn.fetchrow("SELECT * FROM channels WHERE channel_id = $1", channel_id)

    async def get_all_active_channels(self):
        async with self.pool.acquire() as conn:
            return await conn.fetch("SELECT * FROM channels WHERE is_active = TRUE")

    # ── Channel Settings ──────────────────────────────────────────
    async def get_channel_settings(self, channel_id):
        async with self.pool.acquire() as conn:
            settings = await conn.fetchrow(
                "SELECT * FROM channel_settings WHERE channel_id = $1", channel_id
            )
            if not settings:
                await conn.execute(
                    "INSERT INTO channel_settings (channel_id) VALUES ($1) ON CONFLICT DO NOTHING",
                    channel_id
                )
                settings = await conn.fetchrow(
                    "SELECT * FROM channel_settings WHERE channel_id = $1", channel_id
                )
            return settings

    async def update_channel_setting(self, channel_id, setting, value):
        async with self.pool.acquire() as conn:
            await self.get_channel_settings(channel_id)
            if isinstance(value, (dict, list)):
                value = json.dumps(value)
            await conn.execute(
                f"UPDATE channel_settings SET {setting} = $1 WHERE channel_id = $2",
                value, channel_id
            )

    # ── Pending Requests ──────────────────────────────────────────
    async def add_pending_request(self, channel_id, user_id, username=None, first_name=None):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO pending_requests (channel_id, user_id, username, first_name)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (channel_id, user_id) DO UPDATE SET
                    username = COALESCE($3, pending_requests.username),
                    first_name = COALESCE($4, pending_requests.first_name),
                    requested_at = NOW()
            """, channel_id, user_id, username, first_name)

    async def get_pending_requests(self, channel_id, limit=50, offset=0):
        async with self.pool.acquire() as conn:
            return await conn.fetch("""
                SELECT * FROM pending_requests
                WHERE channel_id = $1 AND status = 'pending'
                ORDER BY requested_at DESC
                LIMIT $2 OFFSET $3
            """, channel_id, limit, offset)

    async def get_pending_count(self, channel_id):
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT COUNT(*) as count FROM pending_requests WHERE channel_id = $1 AND status = 'pending'",
                channel_id
            )
            return row['count'] if row else 0

    async def approve_request(self, channel_id, user_id):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE pending_requests SET status = 'approved', processed_at = NOW()
                WHERE channel_id = $1 AND user_id = $2
            """, channel_id, user_id)

    async def decline_request(self, channel_id, user_id):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE pending_requests SET status = 'declined', processed_at = NOW()
                WHERE channel_id = $1 AND user_id = $2
            """, channel_id, user_id)

    async def batch_approve_requests(self, channel_id, user_ids):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE pending_requests SET status = 'approved', processed_at = NOW()
                WHERE channel_id = $1 AND user_id = ANY($2) AND status = 'pending'
            """, channel_id, user_ids)

    async def batch_decline_requests(self, channel_id, user_ids):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE pending_requests SET status = 'declined', processed_at = NOW()
                WHERE channel_id = $1 AND user_id = ANY($2) AND status = 'pending'
            """, channel_id, user_ids)

    async def approve_all_requests(self, channel_id):
        async with self.pool.acquire() as conn:
            result = await conn.execute("""
                UPDATE pending_requests SET status = 'approved', processed_at = NOW()
                WHERE channel_id = $1 AND status = 'pending'
            """, channel_id)
            count = int(result.split()[-1]) if result else 0
            return count

    async def decline_all_requests(self, channel_id):
        async with self.pool.acquire() as conn:
            result = await conn.execute("""
                UPDATE pending_requests SET status = 'declined', processed_at = NOW()
                WHERE channel_id = $1 AND status = 'pending'
            """, channel_id)
            count = int(result.split()[-1]) if result else 0
            return count

    # ── User Management ───────────────────────────────────────────
    async def add_user(self, user_id, username=None, first_name=None, referred_by=None):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO users (user_id, username, first_name, referred_by)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (user_id) DO UPDATE SET
                    username = COALESCE($2, users.username),
                    first_name = COALESCE($3, users.first_name),
                    last_active = NOW()
            """, user_id, username, first_name, referred_by)

    async def get_user(self, user_id):
        async with self.pool.acquire() as conn:
            return await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)

    async def get_total_users(self):
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT COUNT(*) as count FROM users")
            return row['count'] if row else 0

    async def get_active_users(self, days=7):
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT COUNT(*) as count FROM users WHERE last_active > NOW() - INTERVAL '1 day' * $1",
                days
            )
            return row['count'] if row else 0

    async def is_premium(self, user_id):
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT premium_until FROM users WHERE user_id = $1", user_id
            )
            if row and row['premium_until']:
                return row['premium_until'] > datetime.now()
            return False

    async def set_premium(self, user_id, until):
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE users SET premium_until = $1 WHERE user_id = $2",
                until, user_id
            )

    async def get_user_language(self, user_id):
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT language FROM users WHERE user_id = $1", user_id
            )
            return row['language'] if row else 'en'

    async def set_user_language(self, user_id, language):
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE users SET language = $1 WHERE user_id = $2",
                language, user_id
            )

    # ── Welcome Messages ──────────────────────────────────────────
    async def get_welcome_message(self, channel_id):
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(
                "SELECT * FROM welcome_messages WHERE channel_id = $1", channel_id
            )

    async def set_welcome_message(self, channel_id, message_text, media_type=None, media_file_id=None, buttons=None):
        async with self.pool.acquire() as conn:
            buttons_json = json.dumps(buttons) if buttons else None
            await conn.execute("""
                INSERT INTO welcome_messages (channel_id, message_text, media_type, media_file_id, buttons)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (channel_id) DO UPDATE SET
                    message_text = $2,
                    media_type = $3,
                    media_file_id = $4,
                    buttons = $5
            """, channel_id, message_text, media_type, media_file_id, buttons_json)

    async def delete_welcome_message(self, channel_id):
        async with self.pool.acquire() as conn:
            await conn.execute("DELETE FROM welcome_messages WHERE channel_id = $1", channel_id)

    # ── Force Subscribe ───────────────────────────────────────────
    async def get_force_sub_channels(self, channel_id):
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                "SELECT * FROM force_sub_channels WHERE source_channel_id = $1 AND is_active = TRUE",
                channel_id
            )

    async def add_force_sub_channel(self, source_channel_id, target_channel_id, target_channel_name):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO force_sub_channels (source_channel_id, target_channel_id, target_channel_name)
                VALUES ($1, $2, $3)
                ON CONFLICT (source_channel_id, target_channel_id) DO UPDATE SET
                    target_channel_name = $3,
                    is_active = TRUE
            """, source_channel_id, target_channel_id, target_channel_name)

    async def remove_force_sub_channel(self, source_channel_id, target_channel_id):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE force_sub_channels SET is_active = FALSE
                WHERE source_channel_id = $1 AND target_channel_id = $2
            """, source_channel_id, target_channel_id)

    # ── Analytics ─────────────────────────────────────────────────
    async def record_analytics(self, channel_id, event_type, count=1):
        today = date.today()
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO analytics (channel_id, event_date, event_type, count)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (channel_id, event_date, event_type) DO UPDATE SET
                    count = analytics.count + $4
            """, channel_id, today, event_type, count)

    async def get_analytics(self, channel_id, days=7):
        async with self.pool.acquire() as conn:
            return await conn.fetch("""
                SELECT event_date, event_type, count FROM analytics
                WHERE channel_id = $1 AND event_date >= NOW() - INTERVAL '1 day' * $2
                ORDER BY event_date DESC
            """, channel_id, days)

    async def get_analytics_summary(self, channel_id, days=7):
        async with self.pool.acquire() as conn:
            return await conn.fetch("""
                SELECT event_type, SUM(count) as total FROM analytics
                WHERE channel_id = $1 AND event_date >= NOW() - INTERVAL '1 day' * $2
                GROUP BY event_type
            """, channel_id, days)

    # ── Broadcast ─────────────────────────────────────────────────
    async def create_broadcast(self, user_id, channel_id, message_text, media_type=None, media_file_id=None, schedule_time=None):
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                INSERT INTO broadcasts (user_id, channel_id, message_text, media_type, media_file_id, schedule_time)
                VALUES ($1, $2, $3, $4, $5, $6)
                RETURNING id
            """, user_id, channel_id, message_text, media_type, media_file_id, schedule_time)
            return row['id']

    async def get_pending_broadcasts(self):
        async with self.pool.acquire() as conn:
            return await conn.fetch("""
                SELECT * FROM broadcasts
                WHERE status = 'pending' AND (schedule_time IS NULL OR schedule_time <= NOW())
                ORDER BY created_at ASC
            """)

    async def update_broadcast_status(self, broadcast_id, status, sent_count=0, failed_count=0):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE broadcasts SET status = $1, sent_count = $2, failed_count = $3
                WHERE id = $4
            """, status, sent_count, failed_count, broadcast_id)

    # ── Clone Bots ────────────────────────────────────────────────
    async def add_clone_bot(self, user_id, bot_token, bot_username):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO clone_bots (user_id, bot_token, bot_username)
                VALUES ($1, $2, $3)
                ON CONFLICT (bot_token) DO UPDATE SET
                    bot_username = $3,
                    is_active = TRUE
            """, user_id, bot_token, bot_username)

    async def get_user_clone_bots(self, user_id):
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                "SELECT * FROM clone_bots WHERE user_id = $1 AND is_active = TRUE",
                user_id
            )

    async def remove_clone_bot(self, bot_token):
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE clone_bots SET is_active = FALSE WHERE bot_token = $1",
                bot_token
            )

    async def get_clone_bot(self, bot_token):
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(
                "SELECT * FROM clone_bots WHERE bot_token = $1",
                bot_token
            )

    # ── Templates ─────────────────────────────────────────────────
    async def save_template(self, user_id, name, content, template_type='welcome'):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO templates (user_id, name, content, template_type)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (user_id, name) DO UPDATE SET
                    content = $3,
                    template_type = $4
            """, user_id, name, content, template_type)

    async def get_user_templates(self, user_id, template_type=None):
        async with self.pool.acquire() as conn:
            if template_type:
                return await conn.fetch(
                    "SELECT * FROM templates WHERE user_id = $1 AND template_type = $2 ORDER BY name",
                    user_id, template_type
                )
            return await conn.fetch(
                "SELECT * FROM templates WHERE user_id = $1 ORDER BY name",
                user_id
            )

    async def delete_template(self, user_id, name):
        async with self.pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM templates WHERE user_id = $1 AND name = $2",
                user_id, name
            )

    # ── Referral System ───────────────────────────────────────────
    async def get_referral_count(self, user_id):
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT COUNT(*) as count FROM users WHERE referred_by = $1",
                user_id
            )
            return row['count'] if row else 0

    async def get_top_referrers(self, limit=10):
        async with self.pool.acquire() as conn:
            return await conn.fetch("""
                SELECT referred_by as user_id, COUNT(*) as referral_count
                FROM users WHERE referred_by IS NOT NULL
                GROUP BY referred_by
                ORDER BY referral_count DESC
                LIMIT $1
            """, limit)
