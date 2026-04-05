import json
import logging
import os
from datetime import datetime, date, timedelta

logger = logging.getLogger(__name__)

MIGRATION_SQL_PATH = os.path.join(os.path.dirname(__file__), 'migrations', '001_initial_schema.sql')

class DatabaseModels:
    def __init__(self, pool):
        self.db = pool

    async def run_migrations(self):
        try:
            with open(MIGRATION_SQL_PATH, 'r') as f:
                sql = f.read()
            await self.db.execute(sql)
            # Add columns that may be missing from initial migration
            extra_ddl = """
            DO $$ BEGIN
                ALTER TABLE managed_channels ADD COLUMN IF NOT EXISTS support_username TEXT;
                ALTER TABLE managed_channels ADD COLUMN IF NOT EXISTS referral_enabled BOOLEAN DEFAULT FALSE;
                ALTER TABLE managed_channels ADD COLUMN IF NOT EXISTS welcome_messages_json TEXT;
            EXCEPTION WHEN others THEN NULL;
            END $$;
            """
            await self.db.execute(extra_ddl)
            logger.info('Database migrations completed')
        except Exception as e:
            logger.error(f'Migration error: {e}')

    # ==================== OWNER / ADMIN ====================
    async def get_owner(self, user_id):
        return await self.db.fetchrow('SELECT * FROM channel_owners WHERE user_id = $1', user_id)

    async def create_owner(self, user_id, username=None, first_name=None, plan='free'):
        return await self.db.execute("""
            INSERT INTO channel_owners (user_id, username, first_name, tier, registered_at)
            VALUES ($1, $2, $3, $4, NOW())
            ON CONFLICT (user_id) DO UPDATE SET
                username = COALESCE($2, channel_owners.username),
                first_name = COALESCE($3, channel_owners.first_name)
        """, user_id, username, first_name, plan)

    async def get_owner_plan(self, user_id):
        row = await self.db.fetchrow('SELECT tier FROM channel_owners WHERE user_id = $1', user_id)
        if not row:
            return 'free', None
        return row['tier'], None

    async def set_owner_plan(self, user_id, plan, expires=None):
        return await self.db.execute("""
            UPDATE channel_owners SET tier = $2 WHERE user_id = $1
        """, user_id, plan)

    async def get_all_owners(self):
        return await self.db.fetch('SELECT * FROM channel_owners ORDER BY registered_at')

    async def upsert_owner(self, user_id, username=None, first_name=None, last_name=None):
        """Create or update a channel owner."""
        return await self.db.execute("""
            INSERT INTO channel_owners (user_id, username, first_name, last_name, tier, registered_at, last_active)
            VALUES ($1, $2, $3, $4, 'free', NOW(), NOW())
            ON CONFLICT (user_id) DO UPDATE SET
                username = COALESCE($2, channel_owners.username),
                first_name = COALESCE($3, channel_owners.first_name),
                last_name = COALESCE($4, channel_owners.last_name),
                last_active = NOW()
        """, user_id, username, first_name, last_name)

    async def upsert_channel(self, chat_id, owner_id, chat_title=None, chat_username=None, chat_type='channel'):
        """Create or update a managed channel."""
        return await self.db.execute("""
            INSERT INTO managed_channels (chat_id, owner_id, chat_title, chat_username, chat_type, is_active, bot_is_admin, added_at)
            VALUES ($1, $2, $3, $4, $5, TRUE, TRUE, NOW())
            ON CONFLICT (chat_id) DO UPDATE SET
                owner_id = $2, chat_title = COALESCE($3, managed_channels.chat_title),
                chat_username = COALESCE($4, managed_channels.chat_username),
                chat_type = $5, is_active = TRUE, bot_is_admin = TRUE
        """, chat_id, owner_id, chat_title, chat_username, chat_type)

    # ==================== CHANNELS ====================
    async def get_channel(self, chat_id):
        return await self.db.fetchrow('SELECT * FROM managed_channels WHERE chat_id = $1', chat_id)

    async def get_owner_channels(self, owner_id):
        return await self.db.fetch(
            'SELECT * FROM managed_channels WHERE owner_id = $1 ORDER BY added_at', owner_id)

    async def add_channel(self, chat_id, owner_id, chat_title=None, chat_type='channel', username=None):
        return await self.db.execute("""
            INSERT INTO managed_channels (chat_id, owner_id, chat_title, chat_type, chat_username, added_at)
            VALUES ($1, $2, $3, $4, $5, NOW())
            ON CONFLICT (chat_id) DO UPDATE SET
                owner_id = $2, chat_title = COALESCE($3, managed_channels.chat_title),
                chat_type = $4, chat_username = COALESCE($5, managed_channels.chat_username)
        """, chat_id, owner_id, chat_title, chat_type, username)

    async def remove_channel(self, chat_id):
        return await self.db.execute('DELETE FROM managed_channels WHERE chat_id = $1', chat_id)

    async def get_all_channels(self):
        return await self.db.fetch('SELECT * FROM managed_channels ORDER BY added_at')

    async def get_all_active_channels(self):
        """Get all active managed channels."""
        return await self.db.fetch(
            'SELECT * FROM managed_channels WHERE is_active = TRUE')

    async def update_channel_setting(self, chat_id, key, value):
        allowed_columns = [
            'chat_title', 'chat_username', 'approve_mode', 'auto_approve',
            'welcome_dm_enabled', 'welcome_message', 'welcome_media_type',
            'welcome_media_file_id', 'welcome_buttons_json',
            'force_subscribe_enabled', 'force_subscribe_channels',
            'drip_rate', 'drip_interval', 'drip_quantity',
            'support_username', 'member_count',
            'pending_requests',
            'cross_promo_enabled', 'referral_enabled',
            'welcome_messages_json', 'force_sub_timeout',
            'force_sub_mode',
            'is_active', 'bot_is_admin',
        ]
        if key not in allowed_columns:
            raise ValueError(f'Invalid column: {key}')
        if isinstance(value, (dict, list)):
            value = json.dumps(value)
        return await self.db.execute(
            f'UPDATE managed_channels SET {key} = $2 WHERE chat_id = $1', chat_id, value)

    # ==================== JOIN REQUESTS ====================
    async def save_join_request(self, user_id, chat_id, username=None, first_name=None, user_language=None):
        return await self.db.execute("""
            INSERT INTO join_requests (user_id, chat_id, username, first_name, user_language, request_time, status)
            VALUES ($1, $2, $3, $4, $5, NOW(), 'pending')
            ON CONFLICT (user_id, chat_id) DO UPDATE SET
                status = 'pending', username = COALESCE($3, join_requests.username),
                first_name = COALESCE($4, join_requests.first_name),
                user_language = COALESCE($5, join_requests.user_language),
                request_time = NOW()
        """, user_id, chat_id, username, first_name, user_language)

    async def get_pending_count(self, chat_id):
        val = await self.db.fetchval(
            "SELECT COUNT(*) FROM join_requests WHERE chat_id = $1 AND status = 'pending'", chat_id)
        return val or 0

    async def get_pending_requests(self, chat_id, limit=100):
        return await self.db.fetch("""
            SELECT * FROM join_requests WHERE chat_id = $1 AND status = 'pending'
            ORDER BY request_time LIMIT $2
        """, chat_id, limit)

    async def update_join_request_status(self, user_id, chat_id, status, processed_by='auto'):
        return await self.db.execute("""
            UPDATE join_requests SET status = $3, processed_at = NOW(), processed_by = $4
            WHERE user_id = $1 AND chat_id = $2
        """, user_id, chat_id, status, processed_by)

    async def update_join_request_after_approve(self, user_id, chat_id, dm_sent=False, dm_failed_reason=None, dm_message_id=None, processed_by='auto'):
        return await self.db.execute("""
            UPDATE join_requests SET status = 'approved', processed_at = NOW(),
                dm_attempted = TRUE, dm_sent = $3, dm_failed_reason = $4
            WHERE user_id = $1 AND chat_id = $2
        """, user_id, chat_id, dm_sent, dm_failed_reason)

    async def update_join_request_force_sub(self, user_id, chat_id, required):
        return await self.db.execute("""
            UPDATE join_requests SET force_sub_required = $3
            WHERE user_id = $1 AND chat_id = $2
        """, user_id, chat_id, str(required))

    async def update_force_sub_completed(self, user_id, chat_id):
        return await self.db.execute("""
            UPDATE join_requests SET force_sub_completed = TRUE, force_sub_completed_at = NOW()
            WHERE user_id = $1 AND chat_id = $2
        """, user_id, chat_id)

    # ==================== END USERS ====================
    async def upsert_end_user(self, user_id, username=None, first_name=None, last_name=None,
                              language_code=None, source=None, source_channel=None):
        return await self.db.execute("""
            INSERT INTO end_users (user_id, username, first_name, last_name, language_code,
                                   source, source_channel, first_seen_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, NOW())
            ON CONFLICT (user_id) DO UPDATE SET
                username = COALESCE($2, end_users.username),
                first_name = COALESCE($3, end_users.first_name),
                last_name = COALESCE($4, end_users.last_name),
                language_code = COALESCE($5, end_users.language_code),
                last_active = NOW()
        """, user_id, username, first_name, last_name, language_code, source, source_channel)

    async def get_end_user(self, user_id):
        return await self.db.fetchrow('SELECT * FROM end_users WHERE user_id = $1', user_id)

    async def set_referrer(self, user_id, referrer_id):
        """Set referrer for a user and increment referrer's count."""
        await self.db.execute(
            'UPDATE end_users SET referrer_id = $2 WHERE user_id = $1', user_id, referrer_id)
        await self.db.execute(
            'UPDATE end_users SET referral_count = referral_count + 1 WHERE user_id = $1', referrer_id)

    async def award_referral_coins(self, user_id, amount):
        """Award coins to a user for referral."""
        return await self.db.execute(
            'UPDATE end_users SET coins = coins + $2 WHERE user_id = $1', user_id, amount)

    async def mark_user_blocked(self, user_id):
        return await self.db.execute("""
            UPDATE end_users SET has_blocked_bot = TRUE WHERE user_id = $1
        """, user_id)

    async def get_channel_users(self, chat_id):
        return await self.db.fetch("""
            SELECT DISTINCT jr.user_id, jr.username, jr.first_name
            FROM join_requests jr
            WHERE jr.chat_id = $1 AND jr.status = 'approved'
            ORDER BY jr.first_name
        """, chat_id)

    async def get_channel_user_count(self, chat_id):
        """Get count of approved users for a channel."""
        val = await self.db.fetchval(
            "SELECT COUNT(DISTINCT user_id) FROM join_requests WHERE chat_id = $1 AND status = 'approved'", chat_id)
        return val or 0

    async def get_all_bot_users(self):
        return await self.db.fetch('SELECT user_id FROM end_users WHERE has_blocked_bot = FALSE')

    # ==================== ANALYTICS ====================
    async def log_event(self, event_type, owner_id=None, channel_id=None, user_id=None, data=None):
        return await self.db.execute("""
            INSERT INTO analytics_events (event_type, owner_id, channel_id, user_id, data, created_at)
            VALUES ($1, $2, $3, $4, $5, NOW())
        """, event_type, owner_id, channel_id, user_id, json.dumps(data) if data else None)

    async def get_analytics_summary(self, owner_id, days=30):
        result = {}
        result['total_requests'] = await self.db.fetchval("""
            SELECT COUNT(*) FROM join_requests jr
            JOIN managed_channels mc ON jr.chat_id = mc.chat_id
            WHERE mc.owner_id = $1 AND jr.request_time > NOW() - INTERVAL '%s days'
        """ % days, owner_id) or 0
        result['approved'] = await self.db.fetchval("""
            SELECT COUNT(*) FROM join_requests jr
            JOIN managed_channels mc ON jr.chat_id = mc.chat_id
            WHERE mc.owner_id = $1 AND jr.status = 'approved'
                AND jr.processed_at > NOW() - INTERVAL '%s days'
        """ % days, owner_id) or 0
        result['dm_sent'] = await self.db.fetchval("""
            SELECT COUNT(*) FROM join_requests jr
            JOIN managed_channels mc ON jr.chat_id = mc.chat_id
            WHERE mc.owner_id = $1 AND jr.dm_sent = TRUE
                AND jr.request_time > NOW() - INTERVAL '%s days'
        """ % days, owner_id) or 0
        result['dm_failed'] = await self.db.fetchval("""
            SELECT COUNT(*) FROM join_requests jr
            JOIN managed_channels mc ON jr.chat_id = mc.chat_id
            WHERE mc.owner_id = $1 AND jr.dm_attempted = TRUE AND jr.dm_sent = FALSE
                AND jr.request_time > NOW() - INTERVAL '%s days'
        """ % days, owner_id) or 0
        return result

    async def get_channel_analytics(self, chat_id):
        result = {}
        result['total_requests'] = await self.db.fetchval(
            "SELECT COUNT(*) FROM join_requests WHERE chat_id = $1", chat_id) or 0
        result['approved'] = await self.db.fetchval(
            "SELECT COUNT(*) FROM join_requests WHERE chat_id = $1 AND status = 'approved'", chat_id) or 0
        result['pending'] = await self.db.fetchval(
            "SELECT COUNT(*) FROM join_requests WHERE chat_id = $1 AND status = 'pending'", chat_id) or 0
        result['dm_sent'] = await self.db.fetchval(
            "SELECT COUNT(*) FROM join_requests WHERE chat_id = $1 AND dm_sent = TRUE", chat_id) or 0
        result['dm_failed'] = await self.db.fetchval(
            "SELECT COUNT(*) FROM join_requests WHERE chat_id = $1 AND dm_attempted = TRUE AND dm_sent = FALSE", chat_id) or 0
        result['declined'] = await self.db.fetchval(
            "SELECT COUNT(*) FROM join_requests WHERE chat_id = $1 AND status = 'declined'", chat_id) or 0
        return result

    # ==================== REFERRALS ====================
    async def get_referral_count(self, user_id):
        val = await self.db.fetchval(
            'SELECT referral_count FROM end_users WHERE user_id = $1', user_id)
        return val or 0

    async def add_coins(self, user_id, amount):
        return await self.db.execute("""
            UPDATE end_users SET coins = coins + $2 WHERE user_id = $1
        """, user_id, amount)

    # ==================== DRIP MODE ====================
    async def get_drip_channels(self):
        return await self.db.fetch("""
            SELECT mc.*, (SELECT COUNT(*) FROM join_requests jr WHERE jr.chat_id = mc.chat_id AND jr.status = 'pending') as actual_pending
            FROM managed_channels mc WHERE mc.approve_mode = 'drip'
        """)

    async def get_drip_batch(self, chat_id, limit=5):
        return await self.db.fetch("""
            SELECT * FROM join_requests
            WHERE chat_id = $1 AND status = 'pending'
            ORDER BY request_time
            LIMIT $2
        """, chat_id, limit)

    async def get_stale_pending_requests(self, chat_id, hours=48):
        return await self.db.fetch("""
            SELECT * FROM join_requests
            WHERE chat_id = $1 AND status = 'pending'
                AND request_time < NOW() - INTERVAL '1 hour' * $2
        """, chat_id, hours)

    async def get_expired_force_sub_requests(self, hours=24):
        """Get pending requests with force_sub_required that expired (older than X hours)."""
        return await self.db.fetch("""
            SELECT * FROM join_requests
            WHERE status = 'pending'
                AND force_sub_required IS NOT NULL
                AND force_sub_completed = FALSE
                AND request_time < NOW() - INTERVAL '1 hour' * $1
            ORDER BY request_time
        """, hours)

    async def bulk_save_pending_requests(self, chat_id, users):
        if not users:
            return 0
        count = 0
        for u in users:
            try:
                await self.db.execute("""
                    INSERT INTO join_requests (user_id, chat_id, username, first_name, request_time, status)
                    VALUES ($1, $2, $3, $4, NOW(), 'pending')
                    ON CONFLICT (user_id, chat_id) DO NOTHING
                """, u['user_id'], chat_id, u.get('username'), u.get('first_name'))
                count += 1
            except Exception:
                pass
        return count

    async def get_pending_request_user_ids(self, chat_id):
        rows = await self.db.fetch(
            "SELECT user_id FROM join_requests WHERE chat_id = $1 AND status = 'pending'", chat_id)
        return [r['user_id'] for r in rows] if rows else []

    async def update_channel_stats_after_batch(self, chat_id, approved_count, dm_sent_count=0, dm_failed_count=0):
        try:
            pending = await self.get_pending_count(chat_id)
            await self.update_channel_setting(chat_id, 'pending_requests', pending)
        except Exception as e:
            logger.error(f'Error updating channel stats: {e}')

    # ==================== CLONE BOT ====================
    async def save_clone_bot(self, owner_id, bot_token, bot_username, settings=None):
        return await self.db.execute("""
            INSERT INTO bot_clones (owner_id, bot_token, bot_username, created_at)
            VALUES ($1, $2, $3, NOW())
            ON CONFLICT (bot_token) DO UPDATE SET
                bot_username = $3
        """, owner_id, bot_token, bot_username)

    async def get_owner_clones(self, owner_id):
        return await self.db.fetch('SELECT * FROM bot_clones WHERE owner_id = $1', owner_id)

    async def get_clone_bot(self, bot_token):
        return await self.db.fetchrow('SELECT * FROM bot_clones WHERE bot_token = $1', bot_token)

    async def delete_clone_bot(self, bot_token):
        return await self.db.execute('DELETE FROM bot_clones WHERE bot_token = $1', bot_token)

    # ==================== BROADCAST ====================
    async def save_broadcast(self, owner_id, channel_id, message_text, sent=0, failed=0):
        return await self.db.execute("""
            INSERT INTO broadcasts (owner_id, channel_id, content, sent_count, failed_count, created_at)
            VALUES ($1, $2, $3, $4, $5, NOW())
        """, owner_id, channel_id, message_text, sent, failed)

    async def get_broadcasts(self, owner_id, limit=10):
        return await self.db.fetch("""
            SELECT * FROM broadcasts WHERE owner_id = $1
            ORDER BY created_at DESC LIMIT $2
        """, owner_id, limit)

    async def get_total_channel_count(self):
        """Get total number of channels on the platform."""
        row = await self.pool.fetchrow("SELECT COUNT(*) as count FROM channels")
        return row['count'] if row else 0

    async def get_platform_stats(self):
        """Get platform-wide statistics for superadmin panel."""
        stats = {}
        row = await self.pool.fetchrow("SELECT COUNT(*) as c FROM channel_owners")
        stats['total_owners'] = row['c'] if row else 0
        row = await self.pool.fetchrow("SELECT COUNT(*) as c FROM channels")
        stats['total_channels'] = row['c'] if row else 0
        row = await self.pool.fetchrow("SELECT COUNT(*) as c FROM clone_bots WHERE is_active = true")
        stats['active_clones'] = row['c'] if row else 0
        row = await self.pool.fetchrow("SELECT COUNT(*) as c FROM end_users")
        stats['total_users'] = row['c'] if row else 0
        row = await self.pool.fetchrow("SELECT COUNT(*) as c FROM channel_owners WHERE tier = 'premium' OR tier = 'business'")
        stats['premium_owners'] = row['c'] if row else 0
        return stats

    async def get_all_clones(self):
        """Get all clone bots."""
        rows = await self.pool.fetch("SELECT * FROM clone_bots ORDER BY created_at DESC")
        return [dict(r) for r in rows]

