import logging
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

logger = logging.getLogger(__name__)


async def show_force_sub_menu(update, context, chat_id):
    query = update.callback_query
    db = context.application.bot_data.get('db')
    channel = await db.get_channel(chat_id)
    if not channel:
        return
    enabled = channel.get('force_subscribe_enabled', False)
    channels = channel.get('force_subscribe_channels') or []
    timeout = channel.get('force_subscribe_timeout_hours', 24)
    status = '\U0001f7e2 Enabled' if enabled else '\U0001f534 Disabled'
    text = f'\U0001f512 FORCE SUBSCRIBE\n\nStatus: {status}\n\nRequired Channels:\n'
    if channels:
        for i, ch in enumerate(channels, 1):
            text += f"{i}. {ch.get('title', 'Unknown')} \u2705\n"
    else:
        text += 'None configured\n'
    text += f'\nTimeout: {timeout} hours\n(Auto-approve after timeout even if not joined)'
    toggle_text = '\U0001f534 Disable' if enabled else '\U0001f7e2 Enable'
    buttons = [
        [InlineKeyboardButton(toggle_text, callback_data=f'toggle_force_sub:{chat_id}')],
        [InlineKeyboardButton('\u2795 Add Channel', callback_data=f'add_force_sub:{chat_id}')],
        [InlineKeyboardButton('\u2796 Remove Channel', callback_data=f'remove_force_sub:{chat_id}')],
        [InlineKeyboardButton('\U0001f519 Back', callback_data=f'manage_channel:{chat_id}')]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))


async def verify_force_subscribe(update, context, chat_id):
    query = update.callback_query
    user_id = query.from_user.id
    db = context.application.bot_data.get('db')
    channel = await db.get_channel(chat_id)
    if not channel:
        return
    required_channels = channel.get('force_subscribe_channels') or []
    all_joined = True
    not_joined = []
    for req_ch in required_channels:
        try:
            member = await context.bot.get_chat_member(req_ch['chat_id'], user_id)
            if member.status in ('left', 'kicked'):
                all_joined = False
                not_joined.append(req_ch)
        except Exception:
            all_joined = False
            not_joined.append(req_ch)
    if all_joined:
        try:
            await context.bot.approve_chat_join_request(chat_id, user_id)
            await db.update_join_request_status(user_id, chat_id, 'approved', 'force_sub')
            await db.update_force_sub_completed(user_id, chat_id)
            await query.edit_message_text(f'\u2705 Verified! You\'ve been approved to join {channel["chat_title"]}!')
        except Exception as e:
            logger.error(f'Error approving after force sub: {e}')
            await query.edit_message_text('\u2705 Verified! You should now have access.')
    else:
        text = '\u274c You haven\'t joined all channels yet. Please join:\n\n'
        buttons = []
        for ch in not_joined:
            text += f"\u2022 {ch.get('title', 'Channel')}\n"
            if ch.get('url'):
                buttons.append([InlineKeyboardButton(f"\U0001f4e2 Join {ch.get('title', '')}", url=ch['url'])])
        buttons.append([InlineKeyboardButton('\u2705 I\'ve Joined \u2014 Verify', callback_data=f'verify_force_sub:{chat_id}')])
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))

async def add_force_sub(update, context, chat_id):
    """Add a force subscribe channel."""
    query = update.callback_query
    context.user_data['adding_force_sub_for'] = chat_id
    context.user_data['awaiting_force_sub_channel'] = True
    await query.edit_message_text(
        '\U0001f4e2 ADD FORCE SUBSCRIBE CHANNEL\n\n'
        'Forward a message from the channel you want to add, '
        'or send the channel username (e.g. @channelname).\n\n'
        'Send /cancel to cancel.',
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('Cancel', callback_data=f'force_sub_setup:{chat_id}')]])
    )


async def remove_force_sub(update, context, chat_id):
    """Remove a force subscribe channel."""
    query = update.callback_query
    db = context.application.bot_data.get('db')
    channel = await db.get_channel(chat_id)
    if not channel:
        return
    channels = channel.get('force_subscribe_channels') or []
    if not channels:
        await query.answer('No channels to remove.', show_alert=True)
        return
    buttons = []
    for ch in channels:
        title = ch.get('title', 'Unknown')
        ch_id = ch.get('chat_id', 0)
        buttons.append([InlineKeyboardButton(f'\u274c {title}', callback_data=f'rm_force_sub:{chat_id}:{ch_id}')])
    buttons.append([InlineKeyboardButton('\U0001f519 Back', callback_data=f'force_sub_setup:{chat_id}')])
    await query.edit_message_text('Select a channel to remove:', reply_markup=InlineKeyboardMarkup(buttons))


async def confirm_remove_force_sub(update, context, chat_id, remove_ch_id):
    """Actually remove a force sub channel."""
    query = update.callback_query
    db = context.application.bot_data.get('db')
    channel = await db.get_channel(chat_id)
    if not channel:
        return
    channels = channel.get('force_subscribe_channels') or []
    new_channels = [ch for ch in channels if ch.get('chat_id') != remove_ch_id]
    await db.update_channel_setting(chat_id, 'force_subscribe_channels', new_channels)
    await query.answer('Channel removed!', show_alert=True)
    await show_force_sub_menu(update, context, chat_id)


force_subscribe_conv_handler = None
