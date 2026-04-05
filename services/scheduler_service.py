import logging
import asyncio
from datetime import datetime

logger = logging.getLogger(__name__)

class SchedulerService:
    """Handles scheduled/drip approval of pending join requests."""

    def __init__(self, application):
        self.application = application
        self.running = False
        self._task = None

    async def start(self):
        if self.running:
            return
        self.running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("Drip scheduler started")

    async def stop(self):
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Drip scheduler stopped")

    def schedule_drip(self, chat_id, application):
        """Placeholder for explicit drip scheduling. The main loop handles all drip channels."""
        logger.info(f"Drip mode activated for {chat_id} - will be picked up by scheduler loop")

    async def _run_loop(self):
        while self.running:
            try:
                await self._process_drip_channels()
            except Exception as e:
                logger.exception(f"Drip scheduler error: {e}")
            await asyncio.sleep(60)

    async def _process_drip_channels(self):
        db = self.application.bot_data.get('db')
        if not db:
            return

        channels = await db.get_drip_channels()
        for ch in channels:
            chat_id = ch['chat_id']
            actual_pending = ch.get('actual_pending', 0)
            if actual_pending <= 0:
                continue

            drip_quantity = ch.get('drip_quantity') or ch.get('drip_rate') or 50
            drip_interval = ch.get('drip_interval') or 30

            batch = await db.get_drip_batch(chat_id, drip_quantity)
            if not batch:
                continue

            approved = 0
            dm_sent = 0
            dm_failed = 0

            for req in batch:
                user_id = req['user_id']
                try:
                    if ch.get('welcome_dm_enabled') and ch.get('welcome_message'):
                        try:
                            welcome_text = ch['welcome_message']
                            welcome_text = welcome_text.replace('{first_name}', req.get('first_name', 'there'))
                            welcome_text = welcome_text.replace('{name}', req.get('first_name', 'there'))
                            welcome_text = welcome_text.replace('{channel_name}', ch.get('chat_title', ''))
                            welcome_text = welcome_text.replace('{channel}', ch.get('chat_title', ''))
                            welcome_text = welcome_text.replace('{username}', f"@{req.get('username', 'user')}")
                            await self.application.bot.send_message(chat_id=user_id, text=welcome_text)
                            dm_sent += 1
                        except Exception:
                            dm_failed += 1

                    await self.application.bot.approve_chat_join_request(chat_id=chat_id, user_id=user_id)
                    await db.update_join_request_status(user_id, chat_id, 'approved', 'drip')
                    approved += 1
                except Exception as e:
                    logger.warning(f"Drip approve failed for {user_id} in {chat_id}: {e}")
                    try:
                        await db.update_join_request_status(user_id, chat_id, 'failed', 'drip')
                    except Exception:
                        pass

                await asyncio.sleep(0.3)

            if approved > 0:
                new_pending = await db.get_pending_count(chat_id)
                await db.update_channel_setting(chat_id, 'pending_requests', new_pending)
                await db.update_channel_stats_after_batch(chat_id, approved, dm_sent, dm_failed)
                logger.info(f"Drip: approved {approved} in {chat_id}, remaining {new_pending}")

                try:
                    owner_id = ch.get('owner_id')
                    if owner_id:
                        await self.application.bot.send_message(
                            owner_id,
                            f'\xf0\x9f\x92\xa7 Drip batch complete for {ch["chat_title"]}\n'
                            f'Approved: {approved} | Failed: {len(batch) - approved}\n'
                            f'DMs: {dm_sent} sent, {dm_failed} failed\n'
                            f'Remaining: {new_pending:,}'
                        )
                except Exception:
                    pass
