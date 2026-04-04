import asyncio
import logging
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from database.models import (
    get_pending_scheduled_posts,
    mark_scheduled_post_done,
    get_recurring_posts,
)

logger = logging.getLogger(__name__)


class SchedulerService:
    def __init__(self, db, bot):
        self.db = db
        self.bot = bot
        self.scheduler = AsyncIOScheduler()
        self._jobs = {}

    async def start(self):
        self.scheduler.add_job(
            self._process_pending,
            'interval',
            minutes=1,
            id='process_pending',
            replace_existing=True,
        )
        self.scheduler.add_job(
            self._load_recurring,
            'interval',
            hours=1,
            id='load_recurring',
            replace_existing=True,
        )
        self.scheduler.start()
        await self._load_recurring()
        logger.info('Scheduler service started')

    async def _process_pending(self):
        try:
            posts = await get_pending_scheduled_posts(self.db)
            now = datetime.utcnow()
            for post in posts:
                if post['scheduled_at'] <= now:
                    await self._send_post(post)
                    await mark_scheduled_post_done(self.db, post['id'])
        except Exception as e:
            logger.error(f'Error processing pending posts: {e}')

    async def _load_recurring(self):
        try:
            recurring = await get_recurring_posts(self.db)
            for rp in recurring:
                job_id = f"recurring_{rp['id']}"
                if job_id not in self._jobs:
                    trigger = CronTrigger.from_crontab(rp['cron_expression'])
                    job = self.scheduler.add_job(
                        self._send_recurring,
                        trigger,
                        args=[rp],
                        id=job_id,
                        replace_existing=True,
                    )
                    self._jobs[job_id] = job
        except Exception as e:
            logger.error(f'Error loading recurring posts: {e}')

    async def _send_post(self, post):
        try:
            channel_id = post['channel_id']
            if post.get('media_type') == 'photo':
                await self.bot.send_photo(
                    chat_id=channel_id,
                    photo=post['media_file_id'],
                    caption=post.get('text', ''),
                    parse_mode='HTML',
                )
            elif post.get('media_type') == 'video':
                await self.bot.send_video(
                    chat_id=channel_id,
                    video=post['media_file_id'],
                    caption=post.get('text', ''),
                    parse_mode='HTML',
                )
            else:
                await self.bot.send_message(
                    chat_id=channel_id,
                    text=post.get('text', ''),
                    parse_mode='HTML',
                )
            logger.info(f"Sent scheduled post {post['id']} to {channel_id}")
        except Exception as e:
            logger.error(f"Failed to send post {post['id']}: {e}")

    async def _send_recurring(self, rp):
        await self._send_post(rp)

    async def schedule_post(self, channel_id, text, scheduled_at, media_type=None, media_file_id=None):
        from database.models import create_scheduled_post
        post = await create_scheduled_post(
            self.db, channel_id, text, scheduled_at, media_type, media_file_id
        )
        return post

    def stop(self):
        self.scheduler.shutdown(wait=False)
        logger.info('Scheduler service stopped')
