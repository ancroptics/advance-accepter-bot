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
            logger.info('Migrations complete')
        except Exception as e:
            logger.exception(f'Migration error: {e}')
            raise

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
            INSERT INTO end_users (user_id, username, first_name, last_name,
                                   language_code, source, source_channel, first_seen, last_seen)
            VALUES ($1, $2, $3, $4, $5, $6, $7, NOW(), NOW())
            ON CONFLICT (user_id) DO UPDATE SET
                username = COALESCE($2, end_users.username),
                first_name = COALESCE($3, end_users.first_name),
                last_name = COALESCE($4, end_users.last_name),
                language_code = COALESCE($5, end_users.language_code),
                last_seen = NOW()
        """, user_id, username, first_name, last_name, language_code, source, source_channel)

    async def get_end_user(self, user_id):
        return await self.db.fetchrow('SELECT * FROM end_users WHERE user_id = $1', user_id)

    async def register_channel(self, chat_id, title, owner_id, channel_type='channel'):
        return await self.db.execute("""
            INSERT INTO channels (chat_id, title, owner_id, channel_type, added_at, is_active)
            VALUES ($1, $2, $3, $4, NOW(), TRUE)
            ON CONFLICT (chat_id) DO UPDATE SET
                title = $2,
                owner_id = $3,
                channel_type = $4,
                is_active = TRUE
        """, chat_id, title, owner_id, channel_type)

    async def get_channel(self, chat_id):
        return await self.db.fetchrow('SELECT * FROM channels WHERE chat_id = $1', chat_id)

    async def get_owner_channels(self, owner_id):
        return await self.db.fetch(
            'SELECT * FROM channels WHERE owner_id = $1 AND is_active = TRUE ORDER BY added_at DESC',
            owner_id
        )

    async def deactivate_channel(self, chat_id):
        return await self.db.execute(
            'UPDATE channels SET is_active = FALSE WHERE chat_id = $1', chat_id
        )

    async def get_channel_setting(self, chat_id, key):
        row = await self.db.fetchrow(
            'SELECT value FROM channel_settings WHERE chat_id = $1 AND key = $2',
            chat_id, key
        )
        return row['value'] if row else None

    async def update_channel_setting(self, chat_id, key, value):
        return await self.db.execute("""
            INSERT INTO channel_settings (chat_id, key, value)
            VALUES ($1, $2, $3)
            ON CONFLICT (chat_id, key) DO UPDATE SET value = $3
        """, chat_id, key, str(value))

    async def get_all_channel_settings(self, chat_id):
        rows = await self.db.fetch(
            'SELECT key, value FROM channel_settings WHERE chat_id = $1', chat_id
        )
        return {r['key']: r['value'] for r in rows} if rows else {}

    async def record_join_request(self, chat_id, user_id, username=None, first_name=None,
                                   invite_link=None, bio=None):
        return await self.db.execute("""
            INSERT INTO join_requests (chat_id, user_id, username, first_name,
                                       invite_link, bio, requested_at, status)
            VALUES ($1, $2, $3, $4, $5, $6, NOW(), 'pending')
            ON CONFLICT (chat_id, user_id) DO UPDATE SET
                username = COALESCE($3, join_requests.username),
                first_name = COALESCE($4, join_requests.first_name),
                invite_link = COALESCE($5, join_requests.invite_link),
                bio = COALESCE($6, join_requests.bio),
                requested_at = NOW(),
                status = 'pending'
        """, chat_id, user_id, username, first_name, invite_link, bio)

    async def get_pending_requests(self, chat_id, limit=50):
        return await self.db.fetch("""
            SELECT * FROM join_requests
            WHERE chat_id = $1 AND status = 'pending'
            ORDER BY requested_at ASC LIMIT $2
        """, chat_id, limit)

    async def get_pending_count(self, chat_id):
        row = await self.db.fetchrow(
            'SELECT COUNT(*) as cnt FROM join_requests WHERE chat_id = $1 AND status = \'pending\'',
            chat_id
        )
        return row['cnt'] if row else 0

    async def update_request_status(self, chat_id, user_id, status, processed_by=None):
        return await self.db.execute("""
            UPDATE join_requests SET status = $3, processed_at = NOW(), processed_by = $4
            WHERE chat_id = $1 AND user_id = $2
        """, chat_id, user_id, status, processed_by)

    async def bulk_update_request_status(self, chat_id, user_ids, status, processed_by=None):
        if not user_ids:
            return
        return await self.db.execute("""
            UPDATE join_requests SET status = $3, processed_at = NOW(), processed_by = $4
            WHERE chat_id = $1 AND user_id = ANY($2)
        """, chat_id, user_ids, status, processed_by)

    async def get_welcome_template(self, chat_id):
        row = await self.db.fetchrow(
            'SELECT * FROM welcome_templates WHERE chat_id = $1 AND is_active = TRUE',
            chat_id
        )
        return row

    async def set_welcome_template(self, chat_id, text, media_type=None, media_file_id=None,
                                    buttons_json=None):
        return await self.db.execute("""
            INSERT INTO welcome_templates (chat_id, text, media_type, media_file_id, buttons_json, is_active)
            VALUES ($1, $2, $3, $4, $5, TRUE)
            ON CONFLICT (chat_id) DO UPDATE SET
                text = $2, media_type = $3, media_file_id = $4, buttons_json = $5, is_active = TRUE
        """, chat_id, text, media_type, media_file_id, buttons_json)

    async def record_analytics_event(self, chat_id, event_type, user_id=None, metadata=None):
        meta_str = json.dumps(metadata) if metadata else None
        return await self.db.execute("""
            INSERT INTO analytics_events (chat_id, event_type, user_id, metadata, created_at)
            VALUES ($1, $2, $3, $4, NOW())
        """, chat_id, event_type, user_id, meta_str)

    async def get_analytics_summary(self, chat_id, days=7):
        return await self.db.fetch("""
            SELECT event_type, COUNT(*) as count,
                   DATE(created_at) as event_date
            FROM analytics_events
            WHERE chat_id = $1 AND created_at >= NOW() - INTERVAL '1 day' * $2
            GROUP BY event_type, DATE(created_at)
            ORDER BY event_date DESC
        """, chat_id, days)

    async def get_force_sub_channels(self, chat_id):
        return await self.db.fetch("""
            SELECT * FROM force_sub_channels
            WHERE chat_id = $1 AND is_active = TRUE
        """, chat_id)

    async def add_force_sub_channel(self, chat_id, required_chat_id, required_chat_title=None):
        return await self.db.execute("""
            INSERT INTO force_sub_channels (chat_id, required_chat_id, required_chat_title, is_active)
            VALUES ($1, $2, $3, TRUE)
            ON CONFLICT (chat_id, required_chat_id) DO UPDATE SET
                required_chat_title = $3, is_active = TRUE
        """, chat_id, required_chat_id, required_chat_title)

    async def remove_force_sub_channel(self, chat_id, required_chat_id):
        return await self.db.execute("""
            UPDATE force_sub_channels SET is_active = FALSE
            WHERE chat_id = $1 AND required_chat_id = $2
        """, chat_id, required_chat_id)

    async def get_referral_stats(self, user_id):
        row = await self.db.fetchrow("""
            SELECT COUNT(*) as referral_count
            FROM end_users WHERE source = 'referral' AND source_channel = $1::text
        """, str(user_id))
        return row['referral_count'] if row else 0

    async def get_premium_status(self, user_id):
        row = await self.db.fetchrow("""
            SELECT * FROM premium_subscriptions
            WHERE user_id = $1 AND is_active = TRUE AND expires_at > NOW()
        """, user_id)
        return row

    async def set_premium(self, user_id, plan='monthly', days=30):
        return await self.db.execute("""
            INSERT INTO premium_subscriptions (user_id, plan, is_active, started_at, expires_at)
            VALUES ($1, $2, TRUE, NOW(), NOW() + INTERVAL '1 day' * $3)
            ON CONFLICT (user_id) DO UPDATE SET
                plan = $2, is_active = TRUE, started_at = NOW(),
                expires_at = NOW() + INTERVAL '1 day' * $3
        """, user_id, plan, days)

    async def get_broadcast_history(self, owner_id, limit=10):
        return await self.db.fetch("""
            SELECT * FROM broadcast_history
            WHERE owner_id = $1
            ORDER BY created_at DESC LIMIT $2
        """, owner_id, limit)

    async def record_broadcast(self, owner_id, chat_id, message_text, total_users,
                                success_count, fail_count):
        return await self.db.execute("""
            INSERT INTO broadcast_history (owner_id, chat_id, message_text,
                                           total_users, success_count, fail_count, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, NOW())
        """, owner_id, chat_id, message_text, total_users, success_count, fail_count)

    async def get_channel_members(self, chat_id, limit=1000):
        return await self.db.fetch("""
            SELECT user_id FROM join_requests
            WHERE chat_id = $1 AND status = 'approved'
            ORDER BY processed_at DESC LIMIT $2
        """, chat_id, limit)

    async def get_bot_stats(self):
        stats = {}
        row = await self.db.fetchrow('SELECT COUNT(*) as cnt FROM channel_owners')
        stats['total_owners'] = row['cnt']
        row = await self.db.fetchrow('SELECT COUNT(*) as cnt FROM channels WHERE is_active = TRUE')
        stats['active_channels'] = row['cnt']
        row = await self.db.fetchrow('SELECT COUNT(*) as cnt FROM end_users')
        stats['total_users'] = row['cnt']
        row = await self.db.fetchrow('SELECT COUNT(*) as cnt FROM join_requests')
        stats['total_requests'] = row['cnt']
        row = await self.db.fetchrow("SELECT COUNT(*) as cnt FROM join_requests WHERE status = 'pending'")
        stats['pending_requests'] = row['cnt']
        return stats

    async def get_scheduled_posts(self, chat_id):
        return await self.db.fetch("""
            SELECT * FROM scheduled_posts
            WHERE chat_id = $1 AND status = 'scheduled' AND scheduled_at > NOW()
            ORDER BY scheduled_at ASC
        """, chat_id)

    async def create_scheduled_post(self, chat_id, owner_id, content, media_type=None,
                                     media_file_id=None, scheduled_at=None):
        return await self.db.execute("""
            INSERT INTO scheduled_posts (chat_id, owner_id, content, media_type,
                                          media_file_id, scheduled_at, status, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, 'scheduled', NOW())
        """, chat_id, owner_id, content, media_type, media_file_id, scheduled_at)

    async def get_due_scheduled_posts(self):
        return await self.db.fetch("""
            SELECT * FROM scheduled_posts
            WHERE status = 'scheduled' AND scheduled_at <= NOW()
            ORDER BY scheduled_at ASC
        """)

    async def mark_scheduled_post_sent(self, post_id):
        return await self.db.execute("""
            UPDATE scheduled_posts SET status = 'sent', sent_at = NOW()
            WHERE id = $1
        """, post_id)

    async def delete_scheduled_post(self, post_id, owner_id):
        return await self.db.execute("""
            DELETE FROM scheduled_posts WHERE id = $1 AND owner_id = $2
        """, post_id, owner_id)

    async def get_clone_config(self, owner_id):
        return await self.db.fetchrow(
            'SELECT * FROM clone_configs WHERE owner_id = $1 AND is_active = TRUE',
            owner_id
        )

    async def set_clone_config(self, owner_id, bot_token, bot_username=None):
        return await self.db.execute("""
            INSERT INTO clone_configs (owner_id, bot_token, bot_username, is_active, created_at)
            VALUES ($1, $2, $3, TRUE, NOW())
            ON CONFLICT (owner_id) DO UPDATE SET
                bot_token = $2, bot_username = $3, is_active = TRUE
        """, owner_id, bot_token, bot_username)

    async def get_cross_promo_partners(self, chat_id):
        return await self.db.fetch("""
            SELECT * FROM cross_promo_partners
            WHERE chat_id = $1 AND is_active = TRUE
        """, chat_id)

    async def add_cross_promo_partner(self, chat_id, partner_chat_id, partner_title=None):
        return await self.db.execute("""
            INSERT INTO cross_promo_partners (chat_id, partner_chat_id, partner_title, is_active, added_at)
            VALUES ($1, $2, $3, TRUE, NOW())
            ON CONFLICT (chat_id, partner_chat_id) DO UPDATE SET
                partner_title = $3, is_active = TRUE
        """, chat_id, partner_chat_id, partner_title)

    async def get_all_channels(self):
        return await self.db.fetch('SELECT * FROM channels WHERE is_active = TRUE')

    async def get_superadmin_ids(self):
        """Return list of superadmin user IDs from config or env."""
        import config
        return config.SUPERADMIN_IDS

    async def sync_pending_requests(self, chat_id, telegram_pending_user_ids):
        """Sync DB pending requests with actual Telegram pending list.
        Marks requests as 'stale' if they are pending in DB but not in Telegram's list.
        Adds new records for users pending in Telegram but missing from DB.
        Returns dict with sync stats.
        """
        if not telegram_pending_user_ids:
            stale = await self.db.fetch("""
                SELECT user_id FROM join_requests
                WHERE chat_id = $1 AND status = 'pending'
            """, chat_id)
            stale_count = len(stale) if stale else 0
            if stale_count > 0:
                await self.db.execute("""
                    UPDATE join_requests SET status = 'stale', processed_at = NOW()
                    WHERE chat_id = $1 AND status = 'pending'
                """, chat_id)
            return {'synced': 0, 'stale_removed': stale_count, 'new_added': 0}

        db_pending = await self.db.fetch("""
            SELECT user_id FROM join_requests
            WHERE chat_id = $1 AND status = 'pending'
        """, chat_id)
        db_pending_ids = set(r['user_id'] for r in db_pending) if db_pending else set()
        tg_pending_set = set(telegram_pending_user_ids)

        stale_ids = list(db_pending_ids - tg_pending_set)
        if stale_ids:
            await self.db.execute("""
                UPDATE join_requests SET status = 'stale', processed_at = NOW()
                WHERE chat_id = $1 AND user_id = ANY($2) AND status = 'pending'
            """, chat_id, stale_ids)

        new_ids = list(tg_pending_set - db_pending_ids)
        for uid in new_ids:
            await self.record_join_request(chat_id, uid)

        return {
            'synced': len(tg_pending_set & db_pending_ids),
            'stale_removed': len(stale_ids),
            'new_added': len(new_ids)
        }

    async def cleanup_stale_requests(self, days_old=7):
        """Remove stale/expired pending requests older than X days."""
        result = await self.db.execute("""
            UPDATE join_requests SET status = 'expired', processed_at = NOW()
            WHERE status = 'pending'
            AND requested_at < NOW() - INTERVAL '1 day' * $1
        """, days_old)
        return result

    async def get_request_stats(self, chat_id):
        """Get detailed request statistics for a channel."""
        rows = await self.db.fetch("""
            SELECT status, COUNT(*) as cnt
            FROM join_requests
            WHERE chat_id = $1
            GROUP BY status
        """, chat_id)
        stats = {r['status']: r['cnt'] for r in rows} if rows else {}
        stats['total'] = sum(stats.values())
        return stats

    async def get_recent_requests(self, chat_id, limit=20, status=None):
        """Get recent join requests with optional status filter."""
        if status:
            return await self.db.fetch("""
                SELECT * FROM join_requests
                WHERE chat_id = $1 AND status = $3
                ORDER BY requested_at DESC LIMIT $2
            """, chat_id, limit, status)
        return await self.db.fetch("""
            SELECT * FROM join_requests
            WHERE chat_id = $1
            ORDER BY requested_at DESC LIMIT $2
        """, chat_id, limit)

    async def get_channels_by_ids(self, chat_ids):
        """Get multiple channels by their IDs."""
        if not chat_ids:
            return []
        rows = await self.db.fetch("""
            SELECT * FROM channels WHERE chat_id = ANY($1)
        """, chat_ids)
        return [dict(r) for r in rows] if rows else []
    async def bulk_save_pending_requests(self, chat_id, users):
        """Bulk insert detected pending requests (from sync)."""
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
        """Get all pending user IDs for a channel."""
        rows = await self.db.fetch(
            "SELECT user_id FROM join_requests WHERE chat_id = $1 AND status = 'pending'", chat_id)
        return [r['user_id'] for r in rows] if rows else []
