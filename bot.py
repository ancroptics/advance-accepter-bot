import asyncio
import logging
import sys
import socket
from datetime import datetime

from aiohttp import web
import httpx
from telegram import Update
from telegram.ext import Application

import config
from database.connection import DatabasePool
from database.models import DatabaseModels
from services.clone_manager import CloneManager
from services.scheduler_service import SchedulerService
from services.telethon_client import TelethonService
from handlers import register_all_handlers

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

async def error_handler(update, context):
    logger.error(f"Exception while handling an update: {context.error}", exc_info=context.error)

class Bot:
    def __init__(self):
        self.app = None
        self.db_pool = None
        self.db = None
        self.scheduler = None
        self.clone_manager = None
        self.health_runner = None
        self.telethon = None

    async def start(self):
        try:
            logger.info('Starting Telegram Growth Engine...')
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

            self.db_pool = DatabasePool()
            await self.db_pool.connect()
            self.db = DatabaseModels(self.db_pool)
            await self.db.run_migrations()
            logger.info('Database connected and tables created')

            self.telethon = TelethonService()
            telethon_ok = await self.telethon.start()
            if telethon_ok:
                logger.info('Telethon MTProto client connected - can fetch old pending join requests')
            else:
                logger.warning('Telethon not available - set TELETHON_API_ID, TELETHON_API_HASH, TELETHON_SESSION_STRING')

            builder = Application.builder().token(config.BOT_TOKEN)
            builder.read_timeout(30).write_timeout(30).connect_timeout(30)
            self.app = builder.build()

            self.app.bot_data['db'] = self.db
            self.app.bot_data['db_pool'] = self.db_pool
            self.app.bot_data['telethon'] = self.telethon

            await self._load_persisted_settings()

            self.scheduler = SchedulerService(self.app)
            self.app.bot_data['scheduler'] = self.scheduler

            self.clone_manager = CloneManager(self.db)
            self.app.bot_data['clone_manager'] = self.clone_manager

            register_all_handlers(self.app)
            self.app.add_error_handler(error_handler)

            await self.app.initialize()
            await self.app.start()

            try:
                from telegram import BotCommand
                commands = [
                    BotCommand('start', 'Open the dashboard'),
                    BotCommand('dashboard', 'Show your dashboard'),
                    BotCommand('channels', 'Manage your channels'),
                    BotCommand('help', 'Show help & features'),
                    BotCommand('scan', 'Scan channels for pending join requests'),
                    BotCommand('batch', 'Batch approve pending join requests'),
                    BotCommand('superadmin', 'Superadmin panel (admins only)'),
                    BotCommand('activate_premium', 'Activate premium (admins only)'),
                    BotCommand('deactivate_premium', 'Deactivate premium (admins only)'),
                ]
                await self.app.bot.set_my_commands(commands)
                logger.info(f'Registered {len(commands)} bot commands in menu')
            except Exception as _e:
                logger.error(f'set_my_commands failed: {_e}')


            await self.app.updater.start_polling(
                allowed_updates=[
                    "message", "edited_message", "callback_query",
                    "chat_join_request", "chat_member", "my_chat_member",
                    "channel_post",
                ],
                drop_pending_updates=False
            )

            await self.scheduler.start()
            logger.info('Scheduler started')

            asyncio.create_task(self._startup_pending_sync())
            asyncio.create_task(self._self_ping_loop())

            logger.info('Bot is running!')
            while True:
                await asyncio.sleep(3600)

        except Exception as e:
            logger.exception(f'Fatal error: {e}')
            await self.stop()
            sys.exit(1)

    async def _load_persisted_settings(self):
        try:
            toggle_keys = ['ENABLE_PREMIUM', 'ENABLE_CLONING', 'ENABLE_CROSS_PROMO']
            for key in toggle_keys:
                val = await self.db.get_platform_setting(key)
                if val is not None:
                    bool_val = val.lower() == 'true' if isinstance(val, str) else bool(val)
                    setattr(config, key, bool_val)
                    logger.info(f'Loaded persisted setting {key} = {bool_val}')
            logger.info('Persisted settings loaded from database')
        except Exception as e:
            logger.warning(f'Could not load persisted settings: {e}')

    async def _startup_pending_sync(self):
        await asyncio.sleep(5)
        try:
            logger.info('Starting pending request sync...')
            channels = await self.db.get_all_active_channels()
            if not channels:
                logger.info('No active channels to sync')
                return

            for ch in channels:
                chat_id = ch['chat_id']
                try:
                    if self.telethon and self.telethon.available:
                        await self._telethon_sync_channel(chat_id)
                    else:
                        pending_count = await self.db.get_pending_count(chat_id)
                        await self.db.update_channel_setting(chat_id, 'pending_requests', pending_count)

                    pending_count = await self.db.get_pending_count(chat_id)
                    if pending_count > 0:
                        stale = await self.db.get_stale_pending_requests(chat_id, hours=48)
                        cleaned = 0
                        for req in stale:
                            try:
                                member = await self.app.bot.get_chat_member(chat_id, req['user_id'])
                                if member.status in ('member', 'administrator', 'creator'):
                                    await self.db.update_join_request_status(req['user_id'], chat_id, 'approved', 'sync')
                                    cleaned += 1
                                elif member.status in ('kicked', 'banned'):
                                    await self.db.update_join_request_status(req['user_id'], chat_id, 'declined', 'sync')
                                    cleaned += 1
                            except Exception:
                                pass
                            await asyncio.sleep(0.5)
                        if cleaned > 0:
                            new_pending = await self.db.get_pending_count(chat_id)
                            await self.db.update_channel_setting(chat_id, 'pending_requests', new_pending)
                            logger.info(f'Sync: cleaned {cleaned} stale requests in {chat_id}, pending now {new_pending}')

                    logger.info(f'Synced channel {chat_id}: {await self.db.get_pending_count(chat_id)} pending')
                except Exception as e:
                    logger.warning(f'Failed to sync channel {chat_id}: {e}')

            logger.info('Pending request sync complete')
        except Exception as e:
            logger.exception(f'Startup sync error: {e}')

    async def _telethon_sync_channel(self, chat_id):
        try:
            logger.info(f'Telethon: fetching pending join requests for {chat_id}...')
            requests = await self.telethon.get_pending_join_requests(chat_id, limit=50000)
            if requests is None:
                logger.warning(f'Telethon: could not fetch requests for {chat_id}')
                return 0

            logger.info(f'Telethon: found {len(requests)} pending join requests for {chat_id}')
            saved = 0
            for req in requests:
                try:
                    await self.db.save_join_request(
                        user_id=req['user_id'],
                        chat_id=chat_id,
                        username=req.get('username'),
                        first_name=req.get('first_name'),
                    )
                    saved += 1
                except Exception as e:
                    logger.debug(f'Could not save request {req["user_id"]}: {e}')

                try:
                    await self.db.upsert_end_user(
                        user_id=req['user_id'],
                        username=req.get('username'),
                        first_name=req.get('first_name'),
                        source='telethon_sync',
                        source_channel=chat_id,
                    )
                except Exception:
                    pass

            pending = await self.db.get_pending_count(chat_id)
            await self.db.update_channel_setting(chat_id, 'pending_requests', pending)
            logger.info(f'Telethon: saved {saved} requests for {chat_id}, total pending in DB: {pending}')
            return saved
        except Exception as e:
            logger.exception(f'Telethon sync error for {chat_id}: {e}')
            return 0

    async def _self_ping_loop(self):
        import os
        url = os.getenv('RENDER_EXTERNAL_URL', f'http://localhost:{config.PORT}')
        health_url = f"{url}/health"
        logger.info(f'Self-ping loop started, target: {health_url}')
        while True:
            await asyncio.sleep(240)
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.get(health_url, timeout=10)
                    logger.info(f'Self-ping: {resp.status_code}')
            except Exception as e:
                logger.warning(f'Self-ping failed: {e}')

    async def stop(self):
        logger.info('Shutting down...')
        try:
            if self.telethon:
                await self.telethon.stop()
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
