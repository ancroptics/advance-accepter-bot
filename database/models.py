import json
import logging
import os
from datetime import datetime, date, timedelta

logger = logging.getLogger(__name__)

MIGRATION_SQL_PATH = os.path.join(os.path.dirname(__file__), 'migrations', '001_initial_schema.sql')


class DatabaseModels:
    """Wraps all database operations for the bot."""

    def __init__(self, db_pool):
        self.db = db_pool

    async def run_migrations(self):
        try:
            with open(MIGRATION_SQL_PATH, 'r') as f:
                sql = f.read()
            await self.db.run_migration(sql)
            # Run additional migrations
            migration_002 = os.path.join(os.path.dirname(__file__), 'migrations', '002_fixes.sql')
            if os.path.exists(migration_002):
                with open(migration_002, 'r') as f:
                    sql2 = f.read()
                await self.db.run_migration(sql2)
            logger.info('Migrations complete')
        except Exception as e:
            logger.exception(f'Migration error: {e}')
            raise

    async def create_tables(self):
        """Alias for run_migrations."""
        await self.run_migrations()

    async def upsert_owner(self, user_id, username=None, first_name=None, last_name=None):
        return await self.db.execute("""
            INSERT INTO channel_owners (user_id, username, first_name, last_name, registered_at, last_active)
            VALUES ($1, $2, $3, $4, NOW(), NOW())
            ON CONFLICT (user_id) DO UPDATE SET
                username = COALESCE($2, channel_owners.username),
                first_name = COALESCE($3, channel_owners.first_name),
                last_name = COALESCE($4, channel_owners.last_name),
                last_active = NOW()
        """, user_id, username, first_name, last_name)

    async def get_owner(self, user_id):
        return await self.db.fetchrow('SELECT * FROM channel_owners WHERE user_id = $1', user_id)

    async def get_all_owners(self, limit=20):
        return await self.db.fetch('SELECT * FROM channel_owners ORDER BY registered_at DESC LIMIT $1', limit)

    async def upsert_end_user(self, user_id, username=None, first_name=None, last_name=None,
                               language_code=None, source='organic', source_channel=None):
        return await self.db.execute("""
            INSERT INTO end_users (user_id, username, first_name, last_name, language_code, source, source_channel, first_seen_at, last_active)
            VALUES ($1, $2, $3, $4, $5, $6, $7, NOW(), NOW())
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
        return await self.db.execute(
            'UPDATE end_users SET referrer_id = $2 WHERE user_id = $1 AND referrer_id IS NULL',
            user_id, referrer_id)

    async def award_referral_coins(self, user_id, coins):
        return await self.db.execute(
            'UPDATE end_users SET coins = coins + $2, referral_count = referral_count + 1 WHERE user_id = $1',
            user_id, coins)

    async def mark_user_blocked(self, user_id):
        return await self.db.execute(
            'UPDATE end_users SET has_blocked_bot = TRUE WHERE user_id = $1', user_id)

    async def ban_end_user(self, user_id, reason=None):
        return await self.db.execute(
            'UPDATE end_users SET is_banned = TRUE WHERE user_id = $1', user_id)

    async def unban_end_user(self, user_id):
        return await self.db.execute(
            'UPDATE end_users SET is_banned = FALSE WHERE user_id = $1', user_id)

    async def search_users(self, term):
        like = f'%{term}%'
        return await self.db.fetch("""
            SELECT * FROM end_users
            WHERE username ILIKE $1 OR first_name ILIKE $1 OR CAST(user_id AS TEXT) LIKE $1
            LIMIT 20
        """, like)

    async def get_top_referrers(self, limit=10):
        return await self.db.fetch("""
            SELECT user_id, username, first_name, coins, referral_count
            FROM end_users WHERE referral_count > 0
            ORDER BY referral_count DESC LIMIT $1
        """, limit)

    async def upsert_channel(self, chat_id, owner_id, chat_title=None, chat_username=None, chat_type='channel'):
        return await self.db.execute("""
            INSERT INTO managed_channels (chat_id, owner_id, chat_title, chat_username, chat_type, added_at)
            VALUES ($1, $2, $3, $4, $5, NOW())
            ON CONFLICT (chat_id) DO UPDATE SET
                chat_title = COALESCE($3, managed_channels.chat_title),
                chat_username = COALESCE($4, managed_channels.chat_username),
                owner_id = $2, is_active = TRUE, bot_is_admin = TRUE
        """, chat_id, owner_id, chat_title, chat_username, chat_type)

    async def get_channel(self, chat_id):
        return await self.db.fetchrow('SELECT * FROM managed_channels WHERE chat_id = $1', chat_id)

    async def get_owner_channels(self, owner_id):
        return await self.db.fetch(
            'SELECT * FROM managed_channels WHERE owner_id = $1 AND is_active = TRUE ORDER BY added_at', owner_id)

    async def get_all_channels(self, limit=20):
        return await self.db.fetch('SELECT * FROM managed_channels ORDER BY added_at DESC LIMIT $1', limit)

    async def update_channel_setting(self, chat_id, key, value):
        allowed = {
            'auto_approve', 'approve_mode', 'drip_rate', 'drip_interval',
            'drip_speed', 'drip_quantity',
            'welcome_dm_enabled', 'welcome_message', 'welcome_media_type', 'welcome_media_file_id',
            'welcome_buttons_json', 'welcome_parse_mode', 'welcome_messages_i18n',
            'force_subscribe_enabled', 'force_subscribe_channels',
            'cross_promo_enabled', 'cross_promo_category', 'cross_promo_text',
            'watermark_enabled', 'member_count', 'is_active', 'bot_is_admin',
            'pending_requests',
            'force_sub_modes',
        }
        if key not in allowed:
            logger.warning(f'Attempted to update disallowed channel setting: {key}')
            return
        return await self.db.execute(
            f'UPDATE managed_channels SET {key} = $2 WHERE chat_id = $1', chat_id, value)

    async def get_active_channel_count(self):
        val = await self.db.fetchval('SELECT COUNT(*) FROM managed_channels WHERE is_active = TRUE')
        return val or 0

    async def get_total_channel_count(self):
        val = await self.db.fetchval('SELECT COUNT(*) FROM managed_channels')
        return val or 0

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
        """, user_id, chat_id, required)

    async def update_force_sub_completed(self, user_id, chat_id):
        return await self.db.execute("""
            UPDATE join_requests SET force_sub_completed = TRUE, force_sub_completed_at = NOW()
            WHERE user_id = $1 AND chat_id = $2
        """, user_id, chat_id)

    async def update_channel_stats_after_batch(self, chat_id, approved, dm_sent, dm_failed):
        return await self.db.execute("""
            UPDATE managed_channels SET
                total_approved = total_approved + $2,
                total_dms_sent = total_dms_sent + $3,
                total_dms_failed = total_dms_failed + $4
            WHERE chat_id = $1
        """, chat_id, approved, dm_sent, dm_failed)

    async def create_broadcast(self, owner_id, channel_id, content, content_type='text',
                                media_file_id=None, target_segment='all'):
        return await self.db.fetchval("""
            INSERT INTO broadcasts (owner_id, channel_id, content, content_type, media_file_id,
                target_segment, status, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, 'sending', NOW())
            RETURNING broadcast_id
        """, owner_id, channel_id, content, content_type, media_file_id, target_segment)

    async def update_broadcast_status(self, broadcast_id, status, sent=0, failed=0, blocked=0):
        return await self.db.execute("""
            UPDATE broadcasts SET status = $2, sent_count = $3, failed_count = $4, blocked_count = $5,
                completed_at = CASE WHEN $2 = 'completed' THEN NOW() ELSE completed_at END
            WHERE broadcast_id = $1
        """, broadcast_id, status, sent, failed, blocked)

    async def get_owner_users(self, owner_id):
        return await self.db.fetch("""
            SELECT DISTINCT jr.user_id FROM join_requests jr
            JOIN managed_channels mc ON mc.chat_id = jr.chat_id
            WHERE mc.owner_id = $1 AND jr.status = 'approved'
        """, owner_id)

    async def get_channel_users(self, chat_id):
        return await self.db.fetch("""
            SELECT DISTINCT user_id FROM join_requests
            WHERE chat_id = $1 AND status = 'approved'
        """, chat_id)

    async def get_owner_user_count(self, owner_id):
        val = await self.db.fetchval("""
            SELECT COUNT(DISTINCT jr.user_id) FROM join_requests jr
            JOIN managed_channels mc ON mc.chat_id = jr.chat_id
            WHERE mc.owner_id = $1 AND jr.status = 'approved'
        """, owner_id)
        return val or 0

    async def get_channel_user_count(self, chat_id):
        val = await self.db.fetchval(
            "SELECT COUNT(DISTINCT user_id) FROM join_requests WHERE chat_id = $1 AND status = 'approved'", chat_id)
        return val or 0

    async def create_clone(self, owner_id, bot_token, bot_username=None, bot_name=None):
        return await self.db.fetchval("""
            INSERT INTO bot_clones (owner_id, bot_token, bot_username, bot_first_name, is_active, created_at)
            VALUES ($1, $2, $3, $4, FALSE, NOW())
            RETURNING clone_id
        """, owner_id, bot_token, bot_username, bot_name)

    async def get_clone(self, clone_id):
        return await self.db.fetchrow('SELECT * FROM bot_clones WHERE clone_id = $1', clone_id)

    async def get_clone_by_token(self, token):
        return await self.db.fetchrow('SELECT * FROM bot_clones WHERE bot_token = $1', token)

    async def get_owner_clones(self, owner_id):
        return await self.db.fetch('SELECT * FROM bot_clones WHERE owner_id = $1', owner_id)

    async def get_all_clones(self):
        return await self.db.fetch('SELECT * FROM bot_clones ORDER BY created_at DESC')

    async def get_active_clones(self):
        return await self.db.fetch('SELECT * FROM bot_clones WHERE is_active = TRUE')

    async def update_clone_status(self, clone_id, is_active=None, error_msg=None):
        if is_active is not None:
            return await self.db.execute(
                'UPDATE bot_clones SET is_active = $2, last_error = $3 WHERE clone_id = $1',
                clone_id, is_active, error_msg)
        if error_msg is not None:
            return await self.db.execute(
                'UPDATE bot_clones SET last_error = $2, error_count = error_count + 1 WHERE clone_id = $1',
                clone_id, error_msg)

    async def delete_clone(self, clone_id):
        return await self.db.execute('DELETE FROM bot_clones WHERE clone_id = $1', clone_id)

    async def get_active_clone_count(self):
        val = await self.db.fetchval('SELECT COUNT(*) FROM bot_clones WHERE is_active = TRUE')
        return val or 0

    async def log_event(self, event_type, owner_id=None, channel_id=None, user_id=None, data=None):
        return await self.db.execute("""
            INSERT INTO analytics_events (event_type, owner_id, channel_id, user_id, data, created_at)
            VALUES ($1, $2, $3, $4, $5, NOW())
        """, event_type, owner_id, channel_id, user_id, json.dumps(data) if data else None)

    async def get_channel_analytics(self, chat_id, days=30):
        """Return a summary dict with analytics for a channel."""
        result = {}
        result['total_requests'] = await self.db.fetchval(
            "SELECT COUNT(*) FROM join_requests WHERE chat_id = $1", chat_id) or 0
        result['approved'] = await self.db.fetchval(
            "SELECT COUNT(*) FROM join_requests WHERE chat_id = $1 AND status = 'approved'", chat_id) or 0
        result['pending'] = await self.db.fetchval(
            "SELECT COUNT(*) FROM join_requests WHERE chat_id = $1 AND status = 'pending'", chat_id) or 0
        result['declined'] = await self.db.fetchval(
            "SELECT COUNT(*) FROM join_requests WHERE chat_id = $1 AND status = 'declined'", chat_id) or 0
        result['today'] = await self.db.fetchval(
            "SELECT COUNT(*) FROM join_requests WHERE chat_id = $1 AND request_time::date = CURRENT_DATE", chat_id) or 0
        result['this_week'] = await self.db.fetchval(
            "SELECT COUNT(*) FROM join_requests WHERE chat_id = $1 AND request_time >= CURRENT_DATE - INTERVAL '7 days'", chat_id) or 0
        return result

    async def get_channel_analytics_timeseries(self, chat_id, days=30):
        """Return raw timeseries data for charts."""
        since = date.today() - timedelta(days=days)
        return await self.db.fetch("""
            SELECT DATE(created_at) as day, event_type, COUNT(*) as cnt
            FROM analytics_events
            WHERE channel_id = $1 AND created_at >= $2::date
            GROUP BY day, event_type ORDER BY day
        """, chat_id, since)

    async def get_channel_export_data(self, chat_id):
        return await self.db.fetch("""
            SELECT user_id, username, first_name, status, request_time, processed_at, dm_sent
            FROM join_requests WHERE chat_id = $1 ORDER BY request_time
        """, chat_id)

    async def get_platform_stats(self):
        row = await self.db.fetchrow("""
            SELECT
                (SELECT COUNT(*) FROM channel_owners) as total_owners,
                (SELECT COUNT(*) FROM managed_channels WHERE is_active = TRUE) as total_channels,
                (SELECT COUNT(*) FROM bot_clones WHERE is_active = TRUE) as active_clones,
                (SELECT COUNT(*) FROM end_users) as total_users,
                (SELECT COUNT(*) FROM channel_owners WHERE tier != 'free') as premium_owners
        """)
        return row

    async def get_templates(self, owner_id):
        return await self.db.fetch(
            'SELECT * FROM templates WHERE owner_id = $1 ORDER BY created_at', owner_id)

    async def get_auto_post_groups(self, owner_id):
        return await self.db.fetch(
            'SELECT * FROM auto_post_groups WHERE owner_id = $1 AND is_active = TRUE', owner_id)

    async def activate_premium(self, user_id, tier, days):
        expires = datetime.utcnow() + timedelta(days=days)
        await self.db.execute(
            "UPDATE channel_owners SET tier = $2, last_active = NOW() WHERE user_id = $1",
            user_id, tier)
        return await self.db.execute("""
            INSERT INTO payments (owner_id, amount, tier, duration_days, status, created_at, completed_at)
            VALUES ($1, 0, $2, $3, 'completed', NOW(), NOW())
        """, user_id, tier, days)

    async def deactivate_premium(self, user_id):
        return await self.db.execute(
            "UPDATE channel_owners SET tier = 'free' WHERE user_id = $1", user_id)

    async def get_drip_channels(self):
        """Get all channels with drip mode enabled and pending requests."""
        return await self.db.fetch("""
            SELECT mc.*, (SELECT COUNT(*) FROM join_requests jr WHERE jr.chat_id = mc.chat_id AND jr.status = 'pending') as actual_pending
            FROM managed_channels mc
            WHERE mc.approve_mode = 'drip' AND mc.is_active = TRUE
        """)

    async def get_drip_batch(self, chat_id, limit):
        """Get a batch of pending requests for drip approval."""
        return await self.db.fetch("""
            SELECT * FROM join_requests
            WHERE chat_id = $1 AND status = 'pending'
            ORDER BY request_time ASC
            LIMIT $2
        """, chat_id, limit)


    # ===== FIX 2: Fetch all active channels for startup scan =====
    async def fetch_all_active_channels(self):
        return await self.db.fetch(
            "SELECT * FROM managed_channels WHERE is_active = TRUE"
        )

    # ===== FIX 5: Platform settings for global watermark =====
    async def get_platform_setting(self, key, default=''):
        """Get a platform-wide setting."""
        try:
            row = await self.db.fetchrow(
                "SELECT value FROM platform_settings WHERE key = $1", key
            )
            return row['value'] if row else default
        except Exception:
            return default

    async def set_platform_setting(self, key, value):
        """Set a platform-wide setting."""
        await self.db.execute("""
            INSERT INTO platform_settings (key, value, updated_at)
            VALUES ($1, $2, NOW())
            ON CONFLICT (key) DO UPDATE SET value = $2, updated_at = NOW()
        """, key, str(value))
