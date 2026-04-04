-- Migration 001: Initial Schema for Advance Accepter Bot
-- Run this against your Neon PostgreSQL database

-- Channel Owners (bot admins)
CREATE TABLE IF NOT EXISTS channel_owners (
    user_id BIGINT PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    last_name TEXT,
    tier TEXT DEFAULT 'free',
    registered_at TIMESTAMPTZ DEFAULT NOW(),
    last_active TIMESTAMPTZ DEFAULT NOW()
);

-- Managed Channels
CREATE TABLE IF NOT EXISTS managed_channels (
    chat_id BIGINT PRIMARY KEY,
    owner_id BIGINT REFERENCES channel_owners(user_id),
    chat_title TEXT,
    chat_username TEXT,
    chat_type TEXT DEFAULT 'channel',
    is_active BOOLEAN DEFAULT TRUE,
    bot_is_admin BOOLEAN DEFAULT FALSE,
    auto_approve BOOLEAN DEFAULT TRUE,
    approve_mode TEXT DEFAULT 'instant',
    drip_rate INTEGER DEFAULT 5,
    drip_interval INTEGER DEFAULT 60,
    drip_speed TEXT DEFAULT 'medium',
    drip_quantity INTEGER DEFAULT 50,
    welcome_dm_enabled BOOLEAN DEFAULT FALSE,
    welcome_message TEXT,
    welcome_media_type TEXT,
    welcome_media_file_id TEXT,
    welcome_buttons_json TEXT,
    welcome_parse_mode TEXT DEFAULT 'HTML',
    welcome_messages_i18n JSONB DEFAULT '{}',
    force_subscribe_enabled BOOLEAN DEFAULT FALSE,
    force_subscribe_channels TEXT,
    cross_promo_enabled BOOLEAN DEFAULT FALSE,
    cross_promo_category TEXT,
    cross_promo_text TEXT,
    watermark_enabled BOOLEAN DEFAULT FALSE,
    member_count INTEGER DEFAULT 0,
    pending_requests INTEGER DEFAULT 0,
    total_approved INTEGER DEFAULT 0,
    total_declined INTEGER DEFAULT 0,
    total_dms_sent INTEGER DEFAULT 0,
    total_dms_failed INTEGER DEFAULT 0,
    added_at TIMESTAMPTZ DEFAULT NOW()
);

-- Add new columns if they don't exist (for existing databases)
DO $$ BEGIN
    ALTER TABLE managed_channels ADD COLUMN IF NOT EXISTS drip_speed TEXT DEFAULT 'medium';
    ALTER TABLE managed_channels ADD COLUMN IF NOT EXISTS drip_quantity INTEGER DEFAULT 50;
EXCEPTION WHEN others THEN NULL;
END $$;

-- End Users (people who join channels)
CREATE TABLE IF NOT EXISTS end_users (
    user_id BIGINT PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    last_name TEXT,
    language_code TEXT,
    source TEXT DEFAULT 'organic',
    source_channel BIGINT,
    referrer_id BIGINT,
    coins INTEGER DEFAULT 0,
    referral_count INTEGER DEFAULT 0,
    has_blocked_bot BOOLEAN DEFAULT FALSE,
    is_banned BOOLEAN DEFAULT FALSE,
    first_seen_at TIMESTAMPTZ DEFAULT NOW(),
    last_active TIMESTAMPTZ DEFAULT NOW()
);

-- Join Requests
CREATE TABLE IF NOT EXISTS join_requests (
    request_id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    chat_id BIGINT NOT NULL,
    username TEXT,
    first_name TEXT,
    user_language TEXT,
    status TEXT DEFAULT 'pending',
    request_time TIMESTAMPTZ DEFAULT NOW(),
    processed_at TIMESTAMPTZ,
    processed_by TEXT DEFAULT 'auto',
    dm_attempted BOOLEAN DEFAULT FALSE,
    dm_sent BOOLEAN DEFAULT FALSE,
    dm_failed_reason TEXT,
    dm_message_id BIGINT,
    force_sub_required TEXT,
    force_sub_completed BOOLEAN DEFAULT FALSE,
    force_sub_completed_at TIMESTAMPTZ,
    UNIQUE(user_id, chat_id)
);

-- Broadcasts
CREATE TABLE IF NOT EXISTS broadcasts (
    broadcast_id BIGSERIAL PRIMARY KEY,
    owner_id BIGINT REFERENCES channel_owners(user_id),
    channel_id BIGINT,
    content TEXT,
    content_type TEXT DEFAULT 'text',
    media_file_id TEXT,
    target_segment TEXT DEFAULT 'all',
    status TEXT DEFAULT 'pending',
    sent_count INTEGER DEFAULT 0,
    failed_count INTEGER DEFAULT 0,
    blocked_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

-- Bot Clones
CREATE TABLE IF NOT EXISTS bot_clones (
    clone_id BIGSERIAL PRIMARY KEY,
    owner_id BIGINT REFERENCES channel_owners(user_id),
    bot_token TEXT UNIQUE NOT NULL,
    bot_username TEXT,
    bot_first_name TEXT,
    is_active BOOLEAN DEFAULT FALSE,
    last_error TEXT,
    error_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Analytics Events
CREATE TABLE IF NOT EXISTS analytics_events (
    event_id BIGSERIAL PRIMARY KEY,
    event_type TEXT NOT NULL,
    owner_id BIGINT,
    channel_id BIGINT,
    user_id BIGINT,
    data TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Templates
CREATE TABLE IF NOT EXISTS templates (
    template_id BIGSERIAL PRIMARY KEY,
    owner_id BIGINT REFERENCES channel_owners(user_id),
    name TEXT NOT NULL,
    content TEXT,
    content_type TEXT DEFAULT 'text',
    media_file_id TEXT,
    buttons_json TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Auto Post Groups
CREATE TABLE IF NOT EXISTS auto_post_groups (
    group_id BIGSERIAL PRIMARY KEY,
    owner_id BIGINT REFERENCES channel_owners(user_id),
    name TEXT,
    channel_ids TEXT,
    template_id BIGINT,
    schedule_cron TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Payments
CREATE TABLE IF NOT EXISTS payments (
    payment_id BIGSERIAL PRIMARY KEY,
    owner_id BIGINT REFERENCES channel_owners(user_id),
    amount DECIMAL(10,2),
    currency TEXT DEFAULT 'USD',
    tier TEXT,
    duration_days INTEGER,
    status TEXT DEFAULT 'pending',
    provider TEXT,
    provider_payment_id TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_join_requests_chat_status ON join_requests(chat_id, status);
CREATE INDEX IF NOT EXISTS idx_join_requests_user ON join_requests(user_id);
CREATE INDEX IF NOT EXISTS idx_analytics_channel ON analytics_events(channel_id, created_at);
CREATE INDEX IF NOT EXISTS idx_managed_channels_owner ON managed_channels(owner_id);
CREATE INDEX IF NOT EXISTS idx_end_users_referrer ON end_users(referrer_id);
