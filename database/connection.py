import logging
import asyncio
import ssl
from urllib.parse import urlparse, unquote
import asyncpg
import config

logger = logging.getLogger(__name__)


def _get_ssl_context():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _parse_dsn(dsn):
    parsed = urlparse(dsn)
    return {
        'user': unquote(parsed.username or ''),
        'password': unquote(parsed.password or ''),
        'host': parsed.hostname or 'localhost',
        'port': parsed.port or 5432,
        'database': (parsed.path or '/postgres').lstrip('/') or 'postgres',
    }


class DatabasePool:
    def __init__(self):
        self.pool = None
        self._connecting = False

    @classmethod
    async def create(cls, dsn):
        instance = cls()
        params = _parse_dsn(dsn)
        logger.info(f"Connecting to DB: host={params['host']}, port={params['port']}, user={params['user']}, db={params['database']}")
        instance.pool = await asyncpg.create_pool(
            user=params['user'],
            password=params['password'],
            host=params['host'],
            port=params['port'],
            database=params['database'],
            min_size=2,
            max_size=10,
            command_timeout=60,
            statement_cache_size=0,
            ssl=_get_ssl_context(),
        )
        logger.info('Database pool created')
        return instance

    async def connect(self):
        if self._connecting:
            return
        self._connecting = True
        try:
            dsn = config.DATABASE_URL
            params = _parse_dsn(dsn)
            self.pool = await asyncpg.create_pool(
                user=params['user'],
                password=params['password'],
                host=params['host'],
                port=params['port'],
                database=params['database'],
                min_size=2,
                max_size=10,
                command_timeout=60,
                statement_cache_size=0,
                ssl=_get_ssl_context(),
            )
            logger.info('Database pool created')
        except Exception as e:
            logger.exception(f'Failed to create database pool: {e}')
            raise
        finally:
            self._connecting = False

    async def close(self):
        if self.pool:
            await self.pool.close()
            logger.info('Database pool closed')

    async def execute(self, query, *args):
        for attempt in range(3):
            try:
                async with self.pool.acquire() as conn:
                    return await conn.execute(query, *args)
            except (asyncpg.InterfaceError, asyncpg.ConnectionDoesNotExistError) as e:
                logger.warning(f'DB connection error (attempt {attempt+1}): {e}')
                if attempt < 2:
                    await asyncio.sleep(1)
                else:
                    raise

    async def fetchrow(self, query, *args):
        for attempt in range(3):
            try:
                async with self.pool.acquire() as conn:
                    return await conn.fetchrow(query, *args)
            except (asyncpg.InterfaceError, asyncpg.ConnectionDoesNotExistError) as e:
                logger.warning(f'DB connection error (attempt {attempt+1}): {e}')
                if attempt < 2:
                    await asyncio.sleep(1)
                else:
                    raise

    async def fetch(self, query, *args):
        for attempt in range(3):
            try:
                async with self.pool.acquire() as conn:
                    return await conn.fetch(query, *args)
            except (asyncpg.InterfaceError, asyncpg.ConnectionDoesNotExistError) as e:
                logger.warning(f'DB connection error (attempt {attempt+1}): {e}')
                if attempt < 2:
                    await asyncio.sleep(1)
                else:
                    raise

    async def fetchval(self, query, *args):
        for attempt in range(3):
            try:
                async with self.pool.acquire() as conn:
                    return await conn.fetchval(query, *args)
            except (asyncpg.InterfaceError, asyncpg.ConnectionDoesNotExistError) as e:
                logger.warning(f'DB connection error (attempt {attempt+1}): {e}')
                if attempt < 2:
                    await asyncio.sleep(1)
                else:
                    raise

    async def run_migration(self, sql):
        async with self.pool.acquire() as conn:
            await conn.execute(sql)
        logger.info('Migration executed successfully')
