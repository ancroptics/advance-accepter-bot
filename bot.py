import asyncio
import logging
import sys
import socket
from datetime import datetime

from aiohttp import web
from telegram import Update
from telegram.ext import Application

import config
from database.connection import DatabasePool
from database.models import DatabaseModels
from services.clone_manager import CloneManager
from services.scheduler_service import SchedulerService
from handlers import register_all_handlers

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class Bot:
    def __init__(self):
        self.app = None
        self.db_pool = None
        self.db = None
        self.scheduler = None
        self.clone_manager = None
        self.health_runner = None

    async def start(self):
        try:
            logger.info('Starting Telegram Growth Engine...')

            self.db_pool = DatabasePool()
            pool = await self.db_pool.create_pool()
            self.db = DatabaseModels(pool)
            await self.db.create_tables()
            logger.info('Database connected and tables created')

            builder = Application.builder().token(config.BOT_TOKEN)
            builder.read_timeout(30).write_timeout(30).connect_timeout(30)
            self.app = builder.build()

            self.app.bot_data['db'] = self.db
            self.app.bot_data['db_pool'] = self.db_pool

            self.scheduler = SchedulerService(self.app)
            self.app.bot_data['scheduler'] = self.scheduler

            self.clone_manager = CloneManager(self.db)
            self.app.bot_data['clone_manager'] = self.clone_manager

            register_all_handlers(self.app)

            await self.app.initialize()
            await self.app.start()

            # CRITICAL: drop_pending_updates=False to catch join requests during downtime
            await self.app.updater.start_polling(
                allowed_updates=Update.ALL_TYPES,
                drop_pending_updates=False
            )

            await self.scheduler.start()
            logger.info('Scheduler started')

            # Sync pending requests for all managed channels on startup
            asyncio.create_task(self._startup_pending_sync())

            health_app = web.Application()
            health_app.router.add_get('/', self._health_check)
            health_app.router.add_get('/health', self._health_check)
            runner = web.AppRunner(health_app)
            await runner.setup()
            port = config.PORT
            site = web.TCPSite(runner, '0.0.0.0', port)
            await site.start()
            self.health_runner = runner
            logger.info(f'Health server on port {port}')

            logger.info('Bot is running!')
            while True:
                await asyncio.sleep(3600)

        except Exception as e:
            logger.exception(f'Fatal error: {e}')
            await self.stop()
            sys.exit(1)

    async def _startup_pending_sync(self):
        """On startup, sync pending request counts and clean stale requests."""
        await asyncio.sleep(5)  # Wait for polling to start receiving updates
        try:
            logger.info('Starting pending request sync...')
            channels = await self.db.get_all_active_channels()
            if not channels:
                logger.info('No active channels to sync')
                return

            for ch in channels:
                chat_id = ch['chat_id']
                try:
                    # Update pending count from DB
                    pending_count = await self.db.get_pending_count(chat_id)
                    await self.db.update_channel_setting(chat_id, 'pending_requests', pending_count)

                    # Try to verify stale pending requests (ones that may have been
                    # approved/declined outside the bot or expired)
                    if pending_count > 0:
                        stale = await self.db.get_stale_pending_requests(chat_id, hours=48)
                        cleaned = 0
                        for req in stale:
                            try:
                                # Try to approve - if already approved/declined, Telegram returns error
                                member = await self.app.bot.get_chat_member(chat_id, req['user_id'])
                                if member.status in ('member', 'administrator', 'creator'):
                                    # Already a member - mark as approved
                                    await self.db.update_join_request_status(
                                        req['user_id'], chat_id, 'approved', 'sync')
                                    cleaned += 1
                                elif member.status in ('kicked', 'banned'):
                                    await self.db.update_join_request_status(
                                        req['user_id'], chat_id, 'declined', 'sync')
                                    cleaned += 1
                            except Exception:
                                pass
                            await asyncio.sleep(0.5)  # Rate limiting

                        if cleaned > 0:
                            new_pending = await self.db.get_pending_count(chat_id)
                            await self.db.update_channel_setting(chat_id, 'pending_requests', new_pending)
                            logger.info(f'Sync: cleaned {cleaned} stale requests in {chat_id}, pending now {new_pending}')

                    logger.info(f'Synced channel {chat_id}: {pending_count} pending')
                except Exception as e:
                    logger.warning(f'Failed to sync channel {chat_id}: {e}')

            logger.info('Pending request sync complete')
        except Exception as e:
            logger.exception(f'Startup sync error: {e}')

    async def stop(self):
        logger.info('Shutting down...')
        try:
            if self.scheduler:
                await self.scheduler.stop()
            if self.health_runner:
                await self.health_runner.cleanup()
            if self.app:
                if self.app.updater and self.app.updater.running:
                    await self.app.updater.stop()
                await self.app.stop()
                await self.app.shutdown()
            if self.db_pool:
                await self.db_pool.close()
        except Exception as e:
            logger.exception(f'Error during shutdown: {e}')

    async def _health_check(self, request):
        return web.json_response({
            'status': 'ok',
            'bot': config.BOT_TOKEN[:8] + '...',
            'time': datetime.utcnow().isoformat()
        })

def main():
    bot = Bot()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(bot.start())
    except KeyboardInterrupt:
        loop.run_until_complete(bot.stop())
    finally:
        loop.close()

if __name__ == '__main__':
    main()
