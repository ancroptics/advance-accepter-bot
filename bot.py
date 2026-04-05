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

START_TIME = None
BOT_STATUS = {'db': False, 'bot': False}
# Will hold the telegram Application once it's ready
APP_HOLDER = {'app': None}


async def error_handler(update, context):
    """Global error handler to prevent 'No error handlers registered' warnings."""
    logger.error(f'Exception while handling an update: {context.error}', exc_info=context.error)
    if update and update.callback_query:
        try:
            await update.callback_query.answer('An error occurred. Please try again.', show_alert=True)
        except Exception:
            pass


async def start_health_server(port):
    """Start health+webhook server immediately so Render sees us as alive."""
    app = web.Application()

    async def health_handler(request):
        uptime = (datetime.utcnow() - START_TIME).total_seconds() if START_TIME else 0
        return web.json_response({
            'status': 'healthy',
            'uptime_seconds': int(uptime),
            'version': '2.0.0',
            'db_connected': BOT_STATUS['db'],
            'bot_running': BOT_STATUS['bot'],
        })

    async def webhook_handler(request):
        """Handle Telegram webhook updates. Returns 200 even if bot isn't ready yet."""
        application = APP_HOLDER.get('app')
        if not application or not BOT_STATUS['bot']:
            # Bot not ready yet, acknowledge to Telegram so it doesn't retry too aggressively
            return web.Response(status=200)
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
    return app


async def connect_db_with_retry(dsn, max_retries=5):
    """Try connecting to DB with retries and exponential backoff."""
    for attempt in range(max_retries):
        try:
            logger.info(f'DB connection attempt {attempt + 1}/{max_retries}...')
            pool = await asyncio.wait_for(
                DatabasePool.create(dsn),
                timeout=30
            )
            logger.info('Database connected successfully')
            return pool
        except Exception as e:
            logger.warning(f'DB connection attempt {attempt + 1} failed: {e}')
            if attempt < max_retries - 1:
                wait_time = min(2 ** attempt * 2, 30)
                logger.info(f'Retrying in {wait_time}s...')
                await asyncio.sleep(wait_time)
    raise Exception(f'Failed to connect to database after {max_retries} attempts')


async def main():
    global START_TIME
    START_TIME = datetime.utcnow()

    if not config.BOT_TOKEN:
        logger.error('BOT_TOKEN not set!')
        sys.exit(1)

    # Force IPv4 for DNS resolution (Render free tier IPv6 issue)
    original_getaddrinfo = socket.getaddrinfo
    def force_ipv4_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
        return original_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)
    socket.getaddrinfo = force_ipv4_getaddrinfo

    # Start health+webhook server FIRST so Render sees us as alive
    health_app = await start_health_server(config.PORT)
    runner = web.AppRunner(health_app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', config.PORT)
    await site.start()
    logger.info(f'Health server running on port {config.PORT}')

    try:
        # Build telegram application
        application = Application.builder().token(config.BOT_TOKEN).build()
        register_all_handlers(application)
        application.add_error_handler(error_handler)
        await application.initialize()

        # Connect to database with retries
        db_pool = await connect_db_with_retry(config.DATABASE_URL)
        application.bot_data['db_pool'] = db_pool
        application.bot_data['db'] = DatabaseModels(db_pool)
        await application.bot_data['db'].run_migrations()
        BOT_STATUS['db'] = True
        logger.info('Database initialized and migrations complete')

        # Clone manager
        clone_manager = CloneManager(application)
        application.bot_data['clone_manager'] = clone_manager
        await clone_manager.startup_all_clones()
        logger.info('Clone manager initialized')

        # Scheduler
        scheduler = SchedulerService(application)
        application.bot_data['scheduler'] = scheduler
        scheduler.start()
        logger.info('Scheduler started')

        await application.start()
        BOT_STATUS['bot'] = True

        # Store the application so the webhook handler can use it
        APP_HOLDER['app'] = application

        if config.USE_WEBHOOK:
            webhook_url = f'{config.WEBHOOK_URL}/webhook'
            await application.bot.set_webhook(
                url=webhook_url,
                allowed_updates=['message', 'callback_query', 'chat_join_request', 'my_chat_member', 'chat_member'],
                drop_pending_updates=False,
            )
            logger.info(f'Webhook set to {webhook_url}')

            # Notify superadmins
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
                await application.stop()
                await application.shutdown()
                scheduler.stop()
                await clone_manager.shutdown_all_clones()
                await db_pool.close()
        else:
            logger.info('Starting polling mode')
            await application.updater.start_polling(
                allowed_updates=['message', 'callback_query', 'chat_join_request', 'my_chat_member', 'chat_member'],
                drop_pending_updates=False,
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
    except Exception as e:
        logger.exception(f'Fatal error during startup: {e}')
        # Keep health server running so we can see logs
        logger.info('Bot failed to start but health server remains up for debugging')
        try:
            await asyncio.Event().wait()
        except (KeyboardInterrupt, SystemExit):
            pass
    finally:
        await runner.cleanup()


if __name__ == '__main__':
    asyncio.run(main())
