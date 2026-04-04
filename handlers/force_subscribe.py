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
        [InlineKeyboardButton('\u2795 Add Channel', callback_data=f'add_force_sub_ch:{chat_id}')],
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

force_subscribe_conv_handler = None

FORCE_SUB_INPUT = 100  # conversation state

async def handle_force_sub_channel_input(update, context):
    """Handle channel username/ID input for force subscribe setup."""
    text = update.message.text.strip()
    db = context.application.bot_data.get('db')
    chat_id = context.user_data.get('force_sub_target_channel')
    
    if not chat_id:
        await update.message.reply_text('\u274c Session expired. Please try again from channel settings.')
        return ConversationHandler.END
    
    try:
        # Try to resolve the channel
        if text.startswith('@'):
            channel_username = text
        elif text.startswith('-100'):
            channel_username = int(text)
        elif text.isdigit():
            channel_username = int('-100' + text)
        else:
            channel_username = '@' + text
        
        # Verify bot can access the channel
        try:
            chat_info = await context.bot.get_chat(channel_username)
        except Exception:
            await update.message.reply_text(
                '\u274c Could not find that channel. Make sure:\n'
                '1. The channel/group exists\n'
                '2. The bot is a member of that channel\n'
                '3. You entered the correct username or ID\n\n'
                'Send the channel username (e.g. @mychannel) or /cancel'
            )
            return FORCE_SUB_INPUT
        
        # Get current force sub channels
        channel = await db.get_channel(chat_id)
        current_channels = channel.get('force_subscribe_channels') or []
        
        # Check if already added
        for ch in current_channels:
            if ch.get('chat_id') == chat_info.id:
                await update.message.reply_text(f'\u26a0\ufe0f {chat_info.title} is already in the force subscribe list!')
                return ConversationHandler.END
        
        # Add the new channel
        new_entry = {
            'chat_id': chat_info.id,
            'title': chat_info.title,
            'username': chat_info.username or '',
        }
        current_channels.append(new_entry)
        
        import json
        await db.update_channel_setting(chat_id, 'force_subscribe_channels', json.dumps(current_channels))
        
        # Also enable force subscribe if not already
        if not channel.get('force_subscribe_enabled'):
            await db.update_channel_setting(chat_id, 'force_subscribe_enabled', True)
        
        await update.message.reply_text(
            f'\u2705 Added {chat_info.title} to force subscribe list!\n\n'
            f'Users will now need to join {chat_info.title} before their request is approved.\n\n'
            'Use /dashboard to manage settings.'
        )
        return ConversationHandler.END
        
    except Exception as e:
        logger.error(f'Error in force sub channel input: {e}')
        await update.message.reply_text(f'\u274c Error: {e}\nPlease try again or /cancel')
        return FORCE_SUB_INPUT

async def start_add_force_sub_channel(update, context, chat_id):
    """Start the conversation to add a force sub channel."""
    query = update.callback_query
    context.user_data['force_sub_target_channel'] = chat_id
    await query.edit_message_text(
        '\U0001f512 ADD FORCE SUBSCRIBE CHANNEL\n\n'
        'Send the channel username or ID that users must join:\n\n'
        'Examples:\n'
        '\u2022 @mychannel\n'
        '\u2022 -1001234567890\n\n'
        'Send /cancel to abort.'
    )
    return FORCE_SUB_INPUT
