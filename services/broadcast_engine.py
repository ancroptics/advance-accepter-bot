import logging
import asyncio
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

logger = logging.getLogger(__name__)


class BroadcastEngine:
    def __init__(self, db, bot):
        self.db = db
        self.bot = bot
        self.active_broadcasts = {}  # broadcast_id -> {cancel: False}
        self.rate = 25  # messages per second

    async def execute_broadcast(self, broadcast_id, users, content, progress_callback=None):
        self.active_broadcasts[broadcast_id] = {'cancel': False}
        sent = 0
        failed = 0
        blocked = 0
        total = len(users)
        await self.db.update_broadcast_started(broadcast_id)

        for i, user in enumerate(users):
            if self.active_broadcasts.get(broadcast_id, {}).get('cancel'):
                break
            uid = user['user_id']
            try:
                await self._send_content(uid, content)
                sent += 1
            except Exception as e:
                err = str(e).lower()
                if 'forbidden' in err or 'blocked' in err or 'chat not found' in err:
                    blocked += 1
                    await self.db.mark_user_blocked(uid)
                elif 'retry_after' in err:
                    import re
                    match = re.search(r'retry after (\d+)', err)
                    if match:
                        wait = int(match.group(1))
                        await asyncio.sleep(wait)
                        try:
                            await self._send_content(uid, content)
                            sent += 1
                        except Exception:
                            failed += 1
                else:
                    failed += 1

            if progress_callback and (i + 1) % 25 == 0:
                await progress_callback(i + 1, total, sent, failed, blocked)
            await asyncio.sleep(1.0 / self.rate)

        status = 'cancelled' if self.active_broadcasts.get(broadcast_id, {}).get('cancel') else 'completed'
        await self.db.update_broadcast_status(broadcast_id, status, sent, failed, blocked)
        self.active_broadcasts.pop(broadcast_id, None)
        return sent, failed, blocked

    async def _send_content(self, user_id, content):
        ct = content.get('content_type', 'text')
        reply_markup = None
        if content.get('buttons_json'):
            btns = content['buttons_json']
            rows = [[InlineKeyboardButton(b['text'], url=b['url']) for b in btns]]
            reply_markup = InlineKeyboardMarkup(rows)

        if ct == 'text':
            await self.bot.send_message(user_id, content['content'], reply_markup=reply_markup, parse_mode='HTML')
        elif ct == 'photo':
            await self.bot.send_photo(user_id, content['media_file_id'], caption=content.get('caption', ''), reply_markup=reply_markup)
        elif ct == 'video':
            await self.bot.send_video(user_id, content['media_file_id'], caption=content.get('caption', ''), reply_markup=reply_markup)
        elif ct == 'document':
            await self.bot.send_document(user_id, content['media_file_id'], caption=content.get('caption', ''), reply_markup=reply_markup)
        elif ct == 'animation':
            await self.bot.send_animation(user_id, content['media_file_id'], caption=content.get('caption', ''), reply_markup=reply_markup)

    def cancel_broadcast(self, broadcast_id):
        if broadcast_id in self.active_broadcasts:
            self.active_broadcasts[broadcast_id]['cancel'] = True
