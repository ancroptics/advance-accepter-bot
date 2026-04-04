import asyncio
import logging
from aiohttp import web
from datetime import datetime

logger = logging.getLogger(__name__)


class HealthServer:
    def __init__(self, db=None, bot=None, port=8080):
        self.db = db
        self.bot = bot
        self.port = port
        self.app = web.Application()
        self.app.router.add_get('/', self.health_check)
        self.app.router.add_get('/health', self.health_check)
        self.app.router.add_get('/ready', self.readiness_check)
        self._runner = None
        self._start_time = datetime.utcnow()

    async def health_check(self, request):
        uptime = (datetime.utcnow() - self._start_time).total_seconds()
        return web.json_response({
            'status': 'healthy',
            'uptime_seconds': int(uptime),
            'timestamp': datetime.utcnow().isoformat(),
        })

    async def readiness_check(self, request):
        checks = {'database': False, 'bot': False}
        try:
            if self.db and self.db.pool:
                await self.db.execute('SELECT 1')
                checks['database'] = True
        except Exception as e:
            logger.warning(f'DB health check failed: {e}')

        try:
            if self.bot:
                await self.bot.get_me()
                checks['bot'] = True
        except Exception as e:
            logger.warning(f'Bot health check failed: {e}')

        all_ok = all(checks.values())
        status = 200 if all_ok else 503
        return web.json_response({
            'status': 'ready' if all_ok else 'not_ready',
            'checks': checks,
            'timestamp': datetime.utcnow().isoformat(),
        }, status=status)

    async def start(self):
        self._runner = web.AppRunner(self.app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, '0.0.0.0', self.port)
        await site.start()
        logger.info(f'Health server running on port {self.port}')

    async def stop(self):
        if self._runner:
            await self._runner.cleanup()
            logger.info('Health server stopped')
