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