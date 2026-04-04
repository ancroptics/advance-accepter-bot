import logging
import asyncio
from telegram.ext import Application
from telegram import Bot
from database.models import get_bot_clones, update_clone_status
import config

logger = logging.getLogger(__name__)


class CloneManager:
    def __init__(self, db, main_app):
        self.db = db
        self.main_app = main_app
        self.active_clones = {}
        self._running = False

    async def start(self):
        self._running = True
        clones = await get_bot_clones(self.db, active=True)
        logger.info(f'Starting {len(clones)} bot clones')
        for clone in clones:
            try:
                await self._start_clone(clone)
            except Exception as e:
                logger.error(f"Failed to start clone {clone['id']}: {e}")
                await update_clone_status(self.db, clone['id'], 'error', str(e))

    async def _start_clone(self, clone):
        token = clone['bot_token']
        clone_id = clone['id']
        try:
            bot = Bot(token=token)
            info = await bot.get_me()
            logger.info(f'Clone {clone_id} connected as @{info.username}')
            self.active_clones[clone_id] = {
                'bot': bot,
                'username': info.username,
                'token': token,
            }
            await update_clone_status(self.db, clone_id, 'running')
        except Exception as e:
            logger.error(f'Clone {clone_id} start failed: {e}')
            await update_clone_status(self.db, clone_id, 'error', str(e))
            raise

    async def stop_clone(self, clone_id):
        if clone_id in self.active_clones:
            clone = self.active_clones.pop(clone_id)
            logger.info(f'Stopped clone {clone_id}')
            await update_clone_status(self.db, clone_id, 'stopped')

    async def add_clone(self, owner_id, bot_token, label=''):
        from database.models import create_bot_clone
        clone = await create_bot_clone(self.db, owner_id, bot_token, label)
        try:
            await self._start_clone(clone)
            return clone
        except Exception as e:
            await update_clone_status(self.db, clone['id'], 'error', str(e))
            raise

    async def stop_all(self):
        self._running = False
        for cid in list(self.active_clones.keys()):
            await self.stop_clone(cid)
        logger.info('All clones stopped')

    def get_active_count(self):
        return len(self.active_clones)

    def get_clone_info(self, clone_id):
        return self.active_clones.get(clone_id)
