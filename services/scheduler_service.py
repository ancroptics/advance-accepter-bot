import asyncio
import logging

logger = logging.getLogger(__name__)


class SchedulerService:
    def __init__(self, application):
        self.application = application
        self.running = False
        self.task = None

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
            # Every 5 minutes, sync pending counts and process force sub timeouts
            if cycle % 5 == 0:
                try:
                    await self._sync_pending_counts()
                except Exception as e:
                    logger.exception(f"Pending sync error: {e}")
                try:
                    await self._process_force_sub_timeouts()
                except Exception as e:
                    logger.exception(f"Force sub timeout error: {e}")
            cycle += 1
            await asyncio.sleep(60)

    async def _sync_pending_counts(self):
        """Sync pending request counts between Telegram and DB, importing untracked requests."""
        db = self.application.bot_data.get('db')
        if not db:
            return
        channels = await db.get_all_channels()
        if not channels:
            return
        for ch in channels:
            chat_id = ch['chat_id']
            try:
                # Use raw API to get real pending count
                from handlers.channel_detection import get_telegram_pending_count
                telegram_pending = await get_telegram_pending_count(self.application.bot.token, chat_id)
                db_pending = await db.get_pending_count(chat_id)

                # If Telegram has more pending than DB, log the discrepancy
                # NOTE: We cannot enumerate individual pending requests via Bot API
                # They are captured via chat_join_request updates as they arrive
                if telegram_pending > db_pending and telegram_pending > 0:
                    logger.info(f"Channel {chat_id}: {telegram_pending} Telegram pending vs {db_pending} in DB")

                # Refresh DB count after potential import and update stored value
                db_pending = await db.get_pending_count(chat_id)
                await db.update_channel_setting(chat_id, 'pending_requests', db_pending)
                await db.update_channel_setting(chat_id, 'telegram_pending', telegram_pending)
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
        # Get all channels with force sub enabled and a timeout set
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
                expired = await db.get_expired_force_sub_requests(hours=timeout_hours)
                if not expired:
                    continue
                # Filter to this channel
                channel_expired = [r for r in expired if r['chat_id'] == chat_id]
                for req in channel_expired:
                    try:
                        await self.application.bot.approve_chat_join_request(
                            chat_id=chat_id, user_id=req['user_id']
                        )
                        await db.update_join_request_after_approve(
                            req['user_id'], chat_id,
                            dm_sent=False, processed_by='force_sub_timeout'
                        )
                        logger.info(f'Force sub timeout: approved {req["user_id"]} in {chat_id} after {timeout_hours}h')
                    except Exception as e:
                        logger.warning(f'Force sub timeout approve failed for {req["user_id"]} in {chat_id}: {e}')
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
