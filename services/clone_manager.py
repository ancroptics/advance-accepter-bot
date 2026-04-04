import logging
from telegram import Bot
import config

logger = logging.getLogger(__name__)


class CloneManager:
    def __init__(self, application):
        self.application = application
        self.active_clones = {}

    @property
    def db(self):
        return self.application.bot_data.get('db')

    async def startup_all_clones(self):
        """Start all active clones from database."""
        try:
            if not self.db:
                logger.warning('DB not available for clone startup')
                return
            clones = await self.db.get_active_clones()
            logger.info(f'Starting {len(clones)} bot clones')
            for clone in clones:
                try:
                    await self._start_clone(clone)
                except Exception as e:
                    logger.error(f"Failed to start clone {clone['clone_id']}: {e}")
                    await self.db.update_clone_status(clone['clone_id'], error_msg=str(e))
        except Exception as e:
            logger.error(f'Error starting clones: {e}')

    async def _start_clone(self, clone):
        token = clone['bot_token']
        clone_id = clone['clone_id']
        try:
            bot = Bot(token=token)
            info = await bot.get_me()
            logger.info(f'Clone {clone_id} connected as @{info.username}')
            self.active_clones[clone_id] = {
                'bot': bot,
                'username': info.username,
                'token': token,
            }
        except Exception as e:
            logger.error(f'Clone {clone_id} start failed: {e}')
            raise

    async def shutdown_all_clones(self):
        for clone_id in list(self.active_clones.keys()):
            try:
                del self.active_clones[clone_id]
                logger.info(f'Stopped clone {clone_id}')
            except Exception as e:
                logger.error(f'Error stopping clone {clone_id}: {e}')
