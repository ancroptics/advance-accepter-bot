import logging
import asyncio
import asyncpg
import config

logger = logging.getLogger(__name__)

class DatabasePool:
    def __init__(self):
        self.pool = None
        self._connecting = False

    async def connect(self):
        if self._connecting:
            return
        self._connecting = True
        try:
            dsn = config.DATABASE_URL
            self.pool = await asyncpg.create_pool(
                dsn=dsn,
                min_size=2,
                max_size=10,
                command_timeout=60,
                statement_cache_size=0,
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
                    try:
                        await self.connect()
                    except Exception:
                        pass
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
                    try:
                        await self.connect()
                    except Exception:
                        pass
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
                    try:
                        await self.connect()
                    except Exception:
                        pass
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
                    try:
                        await self.connect()
                    except Exception:
                        pass
                else:
                    raise

    async def run_migration(self, sql):
        async with self.pool.acquire() as conn:
            await conn.execute(sql)
        logger.info('Migration executed successfully')


# Global database pool instance
db = DatabasePool()

# Module-level convenience functions used by models.py
async def execute(query, *args):
    return await db.execute(query, *args)

async def fetch(query, *args):
    return await db.fetch(query, *args)

async def fetchrow(query, *args):
    return await db.fetchrow(query, *args)

async def fetchval(query, *args):
    return await db.fetchval(query, *args)
