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
        old_status, new_status = extract_status_change(update.my_chat_member)
        if old_status is None and new_status is None:
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
