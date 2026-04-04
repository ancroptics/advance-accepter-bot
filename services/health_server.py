import logging
import json
import time
from aiohttp import web

logger = logging.getLogger(__name__)


class HealthServer:
    def __init__(self, bot_app, clone_manager=None, db=None):
        self.bot_app = bot_app
        self.clone_manager = clone_manager
        self.db = db
        self.start_time = time.time()
        self.app = web.Application()
        self.app.router.add_get('/health', self.health_handler)
        self.app.router.add_post('/webhook', self.webhook_handler)
        self.app.router.add_post('/clone/{clone_id}', self.clone_webhook_handler)
        self.runner = None

    async def health_handler(self, request):
        uptime = int(time.time() - self.start_time)
        channels = 0
        clones = 0
        if self.db:
            try:
                channels = await self.db.get_total_channel_count()
                clones = len(self.clone_manager.active_clones) if self.clone_manager else 0
            except Exception:
                pass
        data = {
            'status': 'running',
            'uptime': uptime,
            'channels': channels,
            'clones': clones,
            'version': '2.0.0'
        }
        return web.json_response(data)

    async def webhook_handler(self, request):
        try:
            data = await request.json()
            from telegram import Update
            update = Update.de_json(data, self.bot_app.bot)
            await self.bot_app.process_update(update)
            return web.Response(status=200)
        except Exception as e:
            logger.error(f'Webhook error: {e}')
            return web.Response(status=500)

    async def clone_webhook_handler(self, request):
        clone_id = request.match_info.get('clone_id')
        if not clone_id or not self.clone_manager:
            return web.Response(status=404)
        try:
            clone_id = int(clone_id)
            data = await request.json()
            success = await self.clone_manager.process_clone_update(clone_id, data)
            return web.Response(status=200 if success else 404)
        except Exception as e:
            logger.error(f'Clone webhook error: {e}')
            return web.Response(status=500)

    async def start(self, port):
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, '0.0.0.0', port)
        await site.start()
        logger.info(f'Health server started on port {port}')

    async def stop(self):
        if self.runner:
            await self.runner.cleanup()
