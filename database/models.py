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
