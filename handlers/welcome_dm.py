import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, ConversationHandler, CallbackQueryHandler, MessageHandler, filters
)

logger = logging.getLogger(__name__)

EDITING_WELCOME = 0


async def edit_welcome_start(update, context):
    query = update.callback_query
    await query.answer()
    data = query.data
    if ':' in data:
        chat_id = int(data.split(':')[1])
    else:
        chat_id = context.user_data.get('editing_welcome_for')
    if not chat_id:
        await query.edit_message_text('Error: No channel selected.')
        return ConversationHandler.END
    context.user_data['editing_welcome_for'] = chat_id
    db = context.application.bot_data.get('db')
    channel = await db.get_channel(chat_id)
    current_msg = channel.get('welcome_message', 'Not set') if channel else 'Not set'
    await query.edit_message_text(
        f'Current welcome message:\n\n{current_msg}\n\n'
        f'Send the new welcome message.\n'
        f'Available variables: {{name}}, {{username}}, {{channel}}\n\n'
        f'Send /cancel to cancel.',
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('Cancel', callback_data='cancel_edit_welcome')]])
    )
    return EDITING_WELCOME


async def edit_welcome_receive(update, context):
    chat_id = context.user_data.get('editing_welcome_for')
    if not chat_id:
        await update.message.reply_text('Error: No channel context. Please try again from the channel menu.')
        return ConversationHandler.END
    new_message = update.message.text
    if new_message == '/cancel':
        await update.message.reply_text('Cancelled.',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('Back to Dashboard', callback_data='dashboard')]]))
        return ConversationHandler.END
    db = context.application.bot_data.get('db')
    try:
        await db.update_channel_setting(chat_id, 'welcome_message', new_message)
        await update.message.reply_text(
            f'\u2705 Welcome message updated!\n\nNew message:\n{new_message}',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton('Back to Channel', callback_data=f'manage_channel:{chat_id}')],
                [InlineKeyboardButton('Back to Dashboard', callback_data='dashboard')]
            ])
        )
    except Exception as e:
        logger.error(f'Failed to update welcome message: {e}')
        await update.message.reply_text(
            f'\u274c Failed to update welcome message: {e}',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('Back to Dashboard', callback_data='dashboard')]])
        )
    return ConversationHandler.END


async def cancel_edit_welcome(update, context):
    query = update.callback_query
    await query.answer()
    context.user_data.pop('editing_welcome_for', None)
    await query.edit_message_text('Cancelled.',
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('Back to Dashboard', callback_data='dashboard')]]))
    return ConversationHandler.END


def _extract_chat_id_from_callback(update):
    if update.callback_query and update.callback_query.data:
        data = update.callback_query.data
        if ':' in data:
            try:
                return int(data.split(':')[1])
            except (ValueError, IndexError):
                pass
    return None




async def preview_welcome(update, context, chat_id):
    """Preview the welcome message for a channel."""
    query = update.callback_query
    db = context.application.bot_data.get('db')
    channel = await db.get_channel(chat_id)
    if not channel:
        await query.edit_message_text('Channel not found.')
        return
    welcome_msg = channel.get('welcome_message', '')
    if not welcome_msg:
        welcome_msg = 'Welcome {name}! Thanks for joining {channel}!'
    # Format with sample data
    preview = welcome_msg.replace('{name}', query.from_user.first_name or 'User')
    preview = preview.replace('{username}', query.from_user.username or 'username')
    preview = preview.replace('{channel}', channel.get('chat_title', 'Channel'))
    text = f"\U0001f440 WELCOME MESSAGE PREVIEW\n\n{preview}\n\n(This is how the welcome DM will look)"
    buttons = [
        [InlineKeyboardButton('\u270f\ufe0f Edit Message', callback_data=f'edit_welcome:{chat_id}')],
        [InlineKeyboardButton('\U0001f519 Back', callback_data=f'manage_channel:{chat_id}')],
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))

welcome_dm_conv_handler = ConversationHandler(
    entry_points=[
        CallbackQueryHandler(
            edit_welcome_start,
            pattern=r'^edit_welcome:'
        )
    ],
    states={
        EDITING_WELCOME: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, edit_welcome_receive),
            CallbackQueryHandler(cancel_edit_welcome, pattern='^cancel_edit_welcome$'),
        ],
    },
    fallbacks=[
        CallbackQueryHandler(cancel_edit_welcome, pattern='^cancel_edit_welcome$'),
        MessageHandler(filters.COMMAND, cancel_edit_welcome),
    ],
    per_message=False,
)


WELCOME_CH_INPUT = 200

async def start_add_welcome_channel(update, context, chat_id):
    """Start the conversation to add a welcome channel button."""
    query = update.callback_query
    context.user_data['welcome_ch_target'] = chat_id
    await query.edit_message_text(
        '\U0001f4dd ADD CHANNEL BUTTON\n\n'
        'Send the channel username or ID to add as a button in the welcome DM:\n\n'
        'Examples:\n'
        '\u2022 @mychannel\n'
        '\u2022 -1001234567890\n\n'
        'The channel will appear as a clickable button in welcome messages.\n\n'
        'Send /cancel to abort.'
    )
    return WELCOME_CH_INPUT


async def handle_welcome_channel_input(update, context):
    """Handle channel username/ID input for welcome message buttons."""
    text = update.message.text.strip()
    db = context.application.bot_data.get('db')
    chat_id = context.user_data.get('welcome_ch_target')

    if not chat_id:
        await update.message.reply_text('\u274c Session expired. Please try again from channel settings.')
        return ConversationHandler.END

    if text == '/cancel':
        context.user_data.pop('welcome_ch_target', None)
        await update.message.reply_text(
            'Cancelled.',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('Back', callback_data=f'welcome_settings:{chat_id}')]])
        )
        return ConversationHandler.END

    try:
        import json as _json

        if text.startswith('@'):
            channel_ref = text
        elif text.startswith('-100'):
            channel_ref = int(text)
        elif text.isdigit():
            channel_ref = int('-100' + text)
        else:
            channel_ref = '@' + text

        try:
            chat_info = await context.bot.get_chat(channel_ref)
        except Exception:
            await update.message.reply_text(
                '\u274c Could not find that channel. Make sure:\n'
                '1. The channel/group exists\n'
                '2. The bot is a member of that channel\n'
                '3. You entered the correct username or ID\n\n'
                'Send the channel username (e.g. @mychannel) or /cancel'
            )
            return WELCOME_CH_INPUT

        # Get current welcome buttons
        channel = await db.get_channel(chat_id)
        current_btns_raw = channel.get('welcome_buttons_json') or '[]'
        if isinstance(current_btns_raw, str):
            try:
                current_btns = _json.loads(current_btns_raw)
            except (ValueError, TypeError):
                current_btns = []
        elif isinstance(current_btns_raw, list):
            current_btns = current_btns_raw
        else:
            current_btns = []

        # Check duplicate
        for btn in current_btns:
            if btn.get('chat_id') == chat_info.id:
                await update.message.reply_text(
                    f'\u26a0\ufe0f {chat_info.title} is already in the welcome buttons list!',
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('Back', callback_data=f'welcome_settings:{chat_id}')]])
                )
                return ConversationHandler.END

        # Build URL
        if chat_info.username:
            url = f'https://t.me/{chat_info.username}'
        elif hasattr(chat_info, 'invite_link') and chat_info.invite_link:
            url = chat_info.invite_link
        else:
            # Try to create invite link
            try:
                url = (await context.bot.create_chat_invite_link(chat_info.id)).invite_link
            except Exception:
                url = f'https://t.me/c/{str(chat_info.id)[4:]}'

        new_entry = {
            'chat_id': chat_info.id,
            'text': f'\U0001f4e2 Join {chat_info.title}',
            'title': chat_info.title,
            'url': url,
        }
        current_btns.append(new_entry)

        await db.update_channel_setting(chat_id, 'welcome_buttons_json', _json.dumps(current_btns))

        context.user_data.pop('welcome_ch_target', None)
        await update.message.reply_text(
            f'\u2705 Added {chat_info.title} as a welcome button!\n\n'
            f'Users will see a "{new_entry["text"]}" button in their welcome DM.\n\n'
            'Use /dashboard to manage settings.',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('\U0001f519 Welcome Settings', callback_data=f'welcome_settings:{chat_id}')]])
        )
        return ConversationHandler.END

    except Exception as e:
        logger.error(f'Error in welcome channel input: {e}')
        await update.message.reply_text(f'\u274c Error: {e}\nPlease try again or /cancel')
        return WELCOME_CH_INPUT
