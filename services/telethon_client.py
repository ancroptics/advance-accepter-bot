import logging
import os
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.messages import GetChatInviteImportersRequest
from telethon.tl.types import InputPeerChannel

logger = logging.getLogger(__name__)


class TelethonService:
    """Uses Telethon (MTProto) to access Telegram APIs not available to bots."""

    def __init__(self):
        self.api_id = os.getenv('TELETHON_API_ID', '')
        self.api_hash = os.getenv('TELETHON_API_HASH', '')
        self.session_string = os.getenv('TELETHON_SESSION_STRING', '')
        self.client = None
        self.available = bool(self.api_id and self.api_hash and self.session_string)

    async def start(self):
        """Initialize and connect the Telethon client."""
        if not self.available:
            logger.info('Telethon not configured (missing TELETHON_API_ID/API_HASH/SESSION_STRING)')
            return False
        try:
            self.client = TelegramClient(
                StringSession(self.session_string),
                int(self.api_id),
                self.api_hash
            )
            await self.client.connect()
            if not await self.client.is_user_authorized():
                logger.error('Telethon session is not authorized. Please regenerate the session string.')
                self.available = False
                return False
            me = await self.client.get_me()
            logger.info(f'Telethon connected as {me.first_name} (ID: {me.id})')
            return True
        except Exception as e:
            logger.exception(f'Telethon start failed: {e}')
            self.available = False
            return False

    async def stop(self):
        """Disconnect the Telethon client."""
        if self.client:
            await self.client.disconnect()

    async def get_pending_join_requests(self, chat_id, limit=200):
        """Fetch all pending join requests for a channel/group using MTProto API.

        Returns list of dicts: [{user_id, first_name, username, date}, ...]
        """
        if not self.available or not self.client:
            return None

        try:
            entity = await self.client.get_entity(chat_id)

            all_requests = []
            offset_user = None
            offset_date = None

            while True:
                kwargs = {
                    'peer': entity,
                    'requested': True,
                    'limit': min(limit - len(all_requests), 100),
                }
                if offset_date:
                    kwargs['offset_date'] = offset_date
                if offset_user:
                    kwargs['offset_user'] = offset_user
                else:
                    from telethon.tl.types import InputUser
                    kwargs['offset_user'] = InputUser(user_id=0, access_hash=0)
                    kwargs['offset_date'] = 0

                result = await self.client(GetChatInviteImportersRequest(**kwargs))

                if not result.importers:
                    break

                for imp in result.importers:
                    user = next((u for u in result.users if u.id == imp.user_id), None)
                    all_requests.append({
                        'user_id': imp.user_id,
                        'first_name': user.first_name if user else 'Unknown',
                        'username': user.username if user else None,
                        'date': imp.date,
                    })

                if len(all_requests) >= limit or len(result.importers) < kwargs['limit']:
                    break

                # Set offset for next page
                last_imp = result.importers[-1]
                offset_date = last_imp.date
                last_user = next((u for u in result.users if u.id == last_imp.user_id), None)
                if last_user:
                    offset_user = InputUser(user_id=last_user.id, access_hash=last_user.access_hash)
                else:
                    break

            logger.info(f'Fetched {len(all_requests)} pending join requests for {chat_id}')
            return all_requests

        except Exception as e:
            logger.exception(f'Error fetching join requests for {chat_id}: {e}')
            return None
