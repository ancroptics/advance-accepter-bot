import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler

logger = logging.getLogger(__name__)


class SchedulerService:
    def __init__(self, application):
        self.application = application
        self.scheduler = AsyncIOScheduler()

    def start(self):
        """Start the scheduler (synchronous call)."""
        try:
            self.scheduler.start()
            logger.info('Scheduler service started')
        except Exception as e:
            logger.error(f'Error starting scheduler: {e}')

    def stop(self):
        """Stop the scheduler."""
        try:
            if self.scheduler.running:
                self.scheduler.shutdown(wait=False)
                logger.info('Scheduler stopped')
        except Exception as e:
            logger.error(f'Error stopping scheduler: {e}')
