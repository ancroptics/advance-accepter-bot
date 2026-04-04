import logging
from telegram import Update, ChatMemberUpdated, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
import config

logger = logging.getLogger(__name__)

def extract_status_change(chat_member_update: ChatMemberUpdated):
    status_change = chat_member_update.difference().get('status')
    if status_change is None:
        return None, None
    old_status, new_status = status_change
    return old_status, new_status

async def channel_detection_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        result = extract_status_change(update.my_chat_member)
        if result is None:
            return
        old_status, new_status = result
        if old_status is None:
            return
        chat = update.my_chat_member.chat
        from_user = update.my_chat_member.from_user
        db = context.application.bot_data.get('db')
        if not db:
            return

        # Bot was ADDED to a channel/group as admin
        if new_status in ('administrator', 'member') and old_status in ('left', 'kicked', None):
            logger.info(f'Bot added to {chat.type} {chat.title} (ID: {chat.id}) by user {from_user.id}')
            # Create/update channel owner
            await db.upsert_owner(
                user_id=from_user.id,
                username=from_user.username,
                first_name=from_user.first_name,
                last_name=from_user.last_name,
            )
            # Create managed channel
            await db.upsert_channel(
                chat_id=chat.id,
                owner_id=from_user.id,
                chat_title=chat.title,
                chat_username=chat.username,
                chat_type=chat.type,
            )
            # Try to get member count
            try:
                count = await context.bot.get_chat_member_count(chat.id)
                await db.update_channel_setting(chat.id, 'member_count', count)
            except Exception:
                pass
            # Scan for existing pending requests that were there before bot was added
            try:
                import asyncio
                asyncio.create_task(process_existing_pending_requests(context, chat.id, from_user.id))
            except Exception as e:
                logger.error(f'Error scheduling existing request scan: {e}')
            # Notify owner
            pending = await db.get_pending_count(chat.id)
            try:
                text = (
                    f'\u2705 Channel Connected!\n'
                    f'\U0001f4e2 {chat.title}\n\n'
                    f'I\'m now managing join requests for this channel.\n\n'
                    f'\U0001f4cb Pending Requests: {pending}\n'
                    f'\u2699\ufe0f Auto-Approve: ON\n'
                )
                buttons = [
                    [InlineKeyboardButton('\u2699\ufe0f Configure Channel', callback_data=f'manage_channel:{chat.id}')],
                    [InlineKeyboardButton('\U0001f4ca View Analytics', callback_data=f'analytics:{chat.id}')],
                    [InlineKeyboardButton('\U0001f4e2 Manage All Channels', callback_data='dashboard')],
                ]
                await context.bot.send_message(from_user.id, text, reply_markup=InlineKeyboardMarkup(buttons))
            except Exception as e:
                logger.warning(f'Could not DM owner {from_user.id}: {e}')
            # Log event
            await db.log_event('channel_connected', owner_id=from_user.id, channel_id=chat.id)

        # Bot was REMOVED from a channel/group
        elif new_status in ('left', 'kicked') and old_status in ('administrator', 'member'):
            logger.info(f'Bot removed from {chat.title} (ID: {chat.id})')
            await db.update_channel_setting(chat.id, 'is_active', False)
            await db.update_channel_setting(chat.id, 'bot_is_admin', False)
            # Try to notify owner
            channel = await db.get_channel(chat.id)
            if channel:
                try:
                    await context.bot.send_message(
                        channel['owner_id'],
                        f'\u26a0\ufe0f Bot was removed from {chat.title}'
                    )
                except Exception:
                    pass
            await db.log_event('channel_disconnected', channel_id=chat.id)
    except Exception as e:
        logger.exception(f'Error in channel_detection_handler: {e}')

async def process_existing_pending_requests(context, chat_id, owner_id):
    """Process join requests that were already pending before bot became admin."""
    db = context.application.bot_data.get('db')
    if not db:
        return
    try:
        pending_users = []
        try:
            response = await context.bot.get_chat_administrators(chat_id)
            logger.info(f'Bot is admin in {chat_id}, checking for pending requests')
        except Exception as e:
            logger.warning(f'Cannot check admins for {chat_id}: {e}')
        
        # Use raw API call to get pending join requests
        try:
            import json
            url = f'https://api.telegram.org/bot{context.bot.token}/getChatJoinRequests'
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json={'chat_id': chat_id}) as resp:
                    data = await resp.json()
                    if data.get('ok'):
                        pending_users = data.get('result', [])
                        logger.info(f'Found {len(pending_users)} existing pending requests in {chat_id}')
                    else:
                        logger.warning(f'getChatJoinRequests failed: {data}')
        except Exception as e:
            logger.error(f'Error fetching existing pending requests: {e}')
            return
        
        # Save and optionally auto-approve each pending request
        channel = await db.get_channel(chat_id)
        auto_approve = channel.get('auto_approve', True) if channel else True
        approve_mode = channel.get('approve_mode', 'instant') if channel else 'instant'
        
        approved_count = 0
        saved_count = 0
        for req in pending_users:
            user = req.get('user', {})
            user_id = user.get('id')
            if not user_id:
                continue
            try:
                await db.save_join_request(
                    user_id=user_id,
                    chat_id=chat_id,
                    username=user.get('username'),
                    first_name=user.get('first_name'),
                    user_language=None,
                )
                saved_count += 1
                
                if auto_approve and approve_mode == 'instant':
                    try:
                        await context.bot.approve_chat_join_request(chat_id, user_id)
                        await db.update_join_request_status(user_id, chat_id, 'approved', 'auto_existing')
                        approved_count += 1
                    except Exception as e:
                        logger.debug(f'Could not approve existing request {user_id}: {e}')
            except Exception as e:
                logger.debug(f'Error processing existing request {user_id}: {e}')
        
        logger.info(f'Processed existing requests in {chat_id}: saved={saved_count}, approved={approved_count}')
        
        if saved_count > 0:
            try:
                await context.bot.send_message(
                    owner_id,
                    f'\U0001f50d Found {saved_count} existing pending requests in your channel!\n'
                    f'\u2705 Auto-approved: {approved_count}\n\n'
                    f'Use /dashboard to manage.'
                )
            except Exception:
                pass
    except Exception as e:
        logger.error(f'Error in process_existing_pending_requests: {e}')
