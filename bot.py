import asyncio
import logging
import sys
import socket
from datetime import datetime

from aiohttp import web
from telegram import Update
from telegram.ext import Application

import config
from database import Database
from services.scheduler_service import SchedulerService
from handlers import register_all_handlers

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


class Bot:
    def __init__(self):
        self.db = None
        self.app = None
        self.scheduler = None

    async def start(self):
        logger.info('Starting bot...')
        self.db = Database()
        await self.db.connect()
        logger.info('Database connected')

        self.app = (
            Application.builder()
            .token(config.BOT_TOKEN)
            .build()
        )
        self.app.bot_data['db'] = self.db
        self.app.bot_data['start_time'] = datetime.utcnow()

        register_all_handlers(self.app)

        self.scheduler = SchedulerService(self.app)
        await self.scheduler.start()

        await self.app.initialize()
        await self.app.start()

        await self.app.updater.start_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=False
        )

        logger.info('Bot is running!')

        # Health check server for Render
        app_web = web.Application()
        app_web.router.add_get('/', self.health_check)
        app_web.router.add_get('/health', self.health_check)

        port = int(config.PORT) if hasattr(config, 'PORT') and config.PORT else 10000
        runner = web.AppRunner(app_web)
        await runner.setup()

        # Try binding to port, handle address already in use
        try:
            site = web.TCPSite(runner, '0.0.0.0', port)
            await site.start()
            logger.info(f'Health check server on port {port}')
        except OSError as e:
            if 'Address already in use' in str(e):
                logger.warning(f'Port {port} in use, trying {port + 1}')
                site = web.TCPSite(runner, '0.0.0.0', port + 1)
                await site.start()
            else:
                raise

        # Keep running
        try:
            while True:
                await asyncio.sleep(3600)
        except (KeyboardInterrupt, SystemExit):
            pass
        finally:
            await self.stop()

    async def stop(self):
        logger.info('Stopping bot...')
        if self.scheduler:
            await self.scheduler.stop()
        if self.app:
            await self.app.updater.stop()
            await self.app.stop()
            await self.app.shutdown()
        if self.db:
            await self.db.close()

    async def health_check(self, request):
        return web.Response(text='OK')


if __name__ == '__main__':
    bot = Bot()
    try:
        asyncio.run(bot.start())
    except KeyboardInterrupt:
        logger.info('Bot stopped by user')
    except Exception as e:
        logger.exception(f'Fatal error: {e}')
        sys.exit(1)
