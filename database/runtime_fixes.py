import json
import logging
import os

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = os.path.join(os.path.dirname(__file__), 'migrations')


async def run_migrations(self):
    try:
        for filename in sorted(os.listdir(MIGRATIONS_DIR)):
            if not filename.endswith('.sql'):
                continue
            path = os.path.join(MIGRATIONS_DIR, filename)
            with open(path, 'r') as f:
                await self.db.execute(f.read())

        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS platform_settings (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TIMESTAMPTZ DEFAULT NOW()
            );
            CREATE TABLE IF NOT EXISTS force_sub_join_requests (
                user_id BIGINT NOT NULL,
                chat_id BIGINT NOT NULL,
                requested_at TIMESTAMPTZ DEFAULT NOW(),
                PRIMARY KEY (user_id, chat_id)
            );
            ALTER TABLE platform_settings ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();
            ALTER TABLE managed_channels ADD COLUMN IF NOT EXISTS support_username TEXT;
            ALTER TABLE managed_channels ADD COLUMN IF NOT EXISTS referral_enabled BOOLEAN DEFAULT FALSE;
            ALTER TABLE managed_channels ADD COLUMN IF NOT EXISTS welcome_messages_json TEXT;
            ALTER TABLE managed_channels ADD COLUMN IF NOT EXISTS watermark_enabled BOOLEAN DEFAULT FALSE;
            ALTER TABLE managed_channels ADD COLUMN IF NOT EXISTS watermark_username TEXT;
            ALTER TABLE managed_channels ADD COLUMN IF NOT EXISTS watermark_text TEXT;
            ALTER TABLE managed_channels ADD COLUMN IF NOT EXISTS watermark_location TEXT DEFAULT 'bottom';
            ALTER TABLE managed_channels ADD COLUMN IF NOT EXISTS force_sub_mode TEXT DEFAULT 'auto';
            ALTER TABLE managed_channels ADD COLUMN IF NOT EXISTS force_sub_timeout INTEGER DEFAULT 0;
            ALTER TABLE broadcasts ADD COLUMN IF NOT EXISTS caption TEXT;
            ALTER TABLE broadcasts ADD COLUMN IF NOT EXISTS buttons_json TEXT;
            ALTER TABLE bot_clones ADD COLUMN IF NOT EXISTS bot_name TEXT;
        """)
        logger.info('Database migrations completed')
    except Exception as e:
        logger.error(f'Migration error: {e}')
        raise


async def get_user_channels(self, user_id):
    return await self.get_owner_channels(user_id)


async def update_join_request_status(self, user_id, chat_id, status, processed_by='auto'):
    previous = await self.db.fetchrow(
        'SELECT status FROM join_requests WHERE user_id = $1 AND chat_id = $2',
        user_id, chat_id
    )
    result = await self.db.execute("""
        UPDATE join_requests SET status = $3, processed_at = NOW(), processed_by = $4
        WHERE user_id = $1 AND chat_id = $2
    """, user_id, chat_id, status, processed_by)
    previous_status = previous['status'] if previous else None
    if status == 'declined' and previous_status != 'declined':
        await self.db.execute("""
            UPDATE managed_channels
            SET pending_requests = GREATEST(COALESCE(pending_requests, 0) - 1, 0),
                total_declined = COALESCE(total_declined, 0) + 1
            WHERE chat_id = $1
        """, chat_id)
    elif status == 'approved' and previous_status != 'approved':
        await self.db.execute("""
            UPDATE managed_channels
            SET pending_requests = GREATEST(COALESCE(pending_requests, 0) - 1, 0),
                total_approved = COALESCE(total_approved, 0) + 1
            WHERE chat_id = $1
        """, chat_id)
    return result


async def update_join_request_after_approve(self, user_id, chat_id, dm_sent=False,
                                            dm_failed_reason=None, dm_message_id=None,
                                            processed_by='auto'):
    previous = await self.db.fetchrow(
        'SELECT status, dm_attempted FROM join_requests WHERE user_id = $1 AND chat_id = $2',
        user_id, chat_id
    )
    result = await self.db.execute("""
        UPDATE join_requests SET status = 'approved', processed_at = NOW(),
            dm_attempted = TRUE, dm_sent = $3, dm_failed_reason = $4,
            dm_message_id = $5, processed_by = $6, force_sub_completed = TRUE
        WHERE user_id = $1 AND chat_id = $2
    """, user_id, chat_id, dm_sent, dm_failed_reason, dm_message_id, processed_by)
    previous_status = previous['status'] if previous else None
    previous_dm_attempted = previous['dm_attempted'] if previous else False
    if previous_status != 'approved' or not previous_dm_attempted:
        await self.db.execute("""
            UPDATE managed_channels
            SET pending_requests = CASE WHEN $3 THEN GREATEST(COALESCE(pending_requests, 0) - 1, 0) ELSE pending_requests END,
                total_approved = COALESCE(total_approved, 0) + CASE WHEN $3 THEN 1 ELSE 0 END,
                total_dms_sent = COALESCE(total_dms_sent, 0) + CASE WHEN $2 AND NOT $4 THEN 1 ELSE 0 END,
                total_dms_failed = COALESCE(total_dms_failed, 0) + CASE WHEN NOT $2 AND NOT $4 THEN 1 ELSE 0 END
            WHERE chat_id = $1
        """, chat_id, bool(dm_sent), previous_status != 'approved', bool(previous_dm_attempted))
    return result


async def get_user(self, user_id):
    row = await self.db.fetchrow("""
        SELECT eu.*, COALESCE(co.tier, 'free') AS tier
        FROM end_users eu
        LEFT JOIN channel_owners co ON co.user_id = eu.user_id
        WHERE eu.user_id = $1
    """, user_id)
    if not row:
        owner = await self.get_owner(user_id)
        return dict(owner) if owner else None
    data = dict(row)
    data['monthly_approvals'] = await self.db.fetchval("""
        SELECT COUNT(*)
        FROM join_requests jr
        JOIN managed_channels mc ON mc.chat_id = jr.chat_id
        WHERE mc.owner_id = $1
          AND jr.status = 'approved'
          AND jr.processed_at >= date_trunc('month', NOW())
    """, user_id) or 0
    return data


async def ban_end_user(self, user_id, reason=None):
    return await self.db.execute("""
        UPDATE end_users SET is_banned = TRUE, last_active = NOW()
        WHERE user_id = $1
    """, user_id)


async def unban_end_user(self, user_id):
    return await self.db.execute("""
        UPDATE end_users SET is_banned = FALSE, last_active = NOW()
        WHERE user_id = $1
    """, user_id)


async def search_users(self, search_term):
    term = f'%{search_term}%'
    return await self.db.fetch("""
        SELECT * FROM end_users
        WHERE CAST(user_id AS TEXT) ILIKE $1
           OR username ILIKE $1
           OR first_name ILIKE $1
        ORDER BY last_active DESC NULLS LAST
        LIMIT 25
    """, term)


async def get_owner_users(self, owner_id):
    return await self.db.fetch("""
        SELECT DISTINCT jr.user_id, eu.username, eu.first_name
        FROM managed_channels mc
        JOIN join_requests jr ON jr.chat_id = mc.chat_id AND jr.status = 'approved'
        LEFT JOIN end_users eu ON eu.user_id = jr.user_id
        WHERE mc.owner_id = $1 AND COALESCE(eu.has_blocked_bot, FALSE) = FALSE
        ORDER BY eu.first_name
    """, owner_id)


async def get_owner_user_count(self, owner_id):
    val = await self.db.fetchval("""
        SELECT COUNT(DISTINCT jr.user_id)
        FROM managed_channels mc
        JOIN join_requests jr ON jr.chat_id = mc.chat_id AND jr.status = 'approved'
        LEFT JOIN end_users eu ON eu.user_id = jr.user_id
        WHERE mc.owner_id = $1 AND COALESCE(eu.has_blocked_bot, FALSE) = FALSE
    """, owner_id)
    return val or 0


async def get_channel_export_data(self, chat_id):
    return await self.db.fetch("""
        SELECT
            jr.user_id, jr.username, jr.first_name, jr.user_language,
            jr.status, jr.request_time, jr.processed_at, jr.processed_by,
            jr.dm_attempted, jr.dm_sent, jr.dm_failed_reason
        FROM join_requests jr
        WHERE jr.chat_id = $1
        ORDER BY jr.request_time DESC
    """, chat_id)


async def cleanup_stale_pending(self, chat_id, hours=48):
    return await self.db.execute("""
        UPDATE join_requests
        SET status = 'expired', processed_at = NOW(), processed_by = 'cleanup'
        WHERE chat_id = $1
          AND status = 'pending'
          AND request_time < NOW() - INTERVAL '1 hour' * $2
    """, chat_id, hours)


async def approve_request(self, chat_id, user_id):
    return await self.update_join_request_after_approve(
        user_id=user_id, chat_id=chat_id, dm_sent=False, processed_by='batch'
    )


async def decline_request(self, chat_id, user_id):
    return await self.update_join_request_status(
        user_id=user_id, chat_id=chat_id, status='declined', processed_by='batch'
    )


async def increment_approvals(self, user_id, count):
    await self.db.execute("""
        UPDATE channel_owners SET last_active = NOW()
        WHERE user_id = $1
    """, user_id)
    return count


async def create_clone(self, owner_id, bot_token, bot_username, bot_name=None):
    row = await self.db.fetchrow("""
        INSERT INTO bot_clones (owner_id, bot_token, bot_username, bot_name, is_active, created_at)
        VALUES ($1, $2, $3, $4, FALSE, NOW())
        ON CONFLICT (bot_token) DO UPDATE SET
            bot_username = $3,
            bot_name = COALESCE($4, bot_clones.bot_name)
        RETURNING clone_id
    """, owner_id, bot_token, bot_username, bot_name or bot_username)
    return row['clone_id'] if row else None


async def get_clone_by_token(self, bot_token):
    return await self.get_clone_bot(bot_token)


async def get_clone(self, clone_id):
    return await self.db.fetchrow('SELECT * FROM bot_clones WHERE clone_id = $1', clone_id)


async def get_active_clones(self):
    return await self.db.fetch("""
        SELECT * FROM bot_clones WHERE is_active = TRUE ORDER BY created_at
    """)


async def delete_clone(self, clone_id):
    return await self.db.execute('DELETE FROM bot_clones WHERE clone_id = $1')


async def create_broadcast(self, owner_id, content_type='text', content=None,
                           media_file_id=None, caption=None, buttons_json=None,
                           target_segment='all', total_targets=0, channel_id=None):
    row = await self.db.fetchrow("""
        INSERT INTO broadcasts (
            owner_id, channel_id, content, content_type, media_file_id,
            caption, buttons_json, target_segment, status, created_at
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'sending', NOW())
        RETURNING broadcast_id
    """, owner_id, channel_id, content, content_type, media_file_id,
         caption, json.dumps(buttons_json) if isinstance(buttons_json, (dict, list)) else buttons_json,
         target_segment)
    return row['broadcast_id'] if row else None


async def update_broadcast_status(self, broadcast_id, status, sent=0, failed=0, blocked=0):
    return await self.db.execute("""
        UPDATE broadcasts
        SET status = $2,
            sent_count = $3,
            failed_count = $4,
            blocked_count = $5,
            completed_at = CASE WHEN $2 IN ('completed', 'cancelled', 'failed') THEN NOW() ELSE completed_at END
        WHERE broadcast_id = $1
    """, broadcast_id, status, sent, failed, blocked)


async def update_clone_status(self, clone_id, is_active=True, error_msg=None):
    await self.db.execute("""
        UPDATE bot_clones
        SET is_active = $2,
            last_error = $3,
            error_count = CASE WHEN $3 IS NULL THEN error_count ELSE COALESCE(error_count, 0) + 1 END
        WHERE clone_id = $1
    """, clone_id, is_active, error_msg)


async def activate_premium(self, user_id, tier, days=30):
    await self.upsert_owner(user_id=user_id)
    return await self.set_owner_plan(user_id, tier)


async def deactivate_premium(self, user_id):
    return await self.set_owner_plan(user_id, 'free')


async def get_auto_post_groups(self, owner_id):
    return await self.db.fetch("""
        SELECT apg.*, apg.name AS chat_title
        FROM auto_post_groups apg
        WHERE owner_id = $1
        ORDER BY created_at DESC
    """, owner_id)


def apply_runtime_fixes(model_cls):
    methods = {
        'run_migrations': run_migrations,
        'get_user_channels': get_user_channels,
        'update_join_request_status': update_join_request_status,
        'update_join_request_after_approve': update_join_request_after_approve,
        'get_user': get_user,
        'ban_end_user': ban_end_user,
        'unban_end_user': unban_end_user,
        'search_users': search_users,
        'get_owner_users': get_owner_users,
        'get_owner_user_count': get_owner_user_count,
        'get_channel_export_data': get_channel_export_data,
        'cleanup_stale_pending': cleanup_stale_pending,
        'approve_request': approve_request,
        'decline_request': decline_request,
        'increment_approvals': increment_approvals,
        'create_clone': create_clone,
        'get_clone_by_token': get_clone_by_token,
        'get_clone': get_clone,
        'get_active_clones': get_active_clones,
        'delete_clone': delete_clone,
        'create_broadcast': create_broadcast,
        'update_broadcast_status': update_broadcast_status,
        'update_clone_status': update_clone_status,
        'activate_premium': activate_premium,
        'deactivate_premium': deactivate_premium,
        'get_auto_post_groups': get_auto_post_groups,
    }
    for name, method in methods.items():
        setattr(model_cls, name, method)
