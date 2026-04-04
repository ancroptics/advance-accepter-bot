import logging
import asyncio
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler

logger = logging.getLogger(__name__)


class SchedulerService:
    def __init__(self):
        self.scheduler = AsyncIOScheduler(timezone='Asia/Kolkata')
        self.db = None
        self.bot = None
        self.clone_manager = None

    def setup(self, db, bot, clone_manager=None):
        self.db = db
        self.bot = bot
        self.clone_manager = clone_manager

        # Drip approve - every minute
        self.scheduler.add_job(
            self.drip_approve_job, 'interval', minutes=1,
            id='drip_approve', replace_existing=True, max_instances=1
        )
        # Auto post - every minute
        self.scheduler.add_job(
            self.auto_post_job, 'interval', minutes=1,
            id='auto_post', replace_existing=True, max_instances=1
        )
        # Scheduled broadcasts - every minute
        self.scheduler.add_job(
            self.scheduled_broadcast_job, 'interval', minutes=1,
            id='scheduled_broadcast', replace_existing=True, max_instances=1
        )
        # Premium expiry - every hour
        self.scheduler.add_job(
            self.premium_expiry_check, 'interval', hours=1,
            id='premium_expiry', replace_existing=True, max_instances=1
        )
        # Clone health - every 5 minutes
        self.scheduler.add_job(
            self.clone_health_check, 'interval', minutes=5,
            id='clone_health', replace_existing=True, max_instances=1
        )
        # Daily stats aggregation - midnight
        self.scheduler.add_job(
            self.daily_stats_aggregation, 'cron', hour=0, minute=5,
            id='daily_stats', replace_existing=True, max_instances=1
        )
        # Cleanup old analytics - daily at 3am
        self.scheduler.add_job(
            self.cleanup_old_analytics, 'cron', hour=3,
            id='cleanup_analytics', replace_existing=True, max_instances=1
        )

    def start(self):
        self.scheduler.start()
        logger.info('Scheduler started with all jobs')

    def shutdown(self):
        self.scheduler.shutdown()

    async def drip_approve_job(self):
        try:
            channels = await self.db.get_drip_channels()
            now = datetime.now()
            for ch in (channels or []):
                hour = now.hour
                if hour < ch.get('drip_active_start', 8) or hour >= ch.get('drip_active_end', 23):
                    continue
                rate = ch.get('drip_rate', 50)
                pending = await self.db.get_pending_requests(ch['chat_id'], limit=rate)
                for req in pending:
                    try:
                        # Try DM
                        if ch.get('welcome_dm_enabled'):
                            try:
                                text = ch.get('welcome_message', 'Welcome!')
                                text = text.replace('{first_name}', req.get('first_name', 'there'))
                                text = text.replace('{channel_name}', ch.get('chat_title', ''))
                                await self.bot.send_message(req['user_id'], text)
                            except Exception:
                                pass
                        await self.bot.approve_chat_join_request(ch['chat_id'], req['user_id'])
                        await self.db.update_join_request_status(req['user_id'], ch['chat_id'], 'approved', 'drip')
                    except Exception as e:
                        logger.error(f'Drip approve error: {e}')
                    await asyncio.sleep(0.5)
        except Exception as e:
            logger.error(f'Drip approve job error: {e}')

    async def auto_post_job(self):
        try:
            now = datetime.now()
            schedules = await self.db.get_due_auto_posts(now)
            for sched in (schedules or []):
                hour = now.hour
                if hour < sched.get('active_hours_start', 8) or hour >= sched.get('active_hours_end', 23):
                    continue
                try:
                    content = sched.get('content', '')
                    if sched.get('media_file_id'):
                        ct = sched.get('content_type', 'photo')
                        if ct == 'photo':
                            await self.bot.send_photo(sched['group_chat_id'], sched['media_file_id'], caption=sched.get('caption', ''))
                        elif ct == 'video':
                            await self.bot.send_video(sched['group_chat_id'], sched['media_file_id'], caption=sched.get('caption', ''))
                        else:
                            await self.bot.send_document(sched['group_chat_id'], sched['media_file_id'], caption=sched.get('caption', ''))
                    else:
                        await self.bot.send_message(sched['group_chat_id'], content)
                    await self.db.update_auto_post_after_send(sched['schedule_id'])
                except Exception as e:
                    logger.error(f'Auto post error for schedule {sched["schedule_id"]}: {e}')
        except Exception as e:
            logger.error(f'Auto post job error: {e}')

    async def scheduled_broadcast_job(self):
        try:
            broadcasts = await self.db.get_due_broadcasts()
            for bc in (broadcasts or []):
                try:
                    users = []
                    if bc.get('target_segment') == 'all':
                        users = await self.db.get_owner_users(bc['owner_id'])
                    elif bc.get('target_segment', '').startswith('channel:'):
                        ch_id = int(bc['target_segment'].split(':')[1])
                        users = await self.db.get_channel_users(ch_id)
                    sent = 0
                    failed = 0
                    blocked = 0
                    await self.db.update_broadcast_started(bc['broadcast_id'])
                    for user in users:
                        try:
                            if bc['content_type'] == 'text':
                                await self.bot.send_message(user['user_id'], bc['content'])
                            elif bc['content_type'] == 'photo':
                                await self.bot.send_photo(user['user_id'], bc['media_file_id'], caption=bc.get('caption', ''))
                            sent += 1
                        except Exception as e:
                            if 'forbidden' in str(e).lower() or 'blocked' in str(e).lower():
                                blocked += 1
                            else:
                                failed += 1
                        await asyncio.sleep(0.04)
                    await self.db.update_broadcast_status(bc['broadcast_id'], 'completed', sent, failed, blocked)
                except Exception as e:
                    logger.error(f'Scheduled broadcast error: {e}')
        except Exception as e:
            logger.error(f'Scheduled broadcast job error: {e}')

    async def premium_expiry_check(self):
        try:
            expired = await self.db.get_expired_premiums()
            for owner in (expired or []):
                await self.db.deactivate_premium(owner['user_id'])
                try:
                    await self.bot.send_message(
                        owner['user_id'],
                        '\u26a0\ufe0f Your premium plan has expired.\n'
                        'You\'ve been downgraded to the free tier.\n\n'
                        'Upgrade again to restore premium features!'
                    )
                except Exception:
                    pass
        except Exception as e:
            logger.error(f'Premium expiry check error: {e}')

    async def clone_health_check(self):
        if self.clone_manager:
            try:
                await self.clone_manager.health_check_clones(self.db)
            except Exception as e:
                logger.error(f'Clone health check error: {e}')

    async def daily_stats_aggregation(self):
        try:
            await self.db.aggregate_daily_stats()
            await self.db.update_platform_stats()
        except Exception as e:
            logger.error(f'Daily stats aggregation error: {e}')

    async def cleanup_old_analytics(self):
        try:
            cutoff = datetime.now() - timedelta(days=90)
            await self.db.cleanup_old_events(cutoff)
        except Exception as e:
            logger.error(f'Cleanup error: {e}')
