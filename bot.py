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
    level=logging.INFO,
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

async def error_handler(update, context):
    """Log errors caused by updates."""
    logger.error(f"Exception while handling an update: {context.error}", exc_info=context.error)

class Bot:
    def __init__(self):
        self.app = None
        self.db_pool = None
        self.db = None
        self.web_app = None
        self.web_runner = None
        self.scheduler = None
        self.clone_manager = None

    async def initialize(self):
        """Initialize bot, database, and services."""
        logger.info('Initializing bot...')

        # Database
        self.db_pool = DatabasePool()
        pool = await self.db_pool.connect()
        self.db = DatabaseModels(pool)
        await self.db.run_migrations()
        logger.info('Database connected and migrated')

        # Telegram application
        self.app = Application.builder().token(config.BOT_TOKEN).build()
        self.app.bot_data['db'] = self.db
        self.app.bot_data['bot_instance'] = self

        # Register handlers
        register_all_handlers(self.app)
        self.app.add_error_handler(error_handler)

        # Start polling
        await self.app.initialize()
        await self.app.start()
        try:
            await self.app.updater.start_polling(
                allowed_updates=[
                    "message", "edited_message", "callback_query",
                    "chat_join_request", "chat_member", "my_chat_member",
                    "channel_post",
                ],
                drop_pending_updates=False
            )
            logger.info('Polling started successfully')
        except Exception as e:
            logger.error(f'Polling error: {e}')
            raise

        # Services
        self.scheduler = SchedulerService(self.app)
        await self.scheduler.start()

        self.clone_manager = CloneManager(self.db, self.app)
        await self.clone_manager.start_all_clones()

        # Health check web server
        await self._start_health_server()

        logger.info('Bot fully initialized and running')

    async def _start_health_server(self):
        """Start aiohttp health check server for Render."""
        self.web_app = web.Application()
        self.web_app.router.add_get('/health', self._health_handler)
        self.web_app.router.add_get('/', self._health_handler)

        self.web_runner = web.AppRunner(self.web_app)
        await self.web_runner.setup()

        port = int(config.PORT) if hasattr(config, 'PORT') and config.PORT else 10000
        try:
            site = web.TCPSite(self.web_runner, '0.0.0.0', port)
            await site.start()
            logger.info(f'Health server on port {port}')
        except OSError as e:
            logger.warning(f'Port {port} in use, trying {port + 1}')
            site = web.TCPSite(self.web_runner, '0.0.0.0', port + 1)
            await site.start()

    async def _health_handler(self, request):
        return web.json_response({
            'status': 'healthy',
            'bot': 'running',
            'timestamp': datetime.utcnow().isoformat(),
            'polling': self.app.updater.running if self.app and self.app.updater else False
        })

    async def shutdown(self):
        logger.info('Shutting down...')
        if self.scheduler:
            await self.scheduler.stop()
        if self.clone_manager:
            await self.clone_manager.stop_all_clones()
        if self.web_runner:
            await self.web_runner.cleanup()
        if self.app:
            try:
                await self.app.updater.stop()
                await self.app.stop()
                await self.app.shutdown()
            except Exception as e:
                logger.error(f'Shutdown error: {e}')
        if self.db_pool:
            await self.db_pool.disconnect()
        logger.info('Shutdown complete')

async def main():
    bot = Bot()
    try:
        await bot.initialize()
        # Keep running
        while True:
            await asyncio.sleep(3600)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.exception(f'Fatal error: {e}')
    finally:
        await bot.shutdown()

if __name__ == '__main__':
    asyncio.run(main())
