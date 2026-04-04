CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

CREATE TABLE IF NOT EXISTS channel_owners (
    user_id BIGINT PRIMARY KEY,
    username VARCHAR(255),
    first_name VARCHAR(255),
    last_name VARCHAR(255),
    role VARCHAR(50) DEFAULT 'owner',
    tier VARCHAR(50) DEFAULT 'free',
    language VARCHAR(10) DEFAULT 'en',
    registered_at TIMESTAMP DEFAULT NOW(),
    last_active TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS channels (
    id SERIAL PRIMARY KEY,
    owner_id BIGINT REFERENCES channel_owners(user_id) ON DELETE CASCADE,
    channel_id BIGINT UNIQUE NOT NULL,
    channel_name VARCHAR(255),
    channel_type VARCHAR(50) DEFAULT 'channel',
    auto_accept BOOLEAN DEFAULT true,
    accept_delay INTEGER DEFAULT 0,
    captcha_enabled BOOLEAN DEFAULT false,
    cross_promo_enabled BOOLEAN DEFAULT false,
    watermark_enabled BOOLEAN DEFAULT false,
    promo_text TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_channels_owner ON channels(owner_id);
CREATE INDEX idx_channels_channel_id ON channels(channel_id);

CREATE TABLE IF NOT EXISTS channel_settings (
    channel_id BIGINT PRIMARY KEY REFERENCES channels(channel_id) ON DELETE CASCADE,
    welcome_enabled BOOLEAN DEFAULT true,
    welcome_delay INTEGER DEFAULT 0,
    goodbye_enabled BOOLEAN DEFAULT false,
    goodbye_message TEXT,
    auto_delete_join_msg BOOLEAN DEFAULT false,
    auto_delete_delay INTEGER DEFAULT 300,
    min_account_age_days INTEGER DEFAULT 0,
    block_bots BOOLEAN DEFAULT false,
    require_profile_photo BOOLEAN DEFAULT false,
    max_pending_requests INTEGER DEFAULT 1000,
    notification_chat_id BIGINT,
    custom_rules TEXT
);

CREATE TABLE IF NOT EXISTS join_requests (
    id SERIAL PRIMARY KEY,
    channel_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    username VARCHAR(255),
    first_name VARCHAR(255),
    status VARCHAR(50) DEFAULT 'pending',
    requested_at TIMESTAMP DEFAULT NOW(),
    processed_at TIMESTAMP,
    UNIQUE(channel_id, user_id)
);

CREATE INDEX idx_join_requests_channel ON join_requests(channel_id);
CREATE INDEX idx_join_requests_status ON join_requests(status);
CREATE INDEX idx_join_requests_channel_status ON join_requests(channel_id, status);

CREATE TABLE IF NOT EXISTS welcome_messages (
    channel_id BIGINT PRIMARY KEY,
    message_text TEXT NOT NULL,
    media_type VARCHAR(50),
    media_file_id TEXT,
    buttons_json JSONB,
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS captcha_sessions (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    channel_id BIGINT NOT NULL,
    correct_answer VARCHAR(50) NOT NULL,
    attempts INTEGER DEFAULT 0,
    max_attempts INTEGER DEFAULT 3,
    expires_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(user_id, channel_id)
);

CREATE INDEX idx_captcha_expires ON captcha_sessions(expires_at);

CREATE TABLE IF NOT EXISTS daily_stats (
    id SERIAL PRIMARY KEY,
    channel_id BIGINT NOT NULL,
    stat_date DATE NOT NULL DEFAULT CURRENT_DATE,
    stat_type VARCHAR(50) NOT NULL,
    count INTEGER DEFAULT 0,
    UNIQUE(channel_id, stat_date, stat_type)
);

CREATE INDEX idx_daily_stats_channel_date ON daily_stats(channel_id, stat_date);

CREATE TABLE IF NOT EXISTS referrals (
    id SERIAL PRIMARY KEY,
    referrer_id BIGINT NOT NULL,
    channel_id BIGINT,
    code VARCHAR(50) UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_referrals_code ON referrals(code);
CREATE INDEX idx_referrals_referrer ON referrals(referrer_id);

CREATE TABLE IF NOT EXISTS referral_rewards (
    id SERIAL PRIMARY KEY,
    referrer_id BIGINT NOT NULL,
    referred_id BIGINT NOT NULL,
    channel_id BIGINT,
    rewarded_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(referrer_id, referred_id, channel_id)
);

CREATE TABLE IF NOT EXISTS scheduled_posts (
    id SERIAL PRIMARY KEY,
    channel_id BIGINT NOT NULL,
    text TEXT,
    media_type VARCHAR(50),
    media_file_id TEXT,
    scheduled_at TIMESTAMP,
    cron_expression VARCHAR(100),
    status VARCHAR(50) DEFAULT 'pending',
    sent_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_scheduled_posts_status ON scheduled_posts(status);
CREATE INDEX idx_scheduled_posts_scheduled ON scheduled_posts(scheduled_at);

CREATE TABLE IF NOT EXISTS broadcasts (
    id SERIAL PRIMARY KEY,
    channel_id BIGINT NOT NULL,
    text TEXT,
    media_type VARCHAR(50),
    media_file_id TEXT,
    status VARCHAR(50) DEFAULT 'pending',
    sent_count INTEGER DEFAULT 0,
    failed_count INTEGER DEFAULT 0,
    total_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),
    completed_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS bot_clones (
    id SERIAL PRIMARY KEY,
    owner_id BIGINT REFERENCES channel_owners(user_id) ON DELETE CASCADE,
    bot_token TEXT NOT NULL,
    label VARCHAR(255),
    status VARCHAR(50) DEFAULT 'pending',
    last_error TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_bot_clones_owner ON bot_clones(owner_id);
CREATE INDEX idx_bot_clones_status ON bot_clones(status);

CREATE TABLE IF NOT EXISTS subscriptions (
    id SERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES channel_owners(user_id) ON DELETE CASCADE,
    tier VARCHAR(50) NOT NULL DEFAULT 'free',
    status VARCHAR(50) DEFAULT 'active',
    payment_id VARCHAR(255),
    expires_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_subscriptions_user ON subscriptions(user_id);
CREATE INDEX idx_subscriptions_status ON subscriptions(status, expires_at);

CREATE TABLE IF NOT EXISTS audit_log (
    id SERIAL PRIMARY KEY,
    user_id BIGINT,
    action VARCHAR(255) NOT NULL,
    details JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_audit_log_user ON audit_log(user_id);
CREATE INDEX idx_audit_log_action ON audit_log(action);
