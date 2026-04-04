import logging
import asyncio
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler

logger = logging.getLogger(__name__)


class SchedulerService:
    def __init__(self, application):
        self.application = application
        self.scheduler = AsyncIOScheduler()

    def start(self):
        """Start the scheduler with periodic jobs."""
        try:
            # Auto-approve force sub requests after 24 hours
            self.scheduler.add_job(
                self._auto_approve_expired_force_sub,
                'interval',
                hours=1,
                id='force_sub_auto_approve',
                next_run_time=datetime.now() + timedelta(minutes=5),
            )
            # Sync pending requests from Telegram every 6 hours
            self.scheduler.add_job(
                self._sync_pending_from_telegram,
                'interval',
                hours=6,
                id='sync_pending_requests',
                next_run_time=datetime.now() + timedelta(minutes=10),
            )
            self.scheduler.start()
            logger.info('Scheduler service started with force_sub_auto_approve and sync_pending jobs')
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

    async def _auto_approve_expired_force_sub(self):
        """Auto-approve join requests where force sub was required but 24h has passed."""
        try:
            db = self.application.bot_data.get('db')
            if not db:
                return

            # Find all pending requests with force_sub_required=TRUE that are older than 24h
            expired = await db.get_expired_force_sub_requests(hours=24)
            if not expired:
                return

            logger.info(f'Auto-approving {len(expired)} expired force sub requests')
            bot = self.application.bot

            for req in expired:
                try:
                    user_id = req['user_id']
                    chat_id = req['chat_id']

                    # Try to approve the join request on Telegram
                    try:
                        await bot.approve_chat_join_request(chat_id, user_id)
                    except Exception as e:
                        err = str(e).lower()
                        if 'hide_requester_missing' in err or 'user_already_participant' in err:
                            # Already joined or request expired on Telegram side
                            pass
                        else:
                            logger.warning(f'Could not approve expired force sub for {user_id} in {chat_id}: {e}')

                    # Update DB status
                    await db.update_join_request_after_approve(
                        user_id=user_id,
                        chat_id=chat_id,
                        dm_sent=False,
                        processed_by='force_sub_expired_24h',
                    )

                    # Try to send welcome DM
                    channel = await db.get_channel(chat_id)
                    if channel and channel.get('welcome_dm_enabled', True):
                        try:
                            welcome_text = channel.get('welcome_message', 'Welcome! \U0001f389')
                            first_name = req.get('first_name', 'there')
                            welcome_text = welcome_text.replace('{first_name}', first_name or 'there')
                            welcome_text = welcome_text.replace('{channel_name}', channel.get('chat_title', ''))
                            welcome_text = welcome_text.replace('{user_id}', str(user_id))
                            await bot.send_message(user_id, welcome_text)
                        except Exception:
                            pass  # DM may fail if user blocked bot

                    await asyncio.sleep(0.5)  # Rate limit
                except Exception as e:
                    logger.error(f'Error auto-approving expired force sub: {e}')

        except Exception as e:
            logger.error(f'Error in _auto_approve_expired_force_sub: {e}')

    async def _sync_pending_from_telegram(self):
        """Sync pending join requests from Telegram API into our database.
        This catches requests made before the bot became admin."""
        try:
            db = self.application.bot_data.get('db')
            if not db:
                return

            bot = self.application.bot
            channels = await db.get_all_active_channels()
            if not channels:
                return

            total_synced = 0
            for channel in channels:
                chat_id = channel['chat_id']
                try:
                    # Use raw API call to get pending join requests
                    # python-telegram-bot doesn't have a built-in method for this
                    import aiohttp
                    url = f'https://api.telegram.org/bot{bot.token}/getChatJoinRequests'
                    async with aiohttp.ClientSession() as session:
                        async with session.post(url, json={'chat_id': chat_id, 'limit': 100}, timeout=aiohttp.ClientTimeout(total=30)) as response:
                            data = await response.json()

                    if not data.get('ok') or not data.get('result'):
                        continue

                    for req in data['result']:
                        user = req.get('user', {})
                        user_id = user.get('id')
                        if not user_id:
                            continue

                        # Try to save - will update if exists (UPSERT)
                        try:
                            await db.save_join_request(
                                user_id=user_id,
                                chat_id=chat_id,
                                username=user.get('username'),
                                first_name=user.get('first_name'),
                                user_language=user.get('language_code'),
                            )
                            total_synced += 1
                        except Exception as e:
                            logger.debug(f'Error syncing request {user_id} for {chat_id}: {e}')

                    # Update pending count
                    pending_count = await db.get_pending_count(chat_id)
                    await db.update_channel_setting(chat_id, 'pending_requests', pending_count)

                    await asyncio.sleep(1)  # Rate limit between channels
                except Exception as e:
                    if 'chat_admin_required' not in str(e).lower():
                        logger.warning(f'Error syncing pending for {chat_id}: {e}')

            if total_synced > 0:
                logger.info(f'Synced {total_synced} pending requests from Telegram')

        except Exception as e:
            logger.error(f'Error in _sync_pending_from_telegram: {e}')
