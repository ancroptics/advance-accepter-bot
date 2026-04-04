import logging
from aiohttp import web
import config

logger = logging.getLogger(__name__)


class HealthServer:
    def __init__(self, port=None):
        self.port = port or config.PORT
        self.runner = None

    async def start(self):
        app = web.Application()
        app.router.add_get('/', self.health_check)
        app.router.add_get('/health', self.health_check)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, '0.0.0.0', self.port)
        await site.start()
        logger.info(f'Health server started on port {self.port}')

    async def health_check(self, request):
        return web.json_response({'status': 'healthy'})

    async def stop(self):
        if self.runner:
            await self.runner.cleanup()
