import asyncio
import logging

logger = logging.getLogger(__name__)


async def _fetch_all_pending_requests_scheduler(application, chat_id, limit=500):
    """Fetch pending join requests using Telethon (scheduler context, no 'context' object)."""
    telethon = application.bot_data.get('telethon')
    if not telethon or not telethon.available:
        return []
    try:
        requests = await telethon.get_pending_join_requests(chat_id, limit=limit)
        return requests or []
    except Exception as e:
        logger.warning(f'Scheduler: error fetching pending requests for {chat_id}: {e}')
        return []


class SchedulerService:
    def __init__(self, application):
        self.application = application
        self.running = False
        self.task = None
        self._sync_running = False

    async def start(self):
        if self.running:
            return
        self.running = True
        self.task = asyncio.create_task(self._run_loop())
        logger.info('Scheduler started')

    async def stop(self):
        self.running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        logger.info('Scheduler stopped')

    async def _run_loop(self):
        cycle = 0
        while self.running:
            try:
                await self._process_drip_channels()
            except Exception as e:
                logger.exception(f"Drip scheduler error: {e}")
            # Every 5 minutes, process force sub timeouts
            if cycle % 5 == 0:
                try:
                    await self._process_force_sub_timeouts()
                except Exception as e:
                    logger.exception(f"Force sub timeout error: {e}")

            if cycle % 10 == 0 and not self._sync_running:
                asyncio.create_task(self._guarded_sync_pending_counts())

            cycle += 1
            await asyncio.sleep(60)

    async def _guarded_sync_pending_counts(self):
        """Run sync in background with timeout so it never blocks the main loop."""
        if self._sync_running:
            return
        self._sync_running = True
        try:
            await asyncio.wait_for(self._sync_pending_counts(), timeout=180)
        except asyncio.TimeoutError:
            logger.warning("Pending sync timed out after 180s")
        except Exception as e:
            logger.exception(f"Pending sync error: {e}")
        finally:
            self._sync_running = False

    async def _sync_pending_counts(self):
        """Sync pending request counts between Telegram and DB, importing untracked requests."""
        db = self.application.bot_data.get('db')
        if not db:
            return
        channels = await db.get_all_channels()
        if not channels:
            return
        for ch in channels:
            if not self.running:
                break
            chat_id = ch['chat_id']
            try:
                from handlers.channel_detection import get_telegram_pending_count
                telegram_pending = await get_telegram_pending_count(self.application.bot.token, chat_id)
                db_pending = await db.get_pending_count(chat_id)

                if telegram_pending > db_pending and telegram_pending > 0:
                    logger.info(f"Channel {chat_id}: {telegram_pending} Telegram pending vs {db_pending} in DB — importing untracked")
                    try:
                        pending_users = await _fetch_all_pending_requests_scheduler(self.application, chat_id, limit=500)
                        imported = 0
                        for req in pending_users:
                            req_user_id = req.get('user_id')
                            if not req_user_id:
                                continue
                            try:
                                await db.save_join_request(
                                    user_id=req_user_id,
                                    chat_id=chat_id,
                                    username=req.get('username'),
                                    first_name=req.get('first_name'),
                                    user_language=req.get('language_code'),
                                )
                                await db.upsert_end_user(
                                    user_id=req_user_id,
                                    username=req.get('username'),
                                    first_name=req.get('first_name'),
                                    source='scheduler_import',
                                    source_channel=chat_id,
                                )
                                imported += 1
                            except Exception:
                                pass
                        if imported > 0:
                            logger.info(f"Scheduler imported {imported} untracked requests for {chat_id}")
                    except Exception as e:
                        logger.error(f"Error importing untracked requests for {chat_id}: {e}")

                db_pending = await db.get_pending_count(chat_id)
                await db.update_channel_setting(chat_id, 'pending_requests', db_pending)
            except Exception as e:
                if 'chat not found' in str(e).lower() or 'bot was kicked' in str(e).lower():
                    logger.warning(f"Cannot access channel {chat_id}: {e}")
                else:
                    logger.debug(f"Sync error for {chat_id}: {e}")

    async def _process_force_sub_timeouts(self):
        """Auto-approve users whose force sub timeout has expired."""
        db = self.application.bot_data.get('db')
        if not db:
            return
        channels = await db.get_all_channels()
        if not channels:
            return
        for ch in channels:
            if not ch.get('force_subscribe_enabled'):
                continue
            timeout_hours = ch.get('force_sub_timeout', 0)
            if timeout_hours <= 0:
                continue
            chat_id = ch['chat_id']
            try:
                expired = await db.get_expired_force_sub_requests(chat_id=chat_id, hours=timeout_hours)
                if not expired:
                    continue
                approved_count = 0
                for req in expired:
                    try:
                        await self.application.bot.approve_chat_join_request(
                            chat_id=chat_id, user_id=req['user_id']
                        )
                        await db.update_join_request_after_approve(
                            req['user_id'], chat_id,
                            dm_sent=False, processed_by='force_sub_timeout'
                        )
                        approved_count += 1
                        logger.info(f'Force sub timeout: approved {req["user_id"]} in {chat_id} after {timeout_hours}h')
                    except Exception as e:
                        if 'user_already_participant' in str(e).lower() or 'hide_requester_missing' in str(e).lower():
                            try:
                                await db.update_join_request_after_approve(
                                    req['user_id'], chat_id,
                                    dm_sent=False, processed_by='force_sub_timeout_stale'
                                )
                            except Exception:
                                pass
                        else:
                            logger.warning(f'Force sub timeout approve failed for {req["user_id"]} in {chat_id}: {e}')
                if approved_count > 0:
                    logger.info(f'Force sub timeout: approved {approved_count} users in {chat_id}')
            except Exception as e:
                logger.exception(f'Force sub timeout error for {chat_id}: {e}')

    async def _process_drip_channels(self):
        """Process channels with drip mode - approve in batches."""
        db = self.application.bot_data.get('db')
        if not db:
            return
        try:
            channels = await db.get_drip_channels()
        except Exception:
            return
        if not channels:
            return
        for ch in channels:
            chat_id = ch['chat_id']
            batch_size = ch.get('drip_rate', 5)
            try:
                pending = await db.get_drip_batch(chat_id, batch_size)
                if not pending:
                    continue
                for req in pending:
                    try:
                        await self.application.bot.approve_chat_join_request(
                            chat_id=chat_id, user_id=req['user_id']
                        )
                        await db.update_join_request_after_approve(
                            req['user_id'], chat_id,
                            dm_sent=False, processed_by='drip'
                        )
                        logger.info(f'Drip approved {req["user_id"]} in {chat_id}')
                    except Exception as e:
                        logger.warning(f'Drip approve failed for {req["user_id"]} in {chat_id}: {e}')
            except Exception as e:
                logger.exception(f'Drip processing error for {chat_id}: {e}')
