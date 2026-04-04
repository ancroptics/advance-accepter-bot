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
