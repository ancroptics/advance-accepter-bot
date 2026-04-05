-- Migration 002: Fixes for drip settings, force sub modes, watermark management

-- Add force_sub_modes column to managed_channels
DO $$ BEGIN
    ALTER TABLE managed_channels ADD COLUMN IF NOT EXISTS force_sub_modes TEXT DEFAULT 'instant';
EXCEPTION WHEN others THEN NULL;
END $$;

-- Create platform_settings table for global settings (watermark, etc.)
CREATE TABLE IF NOT EXISTS platform_settings (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Insert default watermark settings
INSERT INTO platform_settings (key, value) VALUES ('global_watermark_enabled', 'true')
ON CONFLICT (key) DO NOTHING;
INSERT INTO platform_settings (key, value) VALUES ('global_watermark_message', '')
ON CONFLICT (key) DO NOTHING;
