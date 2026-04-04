import json
import logging
from datetime import datetime, date, timedelta
from database.connection import execute, fetch, fetchrow, fetchval

logger = logging.getLogger(__name__)

# ============= CHANNEL OWNERS =============

async def upsert_channel_owner(user_id, username=None, first_name=None, last_name=None):
    return await execute("""
        INSERT INTO channel_owners (user_id, username, first_name, last_name, registered_at, last_active)
        VALUES ($1, $2, $3, $4, NOW(), NOW())
        ON CONFLICT (user_id) DO UPDATE SET
            username = COALESCE($2, channel_owners.username),
            first_name = COALESCE($3, channel_owners.first_name),
            last_name = COALESCE($4, channel_owners.last_name),
            last_active = NOW()
    """, user_id, username, first_name, last_name)

async def get_user(db, user_id):
    return await db.fetchrow('SELECT * FROM channel_owners WHERE user_id = $1', user_id)

async def is_channel_owner(db, user_id, channel_id):
    row = await db.fetchrow(
        'SELECT 1 FROM channels WHERE owner_id = $1 AND channel_id = $2', user_id, channel_id
    )
    return row is not None

# ============= CHANNELS =============

async def add_channel(db, owner_id, channel_id, channel_name, channel_type='channel'):
    return await db.fetchrow("""
        INSERT INTO channels (owner_id, channel_id, channel_name, channel_type, created_at)
        VALUES ($1, $2, $3, $4, NOW())
        ON CONFLICT (channel_id) DO UPDATE SET
            channel_name = $3, owner_id = $1
        RETURNING *
    """, owner_id, channel_id, channel_name, channel_type)

async def get_channels(db, owner_id):
    return await db.fetch('SELECT * FROM channels WHERE owner_id = $1 ORDER BY created_at', owner_id)

async def get_channel(db, channel_id):
    return await db.fetchrow('SELECT * FROM channels WHERE channel_id = $1', channel_id)

async def remove_channel(db, channel_id):
    return await db.execute('DELETE FROM channels WHERE channel_id = $1', channel_id)

async def update_channel_setting(db, channel_id, key, value):
    return await db.execute(f'UPDATE channels SET {key} = $2 WHERE channel_id = $1', channel_id, value)

async def get_all_active_channels(db):
    return await db.fetch('SELECT * FROM channels WHERE auto_accept = true')

# ============= CHANNEL SETTINGS =============

async def get_channel_settings(db, channel_id):
    return await db.fetchrow('SELECT * FROM channel_settings WHERE channel_id = $1', channel_id)

async def upsert_channel_settings(db, channel_id, settings_dict):
    existing = await get_channel_settings(db, channel_id)
    if existing:
        sets = ', '.join(f'{k} = ${i+2}' for i, k in enumerate(settings_dict.keys()))
        query = f'UPDATE channel_settings SET {sets} WHERE channel_id = $1'
        await db.execute(query, channel_id, *settings_dict.values())
    else:
        cols = ', '.join(['channel_id'] + list(settings_dict.keys()))
        placeholders = ', '.join(f'${i+1}' for i in range(len(settings_dict) + 1))
        query = f'INSERT INTO channel_settings ({cols}) VALUES ({placeholders})'
        await db.execute(query, channel_id, *settings_dict.values())

# ============= JOIN REQUESTS =============

async def log_join_request(db, channel_id, user_id, username=None, first_name=None, status='pending'):
    return await db.execute("""
        INSERT INTO join_requests (channel_id, user_id, username, first_name, status, requested_at)
        VALUES ($1, $2, $3, $4, $5, NOW())
        ON CONFLICT (channel_id, user_id) DO UPDATE SET
            status = $5, username = COALESCE($3, join_requests.username),
            first_name = COALESCE($4, join_requests.first_name),
            requested_at = NOW()
    """, channel_id, user_id, username, first_name, status)

async def update_join_request_status(db, channel_id, user_id, status):
    return await db.execute("""
        UPDATE join_requests SET status = $3, processed_at = NOW()
        WHERE channel_id = $1 AND user_id = $2
    """, channel_id, user_id, status)

async def get_pending_requests(db, channel_id):
    return await db.fetch("""
        SELECT * FROM join_requests WHERE channel_id = $1 AND status = 'pending'
        ORDER BY requested_at
    """, channel_id)

async def get_join_request_count(db, channel_id, status=None):
    if status:
        row = await db.fetchrow(
            'SELECT COUNT(*) as cnt FROM join_requests WHERE channel_id = $1 AND status = $2',
            channel_id, status
        )
    else:
        row = await db.fetchrow(
            'SELECT COUNT(*) as cnt FROM join_requests WHERE channel_id = $1', channel_id
        )
    return row['cnt'] if row else 0

# ============= WELCOME MESSAGES =============

async def set_welcome_message(db, channel_id, message_text, media_type=None, media_file_id=None):
    return await db.execute("""
        INSERT INTO welcome_messages (channel_id, message_text, media_type, media_file_id)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (channel_id) DO UPDATE SET
            message_text = $2, media_type = $3, media_file_id = $4
    """, channel_id, message_text, media_type, media_file_id)

async def get_welcome_message(db, channel_id):
    return await db.fetchrow('SELECT * FROM welcome_messages WHERE channel_id = $1', channel_id)

# ============= CAPTCHA =============

async def create_captcha_session(db, user_id, channel_id, answer, expires_at):
    return await db.execute("""
        INSERT INTO captcha_sessions (user_id, channel_id, correct_answer, expires_at, created_at)
        VALUES ($1, $2, $3, $4, NOW())
        ON CONFLICT (user_id, channel_id) DO UPDATE SET
            correct_answer = $3, expires_at = $4, attempts = 0, created_at = NOW()
    """, user_id, channel_id, str(answer), expires_at)

async def get_captcha_session(db, user_id, channel_id):
    return await db.fetchrow("""
        SELECT * FROM captcha_sessions
        WHERE user_id = $1 AND channel_id = $2 AND expires_at > NOW()
    """, user_id, channel_id)

async def increment_captcha_attempts(db, user_id, channel_id):
    return await db.execute("""
        UPDATE captcha_sessions SET attempts = attempts + 1
        WHERE user_id = $1 AND channel_id = $2
    """, user_id, channel_id)

# ============= ANALYTICS / STATS =============

async def record_daily_stat(db, channel_id, stat_type, count=1):
    today = date.today().isoformat()
    return await db.execute("""
        INSERT INTO daily_stats (channel_id, stat_date, stat_type, count)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (channel_id, stat_date, stat_type) DO UPDATE SET
            count = daily_stats.count + $4
    """, channel_id, today, stat_type, count)

async def get_daily_stats(db, owner_id, channel_id=None, days=7):
    since = (date.today() - timedelta(days=days)).isoformat()
    if channel_id:
        return await db.fetch("""
            SELECT * FROM daily_stats
            WHERE channel_id = $1 AND stat_date >= $2
            ORDER BY stat_date
        """, channel_id, since)
    else:
        return await db.fetch("""
            SELECT ds.* FROM daily_stats ds
            JOIN channels c ON c.channel_id = ds.channel_id
            WHERE c.owner_id = $1 AND ds.stat_date >= $2
            ORDER BY ds.stat_date
        """, owner_id, since)

async def get_channel_analytics(db, channel_id, days=30):
    since = (date.today() - timedelta(days=days)).isoformat()
    return await db.fetch("""
        SELECT stat_date as date,
            SUM(CASE WHEN stat_type = 'join' THEN count ELSE 0 END) as joins,
            SUM(CASE WHEN stat_type = 'leave' THEN count ELSE 0 END) as leaves,
            SUM(CASE WHEN stat_type = 'request' THEN count ELSE 0 END) as requests
        FROM daily_stats
        WHERE channel_id = $1 AND stat_date >= $2
        GROUP BY stat_date ORDER BY stat_date
    """, channel_id, since)

# ============= REFERRALS =============

async def create_referral(db, user_id, channel_id):
    import random, string
    code = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
    return await db.fetchrow("""
        INSERT INTO referrals (referrer_id, channel_id, code, created_at)
        VALUES ($1, $2, $3, NOW())
        RETURNING *
    """, user_id, channel_id, code)

async def get_referral_by_code(db, code):
    return await db.fetchrow('SELECT * FROM referrals WHERE code = $1', code)

async def process_referral_reward(db, referrer_id, referred_id, channel_id):
    return await db.execute("""
        INSERT INTO referral_rewards (referrer_id, referred_id, channel_id, rewarded_at)
        VALUES ($1, $2, $3, NOW())
        ON CONFLICT DO NOTHING
    """, referrer_id, referred_id, channel_id)

async def get_referral_stats(db, user_id):
    return await db.fetchrow("""
        SELECT COUNT(*) as total,
            COUNT(CASE WHEN rr.id IS NOT NULL THEN 1 END) as successful
        FROM referrals r
        LEFT JOIN referral_rewards rr ON rr.referrer_id = r.referrer_id
        WHERE r.referrer_id = $1
    """, user_id)

# ============= CROSS PROMO =============

async def get_cross_promo_channel(db, owner_id):
    return await db.fetch("""
        SELECT c.* FROM channels c
        WHERE c.owner_id != $1 AND c.cross_promo_enabled = true
        ORDER BY RANDOM() LIMIT 5
    """, owner_id)

# ============= SCHEDULED POSTS =============

async def create_scheduled_post(db, channel_id, text, scheduled_at, media_type=None, media_file_id=None):
    return await db.fetchrow("""
        INSERT INTO scheduled_posts (channel_id, text, scheduled_at, media_type, media_file_id, status, created_at)
        VALUES ($1, $2, $3, $4, $5, 'pending', NOW())
        RETURNING *
    """, channel_id, text, scheduled_at, media_type, media_file_id)

async def get_pending_scheduled_posts(db):
    return await db.fetch("""
        SELECT * FROM scheduled_posts WHERE status = 'pending' AND scheduled_at <= NOW()
        ORDER BY scheduled_at
    """)

async def mark_scheduled_post_done(db, post_id):
    return await db.execute(
        "UPDATE scheduled_posts SET status = 'sent', sent_at = NOW() WHERE id = $1", post_id
    )

async def get_recurring_posts(db):
    return await db.fetch("SELECT * FROM scheduled_posts WHERE status = 'recurring'")

# ============= BROADCASTS =============

async def create_broadcast(db, channel_id, text, media_type=None, media_file_id=None):
    return await db.fetchrow("""
        INSERT INTO broadcasts (channel_id, text, media_type, media_file_id, status, created_at)
        VALUES ($1, $2, $3, $4, 'pending', NOW())
        RETURNING *
    """, channel_id, text, media_type, media_file_id)

async def get_broadcast_recipients(db, channel_id):
    rows = await db.fetch("""
        SELECT DISTINCT user_id FROM join_requests
        WHERE channel_id = $1 AND status = 'approved'
    """, channel_id)
    return [r['user_id'] for r in rows]

async def update_broadcast_status(db, broadcast_id, sent=0, failed=0, total=0, completed=False):
    status = 'completed' if completed else 'sending'
    return await db.execute("""
        UPDATE broadcasts SET status = $2, sent_count = $3, failed_count = $4, total_count = $5
        WHERE id = $1
    """, broadcast_id, status, sent, failed, total)

# ============= BOT CLONES =============

async def create_bot_clone(db, owner_id, bot_token, label=''):
    return await db.fetchrow("""
        INSERT INTO bot_clones (owner_id, bot_token, label, status, created_at)
        VALUES ($1, $2, $3, 'pending', NOW())
        RETURNING *
    """, owner_id, bot_token, label)

async def get_bot_clones(db, active=False):
    if active:
        return await db.fetch("SELECT * FROM bot_clones WHERE status = 'running'")
    return await db.fetch('SELECT * FROM bot_clones ORDER BY created_at')

async def update_clone_status(db, clone_id, status, error_msg=None):
    return await db.execute("""
        UPDATE bot_clones SET status = $2, last_error = $3 WHERE id = $1
    """, clone_id, status, error_msg)

# ============= PREMIUM / SUBSCRIPTIONS =============

async def get_subscription(db, user_id):
    return await db.fetchrow("""
        SELECT * FROM subscriptions WHERE user_id = $1 AND status = 'active' AND expires_at > NOW()
    """, user_id)

async def create_subscription(db, user_id, tier, expires_at, payment_id=None):
    return await db.fetchrow("""
        INSERT INTO subscriptions (user_id, tier, status, expires_at, payment_id, created_at)
        VALUES ($1, $2, 'active', $3, $4, NOW())
        RETURNING *
    """, user_id, tier, expires_at, payment_id)

async def get_user_tier(db, user_id):
    sub = await get_subscription(db, user_id)
    return sub['tier'] if sub else 'free'
