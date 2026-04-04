import logging
import asyncio
from telegram.ext import Application, ChatJoinRequestHandler, ChatMemberHandler, CommandHandler, CallbackQueryHandler, MessageHandler, filters

logger = logging.getLogger(__name__)


class CloneManager:
    def __init__(self):
        self.active_clones = {}  # clone_id -> Application

    async def start_clone(self, clone_id, bot_token, owner_id):
        logger.info(f'Starting clone {clone_id} for owner {owner_id}')
        try:
            from handlers.join_request import join_request_handler
            from handlers.channel_detection import channel_detection_handler
            from handlers.start import start_handler
            from handlers.callbacks import callback_router

            app = Application.builder().token(bot_token).build()
            app.bot_data['clone_id'] = clone_id
            app.bot_data['clone_owner_id'] = owner_id
            app.bot_data['is_clone'] = True

            # Share database with master
            from bot import master_db
            app.bot_data['db'] = master_db

            # Register handlers
            app.add_handler(CommandHandler('start', start_handler))
            app.add_handler(ChatJoinRequestHandler(join_request_handler))
            app.add_handler(ChatMemberHandler(channel_detection_handler, ChatMemberHandler.MY_CHAT_MEMBER))
            app.add_handler(CallbackQueryHandler(callback_router))

            await app.initialize()
            await app.start()

            # Set webhook
            import config
            webhook_url = f'{config.CLONE_WEBHOOK_BASE_URL}/{clone_id}'
            await app.bot.set_webhook(webhook_url)

            self.active_clones[clone_id] = app
            logger.info(f'Clone {clone_id} started successfully')
        except Exception as e:
            logger.exception(f'Failed to start clone {clone_id}: {e}')
            raise

    async def stop_clone(self, clone_id):
        logger.info(f'Stopping clone {clone_id}')
        app = self.active_clones.pop(clone_id, None)
        if app:
            try:
                await app.bot.delete_webhook()
                await app.stop()
                await app.shutdown()
            except Exception as e:
                logger.error(f'Error stopping clone {clone_id}: {e}')

    async def restart_clone(self, clone_id, bot_token, owner_id):
        await self.stop_clone(clone_id)
        await asyncio.sleep(1)
        await self.start_clone(clone_id, bot_token, owner_id)

    async def startup_all_clones(self, db):
        logger.info('Starting all active clones...')
        clones = await db.get_active_clones()
        started = 0
        failed = 0
        for clone in (clones or []):
            try:
                await self.start_clone(
                    clone['clone_id'],
                    clone['bot_token'],
                    clone['owner_id']
                )
                started += 1
            except Exception as e:
                failed += 1
                logger.error(f"Failed to start clone {clone['clone_id']}: {e}")
        logger.info(f'Clones started: {started}, failed: {failed}')
        return started, failed

    async def health_check_clones(self, db):
        for clone_id, app in list(self.active_clones.items()):
            try:
                await app.bot.get_me()
                await db.update_clone_health(clone_id)
            except Exception as e:
                logger.error(f'Clone {clone_id} health check failed: {e}')
                await db.increment_clone_errors(clone_id, str(e))
                clone = await db.get_clone(clone_id)
                if clone and clone.get('error_count', 0) > 5:
                    logger.warning(f'Deactivating clone {clone_id} due to errors')
                    await self.stop_clone(clone_id)
                    await db.update_clone_status(clone_id, is_active=False)

    async def process_clone_update(self, clone_id, update_data):
        app = self.active_clones.get(clone_id)
        if not app:
            logger.warning(f'No active clone for id {clone_id}')
            return False
        try:
            from telegram import Update
            update = Update.de_json(update_data, app.bot)
            await app.process_update(update)
            return True
        except Exception as e:
            logger.error(f'Error processing update for clone {clone_id}: {e}')
            return False

    async def shutdown_all(self):
        for clone_id in list(self.active_clones.keys()):
            await self.stop_clone(clone_id)
