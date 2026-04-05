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
            # Every 5 minutes, sync pending counts with Telegram
            if cycle % 5 == 0:
                try:
                    await self._sync_pending_counts()
                except Exception as e:
                    logger.exception(f"Pending sync error: {e}")
            cycle += 1
            await asyncio.sleep(60)

    async def _sync_pending_counts(self):
        """Sync pending request counts between Telegram and DB.
        Detects old/untracked pending requests and creates placeholder records."""
        db = self.application.bot_data.get('db')
        if not db:
            return
        channels = await db.get_all_channels()
        if not channels:
            return
        for ch in channels:
            chat_id = ch['chat_id']
            try:
                chat_info = await self.application.bot.get_chat(chat_id)
                telegram_pending = getattr(chat_info, 'pending_join_request_count', 0) or 0
                db_pending = await db.get_pending_count(chat_id)
                # Update the stored count to match Telegram reality
                if telegram_pending != ch.get('pending_requests', 0):
                    await db.update_channel_setting(chat_id, 'pending_requests', telegram_pending)
                # If Telegram has more pending than DB, there are untracked old requests
                if telegram_pending > db_pending and telegram_pending > 0:
                    logger.info(f"Channel {chat_id}: {telegram_pending} Telegram pending vs {db_pending} in DB - {telegram_pending - db_pending} untracked")
            except Exception as e:
                if 'chat not found' in str(e).lower() or 'bot was kicked' in str(e).lower():
                    logger.warning(f"Cannot access channel {chat_id}: {e}")
                else:
                    logger.debug(f"Sync error for {chat_id}: {e}")

    async def _process_drip_channels(self):
        """Process channels with drip mode - approve in batches."""
        db = self.application.bot_data.get('db')
        if not db:
            return
        channels = await db.get_drip_channels()
        if not channels:
            return
        for ch in channels:
            chat_id = ch['chat_id']
            batch_size = ch.get('drip_batch_size', 5)
            try:
                pending = await db.get_drip_batch(chat_id, batch_size)
                if not pending:
                    continue
                for req in pending:
                    try:
                        await self.application.bot.approve_chat_join_request(
                            chat_id=chat_id, user_id=req['user_id']
                        )
                        await db.update_join_request_status(
                            req['user_id'], chat_id, 'approved', 'processed_by=''drip'''
                        )
                        logger.info(f'Drip approved {req["user_id"]} in {chat_id}')
                    except Exception as e:
                        logger.warning(f'Drip approve failed for {req["user_id"]} in {chat_id}: {e}')
            except Exception as e:
                logger.exception(f'Drip processing error for {chat_id}: {e}')