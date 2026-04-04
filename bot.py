import asyncio
import logging
import sys
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

START_TIME = None


async def main():
    global START_TIME
    START_TIME = datetime.utcnow()

    if not config.BOT_TOKEN:
        logger.error('BOT_TOKEN not set!')
        sys.exit(1)

    application = Application.builder().token(config.BOT_TOKEN).build()
    register_all_handlers(application)
    await application.initialize()

    db_pool = await DatabasePool.create(config.DATABASE_URL)
    application.bot_data['db_pool'] = db_pool
    application.bot_data['db'] = DatabaseModels(db_pool)
    await application.bot_data['db'].run_migrations()
    logger.info('Database initialized and migrations complete')

    clone_manager = CloneManager(application)
    application.bot_data['clone_manager'] = clone_manager
    await clone_manager.startup_all_clones()
    logger.info('Clone manager initialized')

    scheduler = SchedulerService(application)
    application.bot_data['scheduler'] = scheduler
    scheduler.start()
    logger.info('Scheduler started')

    await application.start()

    if config.USE_WEBHOOK:
        webhook_url = f'{config.WEBHOOK_URL}/webhook'
        await application.bot.set_webhook(
            url=webhook_url,
            allowed_updates=['message', 'callback_query', 'chat_join_request', 'my_chat_member', 'chat_member'],
            drop_pending_updates=True,
        )
        logger.info(f'Webhook set to {webhook_url}')

        app = web.Application()

        async def health_handler(request):
            uptime = (datetime.utcnow() - START_TIME).total_seconds()
            return web.json_response({'status': 'healthy', 'uptime_seconds': int(uptime), 'version': '2.0.0'})

        async def webhook_handler(request):
            try:
                data = await request.json()
                update = Update.de_json(data, application.bot)
                await application.update_queue.put(update)
            except Exception as e:
                logger.error(f'Error processing webhook update: {e}')
            return web.Response(status=200)

        app.router.add_get('/', health_handler)
        app.router.add_get('/health', health_handler)
        app.router.add_post('/webhook', webhook_handler)

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', config.PORT)
        await site.start()
        logger.info(f'Server running on port {config.PORT}')

        db = application.bot_data['db']
        channel_count = await db.get_active_channel_count()
        clone_count = await db.get_active_clone_count()
        for admin_id in config.SUPERADMIN_IDS:
            try:
                await application.bot.send_message(admin_id,
                    f'\U0001f7e2 Bot started successfully!\n\n'
                    f'\U0001f4e2 Active Channels: {channel_count}\n'
                    f'\U0001f9ec Active Clones: {clone_count}\n'
                    f'\U0001f310 Webhook: ON\n'
                    f'\U0001f4bb Port: {config.PORT}')
            except Exception as e:
                logger.warning(f'Could not notify superadmin {admin_id}: {e}')

        try:
            await asyncio.Event().wait()
        except (KeyboardInterrupt, SystemExit):
            pass
        finally:
            await runner.cleanup()
            await application.stop()
            await application.shutdown()
            scheduler.stop()
            await clone_manager.shutdown_all_clones()
            await db_pool.close()
    else:
        logger.info('Starting polling mode')
        await application.updater.start_polling(
            allowed_updates=['message', 'callback_query', 'chat_join_request', 'my_chat_member', 'chat_member'],
            drop_pending_updates=True,
        )
        try:
            await asyncio.Event().wait()
        except (KeyboardInterrupt, SystemExit):
            pass
        finally:
            await application.updater.stop()
            await application.stop()
            await application.shutdown()
            scheduler.stop()
            await clone_manager.shutdown_all_clones()
            await db_pool.close()


if __name__ == '__main__':
    asyncio.run(main())
