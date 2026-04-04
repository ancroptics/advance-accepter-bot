-- Telegram Growth Engine Schema
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Channel Owners
CREATE TABLE IF NOT EXISTS channel_owners (
    user_id BIGINT PRIMARY KEY,
    username VARCHAR(255),
    first_name VARCHAR(255),
    last_name VARCHAR(255),
    registered_at TIMESTAMPTZ DEFAULT NOW(),
    last_active TIMESTAMPTZ DEFAULT NOW(),
    tier VARCHAR(20) DEFAULT 'free',
    referral_code VARCHAR(50) UNIQUE,
    referred_by BIGINT,
    language VARCHAR(10) DEFAULT 'en',
    is_banned BOOLEAN DEFAULT FALSE,
    notes TEXT
);

-- End Users
CREATE TABLE IF NOT EXISTS end_users (
    user_id BIGINT PRIMARY KEY,
    username VARCHAR(255),
    first_name VARCHAR(255),
    last_name VARCHAR(255),
    language_code VARCHAR(10),
    first_seen_at TIMESTAMPTZ DEFAULT NOW(),
    last_active TIMESTAMPTZ DEFAULT NOW(),
    referrer_id BIGINT,
    referral_count INTEGER DEFAULT 0,
    coins INTEGER DEFAULT 0,
    source VARCHAR(100) DEFAULT 'organic',
    source_channel BIGINT,
    is_banned BOOLEAN DEFAULT FALSE,
    has_blocked_bot BOOLEAN DEFAULT FALSE
);

-- Managed Channels
CREATE TABLE IF NOT EXISTS managed_channels (
    chat_id BIGINT PRIMARY KEY,
    owner_id BIGINT NOT NULL REFERENCES channel_owners(user_id) ON DELETE CASCADE,
    chat_title VARCHAR(255),
    chat_username VARCHAR(255),
    chat_type VARCHAR(20) DEFAULT 'channel',
    member_count INTEGER DEFAULT 0,
    auto_approve BOOLEAN DEFAULT TRUE,
    approve_mode VARCHAR(20) DEFAULT 'instant',
    drip_rate INTEGER DEFAULT 50,
    drip_interval INTEGER DEFAULT 30,
    welcome_dm_enabled BOOLEAN DEFAULT TRUE,
    welcome_message TEXT DEFAULT 'Welcome to {channel_name}! \ud83c\udf89',
    welcome_media_type VARCHAR(20),
    welcome_media_file_id TEXT,
    welcome_buttons_json JSONB,
    welcome_parse_mode VARCHAR(10) DEFAULT 'HTML',
    welcome_messages_i18n JSONB DEFAULT '{}',
    force_subscribe_enabled BOOLEAN DEFAULT FALSE,
    force_subscribe_channels JSONB DEFAULT '[]',
    cross_promo_enabled BOOLEAN DEFAULT FALSE,
    cross_promo_category VARCHAR(50),
    cross_promo_text TEXT,
    watermark_enabled BOOLEAN DEFAULT TRUE,
    total_requests_received INTEGER DEFAULT 0,
    total_approved INTEGER DEFAULT 0,
    total_declined INTEGER DEFAULT 0,
    total_dms_sent INTEGER DEFAULT 0,
    total_dms_failed INTEGER DEFAULT 0,
    pending_requests INTEGER DEFAULT 0,
    is_active BOOLEAN DEFAULT TRUE,
    bot_is_admin BOOLEAN DEFAULT TRUE,
    added_at TIMESTAMPTZ DEFAULT NOW(),
    last_request_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_mc_owner ON managed_channels(owner_id);
CREATE INDEX IF NOT EXISTS idx_mc_active ON managed_channels(is_active);

-- Join Requests
CREATE TABLE IF NOT EXISTS join_requests (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    chat_id BIGINT NOT NULL REFERENCES managed_channels(chat_id) ON DELETE CASCADE,
    username VARCHAR(255),
    first_name VARCHAR(255),
    user_language VARCHAR(10),
    request_time TIMESTAMPTZ DEFAULT NOW(),
    status VARCHAR(20) DEFAULT 'pending',
    processed_at TIMESTAMPTZ,
    processed_by VARCHAR(20) DEFAULT 'auto',
    dm_attempted BOOLEAN DEFAULT FALSE,
    dm_sent BOOLEAN DEFAULT FALSE,
    dm_failed_reason TEXT,
    force_sub_required BOOLEAN DEFAULT FALSE,
    force_sub_completed BOOLEAN DEFAULT FALSE,
    force_sub_completed_at TIMESTAMPTZ,
    UNIQUE(user_id, chat_id)
);
CREATE INDEX IF NOT EXISTS idx_jr_status ON join_requests(status);
CREATE INDEX IF NOT EXISTS idx_jr_chat ON join_requests(chat_id);

-- Broadcasts
CREATE TABLE IF NOT EXISTS broadcasts (
    broadcast_id BIGSERIAL PRIMARY KEY,
    owner_id BIGINT REFERENCES channel_owners(user_id),
    channel_id BIGINT,
    content TEXT,
    content_type VARCHAR(20) DEFAULT 'text',
    media_file_id TEXT,
    target_segment VARCHAR(100) DEFAULT 'all',
    sent_count INTEGER DEFAULT 0,
    failed_count INTEGER DEFAULT 0,
    blocked_count INTEGER DEFAULT 0,
    status VARCHAR(20) DEFAULT 'pending',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

-- Bot Clones
CREATE TABLE IF NOT EXISTS bot_clones (
    clone_id BIGSERIAL PRIMARY KEY,
    owner_id BIGINT NOT NULL REFERENCES channel_owners(user_id) ON DELETE CASCADE,
    bot_token TEXT NOT NULL UNIQUE,
    bot_username VARCHAR(255),
    bot_first_name VARCHAR(255),
    is_active BOOLEAN DEFAULT FALSE,
    error_count INTEGER DEFAULT 0,
    last_error TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_clones_owner ON bot_clones(owner_id);

-- Analytics Events
CREATE TABLE IF NOT EXISTS analytics_events (
    id BIGSERIAL PRIMARY KEY,
    event_type VARCHAR(50) NOT NULL,
    owner_id BIGINT,
    channel_id BIGINT,
    user_id BIGINT,
    data JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_ae_type ON analytics_events(event_type);
CREATE INDEX IF NOT EXISTS idx_ae_time ON analytics_events(created_at);

-- Templates
CREATE TABLE IF NOT EXISTS templates (
    template_id BIGSERIAL PRIMARY KEY,
    owner_id BIGINT NOT NULL REFERENCES channel_owners(user_id),
    name VARCHAR(100) NOT NULL,
    content_type VARCHAR(20) DEFAULT 'text',
    content TEXT,
    media_file_id TEXT,
    buttons_json JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(owner_id, name)
);

-- Auto Post Groups
CREATE TABLE IF NOT EXISTS auto_post_groups (
    id BIGSERIAL PRIMARY KEY,
    owner_id BIGINT NOT NULL REFERENCES channel_owners(user_id),
    chat_id BIGINT NOT NULL,
    chat_title VARCHAR(255),
    is_active BOOLEAN DEFAULT TRUE,
    added_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(owner_id, chat_id)
);

-- Payments
CREATE TABLE IF NOT EXISTS payments (
    payment_id BIGSERIAL PRIMARY KEY,
    owner_id BIGINT NOT NULL REFERENCES channel_owners(user_id),
    amount INTEGER DEFAULT 0,
    tier VARCHAR(20),
    duration_days INTEGER,
    status VARCHAR(20) DEFAULT 'pending',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);
