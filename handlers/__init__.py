import logging
from telegram import Update
from telegram.ext import (
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ChatJoinRequestHandler,
    ConversationHandler,
    filters
)

from handlers.callbacks import callback_router
from handlers.start import start_handler
from handlers.user_commands import help_handler, mystats_handler
from handlers.admin_panel import dashboard_handler, channels_handler, superadmin_handler
from handlers.join_request import join_request_handler
from handlers.batch_approve import batch_approve_command, batch_button_handler
from handlers.clone_bot import clone_command
from handlers.broadcast import start_broadcast, receive_content, cancel_broadcast
from handlers.welcome_dm import edit_welcome_receive, cancel_edit_welcome
from handlers.channel_detection import channel_detection_handler

logger = logging.getLogger(__name__)


def register_all_handlers(app):
    """Register all bot handlers."""

    # Commands
    app.add_handler(CommandHandler('start', start_handler))
    app.add_handler(CommandHandler('help', help_handler))
    app.add_handler(CommandHandler('dashboard', dashboard_handler))
    app.add_handler(CommandHandler('mychannels', channels_handler))
    app.add_handler(CommandHandler('stats', mystats_handler))
    app.add_handler(CommandHandler('admin', superadmin_handler))
    app.add_handler(CommandHandler('clone', clone_command))
    app.add_handler(CommandHandler('batch', batch_approve_command))

    # Callback queries - batch first (more specific), then general
    app.add_handler(CallbackQueryHandler(batch_button_handler, pattern=r'^(batch_|bapprove_|bdecline_)'))
    app.add_handler(CallbackQueryHandler(callback_router))

    # Join requests
    app.add_handler(ChatJoinRequestHandler(join_request_handler))

    # Chat member updates (channel detection)
    try:
        from telegram.ext import ChatMemberHandler
        app.add_handler(ChatMemberHandler(channel_detection_handler, ChatMemberHandler.MY_CHAT_MEMBER))
    except ImportError:
        logger.warning("ChatMemberHandler not available")

    # Message handlers for conversations (welcome DM editing, broadcast, etc.)
    # These catch text messages during active editing sessions
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE,
        _handle_text_message
    ))

    logger.info('All handlers registered')


async def _handle_text_message(update: Update, context):
    """Route text messages based on user state."""
    user_data = context.user_data

    if user_data.get('editing_welcome_for'):
        await edit_welcome_receive(update, context)
    elif user_data.get('broadcast_channel'):
        await receive_content(update, context)
    elif user_data.get('awaiting_upi_input'):
        # Handle UPI edit
        import config as cfg
        import os
        new_upi = update.message.text.strip()
        cfg.UPI_ID = new_upi
        os.environ['UPI_ID'] = new_upi
        user_data.pop('awaiting_upi_input', None)
        await update.message.reply_text(f'\u2705 UPI ID updated to: {new_upi}')
    elif user_data.get('awaiting_clone_token'):
        from handlers.clone_bot import clone_receive_token
        await clone_receive_token(update, context)
