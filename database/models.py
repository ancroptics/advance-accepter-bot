import json
import logging
import os
from datetime import datetime, date, timedelta

logger = logging.getLogger(__name__)

MIGRATION_SQL_PATH = os.path.join(os.path.dirname(__file__), 'migrations', '001_initial_schema.sql')

class DatabaseModels:
    def __init__(self, pool):
        self.db = pool
        self.pool = pool  # Expose pool for direct access

    async def run_migrations(self):
        try:
            with open(MIGRATION_SQL_PATH, 'r') as f:
                sql = f.read()
            await self.db.execute(sql)
            # Add columns that may be missing from initial migration
            extra_ddl = """
            CREATE TABLE IF NOT EXISTS platform_settings (
                key TEXT PRIMARY KEY,
                value TEXT
            );
            DO $$ BEGIN
                ALTER TABLE managed_channels ADD COLUMN IF NOT EXISTS support_username TEXT;
                ALTER TABLE managed_channels ADD COLUMN IF NOT EXISTS referral_enabled BOOLEAN DEFAULT FALSE;
                ALTER TABLE managed_channels ADD COLUMN IF NOT EXISTS welcome_messages_json TEXT;
                ALTER TABLE managed_channels ADD COLUMN IF NOT EXISTS watermark_enabled BOOLEAN DEFAULT FALSE;
                ALTER TABLE managed_channels ADD COLUMN IF NOT EXISTS watermark_username TEXT;
            EXCEPTION WHEN others THEN NULL;
            END $$;
            """
            await self.db.execute(extra_ddl)
            logger.info('Database migrations completed')
        except Exception as e:
            logger.error(f'Migration error: {e}')