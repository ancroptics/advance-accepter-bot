import asyncio
import logging
import sys

from telegram.ext import (
    Application,
    CommandHandler,
    ChatJoinRequestHandler,
    ChatMemberHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ConversationHandler,
)

import config
from database.connection import DatabasePool
from database.models import DatabaseModels
from services.health_server import HealthServer
from services.clone_manager import CloneManager
from services.scheduler_service import SchedulerService
from handlers import register_all_handlers

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


async def post_init(application):
    """Post-initialization: set up DB, clones, scheduler."""
    try:
        # Initialize database
        db_pool = await DatabasePool.create(config.DATABASE_URL)
        application.bot_data['db_pool'] = db_pool
        application.bot_data['db'] = DatabaseModels(db_pool)

        # Run migrations
        await application.bot_data['db'].run_migrations()
        logger.info('Database initialized and migrations complete')

        # Initialize clone manager
        clone_manager = CloneManager(application)
        application.bot_data['clone_manager'] = clone_manager
        await clone_manager.startup_all_clones()
        logger.info('Clone manager initialized')

        # Initialize scheduler
        scheduler = SchedulerService(application)
        application.bot_data['scheduler'] = scheduler
        scheduler.start()
        logger.info('Scheduler started')

        # Start health server
        health_server = HealthServer(application)
        application.bot_data['health_server'] = health_server
        await health_server.start()
        logger.info(f'Health server started on port {config.PORT}')

        # Notify superadmin
        db = application.bot_data['db']
        channel_count = await db.get_active_channel_count()
        clone_count = await db.get_active_clone_count()
        for admin_id in config.SUPERADMIN_IDS:
            try:
                await application.bot.send_message(
                    admin_id,
                    f"\U0001f7e2 Bot started successfully!\n\n"
                    f"\U0001f4e2 Active Channels: {channel_count}\n"
                    f"\U0001f9ec Active Clones: {clone_count}\n"
                    f"\U0001f310 Webhook: {'ON' if config.USE_WEBHOOK else 'OFF'}\n"
                    f"\U0001f4bb Port: {config.PORT}"
                )
            except Exception as e:
                logger.warning(f'Could not notify superadmin {admin_id}: {e}')

    except Exception as e:
        logger.exception(f'Error in post_init: {e}')
        raise


async def post_shutdown(application):
    """Cleanup on shutdown."""
    try:
        if 'health_server' in application.bot_data:
            await application.bot_data['health_server'].stop()
        if 'clone_manager' in application.bot_data:
            await application.bot_data['clone_manager'].shutdown_all_clones()
        if 'scheduler' in application.bot_data:
            application.bot_data['scheduler'].stop()
        if 'db_pool' in application.bot_data:
            await application.bot_data['db_pool'].close()
        logger.info('Shutdown complete')
    except Exception as e:
        logger.exception(f'Error in post_shutdown: {e}')


def main():
    """Main entry point."""
    if not config.BOT_TOKEN:
        logger.error('BOT_TOKEN not set!')
        sys.exit(1)

    builder = Application.builder().token(config.BOT_TOKEN)
    builder.post_init(post_init)
    builder.post_shutdown(post_shutdown)
    application = builder.build()

    # Register all handlers
    register_all_handlers(application)

    if config.USE_WEBHOOK:
        logger.info(f'Starting webhook mode on {config.WEBHOOK_URL}/webhook')
        application.run_webhook(
            listen='0.0.0.0',
            port=config.PORT,
            url_path='/webhook',
            webhook_url=f'{config.WEBHOOK_URL}/webhook',
            allowed_updates=[
                'message', 'callback_query', 'chat_join_request',
                'my_chat_member', 'chat_member'
            ],
            drop_pending_updates=True,
        )
    else:
        logger.info('Starting polling mode')
        application.run_polling(
            allowed_updates=[
                'message', 'callback_query', 'chat_join_request',
                'my_chat_member', 'chat_member'
            ],
            drop_pending_updates=True,
        )


if __name__ == '__main__':
    main()
