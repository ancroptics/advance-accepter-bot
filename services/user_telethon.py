import asyncio
import logging

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError
from telethon.sessions import StringSession
from telethon.tl.functions.messages import GetChatInviteImportersRequest
from telethon.tl.types import InputUser

import config

logger = logging.getLogger(__name__)


def configured():
    return bool(config.TELETHON_API_ID and config.TELETHON_API_HASH)


def _client(session_string=''):
    return TelegramClient(
        StringSession(session_string or ''),
        int(config.TELETHON_API_ID),
        config.TELETHON_API_HASH,
    )


async def send_login_code(phone):
    client = _client()
    await client.connect()
    try:
        sent = await client.send_code_request(phone)
        return client.session.save(), sent.phone_code_hash
    finally:
        await client.disconnect()


async def complete_login(temp_session, phone, code_hash, code):
    client = _client(temp_session)
    await client.connect()
    try:
        try:
            await client.sign_in(phone=phone, code=code, phone_code_hash=code_hash)
        except SessionPasswordNeededError:
            return {'needs_password': True, 'temp_session': client.session.save()}
        return {'session': client.session.save()}
    finally:
        await client.disconnect()


async def complete_password(temp_session, password):
    client = _client(temp_session)
    await client.connect()
    try:
        await client.sign_in(password=password)
        return client.session.save()
    finally:
        await client.disconnect()


async def get_pending_join_requests(session_string, chat_id, limit=50000):
    client = _client(session_string)
    await client.connect()
    try:
        if not await client.is_user_authorized():
            raise RuntimeError('Telegram session is not authorized')
        entity = await client.get_entity(chat_id)
        all_requests = []
        offset_date = 0
        offset_user = InputUser(user_id=0, access_hash=0)

        while len(all_requests) < limit:
            batch_limit = min(limit - len(all_requests), 100)
            result = await client(GetChatInviteImportersRequest(
                peer=entity,
                requested=True,
                limit=batch_limit,
                offset_date=offset_date,
                offset_user=offset_user,
            ))
            if not result.importers:
                break

            users_by_id = {u.id: u for u in result.users}
            for importer in result.importers:
                user = users_by_id.get(importer.user_id)
                all_requests.append({
                    'user_id': importer.user_id,
                    'first_name': user.first_name if user else 'Unknown',
                    'last_name': user.last_name if user else None,
                    'username': user.username if user else None,
                    'date': importer.date,
                })

            if len(result.importers) < batch_limit:
                break
            last_importer = result.importers[-1]
            offset_date = last_importer.date
            last_user = users_by_id.get(last_importer.user_id)
            if not last_user:
                break
            offset_user = InputUser(user_id=last_user.id, access_hash=last_user.access_hash)
            if len(all_requests) % 5000 == 0:
                await asyncio.sleep(2)

        return all_requests
    finally:
        await client.disconnect()
