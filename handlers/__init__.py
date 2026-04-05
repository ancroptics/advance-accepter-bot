import logging
from telegram.ext import (
    CommandHandler, MessageHandler, CallbackQueryHandler,
    ChatMemberHandler, ChatJoinRequestHandler, ConversationHandler,
    filters
)
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from handlers.callbacks import callback_router
from handlers.channel_detection import channel_detection_handler
from handlers.join_request import join_request_handler
import config

logger = logging.getLogger(__name__)

def register_handlers(application):
    """Register all bot handlers."""
    from handlers.admin_panel import dashboard_handler, channels_handler, superadmin_handler
    from handlers.start import start_handler
    from handlers.user_commands import help_handler
    from handlers.premium import activate_premium_handler, deactivate_premium_handler

    # 1. Command handlers
    application.add_handler(CommandHandler('start', start_handler))
    application.add_handler(CommandHandler('help', help_handler))
    application.add_handler(CommandHandler('dashboard', dashboard_handler))
    application.add_handler(CommandHandler('channels', channels_handler))
    application.add_handler(CommandHandler('superadmin', superadmin_handler))
    application.add_handler(CommandHandler('activate_premium', activate_premium_handler))
    application.add_handler(CommandHandler('deactivate_premium', deactivate_premium_handler))

    # 2. Chat member handler (bot added/removed from channels)
    application.add_handler(ChatMemberHandler(channel_detection_handler, ChatMemberHandler.MY_CHAT_MEMBER))

    # 3. Join request handler
    application.add_handler(ChatJoinRequestHandler(join_request_handler))

    # 4. Clone bot conversation handler
    from handlers.clone_bot import clone_conv_handler
    application.add_handler(clone_conv_handler)

    # 5. Force sub channel input conversation handler
    from handlers.force_subscribe import handle_force_sub_channel_input, start_add_force_sub_channel, FORCE_SUB_INPUT

    async def force_sub_entry(update, context):
        query = update.callback_query
        data = query.data
        chat_id = int(data.split(':')[1])
        await query.answer()
        return await start_add_force_sub_channel(update, context, chat_id)

    force_sub_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(force_sub_entry, pattern=r'^add_force_sub_ch:')],
        states={
            FORCE_SUB_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_force_sub_channel_input)],
        },
        fallbacks=[
            CommandHandler('cancel', lambda u, c: ConversationHandler.END),
        ],
        per_message=False,
    )
    application.add_handler(force_sub_conv)

    # 6. Callback query handler (catch-all for buttons)
    application.add_handler(CallbackQueryHandler(callback_router))

    # 7. Fallback message handler
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_input))

    logger.info('All handlers registered.')

async def handle_text_input(update, context):
    """Handle text inputs for various conversation states."""
    if not update.effective_user:
        return
    user_id = update.effective_user.id
    db = context.application.bot_data.get('db')

    # Handle welcome message editing
    if context.user_data.get('editing_welcome_for'):
        chat_id = context.user_data.pop('editing_welcome_for')
        new_msg = update.message.text
        await db.update_channel_setting(chat_id, 'welcome_message', new_msg)
        await update.message.reply_text(
            f'\u2705 Welcome message updated!\n\nPreview:\n{new_msg}',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('Back', callback_data=f'manage_channel:{chat_id}')]])
        )
        return

    # Handle support username editing
    if context.user_data.get('awaiting_support_username'):
        context.user_data.pop('awaiting_support_username')
        new_username = update.message.text.strip().replace('@', '')
        config.SUPPORT_USERNAME = new_username
        import os
        os.environ['SUPPORT_USERNAME'] = new_username
        await update.message.reply_text(
            f'\u2705 Support username updated to @{new_username}',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('Back', callback_data='dashboard')]])
        )
        return

    # Handle watermark username editing
    if context.user_data.get('editing_watermark_for'):
        chat_id = context.user_data.pop('editing_watermark_for')
        new_username = update.message.text.strip().replace('@', '')
        await db.update_channel_setting(chat_id, 'watermark_username', new_username)
        await db.update_channel_setting(chat_id, 'watermark_enabled', True)
        await update.message.reply_text(
            f'\u2705 Watermark set to @{new_username}\n\nThis will appear on all welcome and force-sub messages.',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('Back', callback_data=f'manage_channel:{chat_id}')]])
        )
        return

    # Handle UPI ID editing (superadmin)
    if context.user_data.get('awaiting_upi_input'):
        if user_id not in config.SUPERADMIN_IDS:
            return
        context.user_data.pop('awaiting_upi_input')
        new_upi = update.message.text.strip()
        config.UPI_ID = new_upi
        import os
        os.environ['UPI_ID'] = new_upi
        await update.message.reply_text(
            f'\u2705 UPI ID updated to: {new_upi}\n\n'
            'Note: Set UPI_ID env var on Render for permanent change.',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('Back to Dashboard', callback_data='dashboard')]])
        )
        return

    # Handle broadcast message
    if context.user_data.get('broadcast_channel'):
        chat_id = context.user_data.pop('broadcast_channel')
        message = update.message.text
        users = await db.get_channel_users(chat_id)
        sent = 0
        failed = 0
        for u in (users or []):
            try:
                await context.bot.send_message(u['user_id'], message)
                sent += 1
            except Exception:
                failed += 1
        await update.message.reply_text(
            f'\U0001f4e2 Broadcast complete!\n\nSent: {sent}\nFailed: {failed}',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('Back', callback_data=f'manage_channel:{chat_id}')]])
        )
        return

# Alias for bot.py import
register_all_handlers = register_handlers
