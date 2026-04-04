import asyncio
import logging

logger = logging.getLogger(__name__)


class BroadcastEngine:
    def __init__(self, db, bot):
        self.db = db
        self.bot = bot
        self._running = False

    async def send_broadcast(self, broadcast_id, channel_id, text, media_type=None, media_file_id=None):
        self._running = True
        users = await self.db.get_channel_users(channel_id)
        recipients = [r['user_id'] for r in users]
        total = len(recipients)
        sent = 0
        failed = 0
        blocked = 0

        logger.info(f'Starting broadcast {broadcast_id} to {total} recipients')

        for i, user_id in enumerate(recipients):
            if not self._running:
                logger.info(f'Broadcast {broadcast_id} cancelled')
                break
            try:
                if media_type == 'photo':
                    await self.bot.send_photo(chat_id=user_id, photo=media_file_id, caption=text, parse_mode='HTML')
                elif media_type == 'video':
                    await self.bot.send_video(chat_id=user_id, video=media_file_id, caption=text, parse_mode='HTML')
                else:
                    await self.bot.send_message(chat_id=user_id, text=text, parse_mode='HTML')
                sent += 1
            except Exception as e:
                err = str(e).lower()
                if 'blocked' in err or 'deactivated' in err:
                    blocked += 1
                    await self.db.mark_user_blocked(user_id)
                else:
                    failed += 1
                logger.debug(f'Broadcast to {user_id} failed: {e}')

            if (i + 1) % 30 == 0:
                await asyncio.sleep(1)

            if (i + 1) % 100 == 0:
                await self.db.update_broadcast_status(broadcast_id, 'sending', sent, failed, blocked)

        await self.db.update_broadcast_status(broadcast_id, 'completed', sent, failed, blocked)
        self._running = False
        logger.info(f'Broadcast {broadcast_id} complete: {sent}/{total} sent, {failed} failed, {blocked} blocked')
        return sent, failed

    def cancel(self):
        self._running = False
