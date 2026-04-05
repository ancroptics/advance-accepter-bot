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

from handlers.callbacks import (
    start_command,
    help_command,
    my_channels_command,
    stats_command,
    button_handler,
    join_request_handler,
    dm_text_handler,
    broadcast_text_handler,
    admin_command,
    admin_button_handler,
    clone_command,
)
from handlers.batch_approve import batch_approve_command, batch_button_handler

logger = logging.getLogger(__name__)

# Conversation states
DM_TEXT_STATE = range(1)
BROADCAST_TEXT_STATE = range(1, 2)


def register_all_handlers(app):
    """Register all bot handlers."""

    # DM template conversation
    dm_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(lambda u, c: _is_set_dm(u), _dm_entry)],
        states={
            0: [MessageHandler(filters.TEXT & ~filters.COMMAND, dm_text_handler)],
        },
        fallbacks=[CommandHandler('cancel', _cancel)],
        per_message=False,
    )

    # Broadcast conversation
    bcast_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(lambda u, c: _is_broadcast(u), _bcast_entry)],
        states={
            0: [
                MessageHandler(filters.TEXT | filters.PHOTO | filters.Document.ALL, broadcast_text_handler),
            ],
        },
        fallbacks=[CommandHandler('cancel', _cancel)],
        per_message=False,
    )

    # Conversations first (they need priority)
    app.add_handler(dm_conv)
    app.add_handler(bcast_conv)

    # Commands
    app.add_handler(CommandHandler('start', start_command))
    app.add_handler(CommandHandler('help', help_command))
    app.add_handler(CommandHandler('mychannels', my_channels_command))
    app.add_handler(CommandHandler('stats', stats_command))
    app.add_handler(CommandHandler('admin', admin_command))
    app.add_handler(CommandHandler('clone', clone_command))
    app.add_handler(CommandHandler('batch', batch_approve_command))

    # Callback queries
    app.add_handler(CallbackQueryHandler(_is_admin_callback, admin_button_handler))
    app.add_handler(CallbackQueryHandler(_is_batch_callback, batch_button_handler))
    app.add_handler(CallbackQueryHandler(_is_general_callback, button_handler))

    # Join requests
    app.add_handler(ChatJoinRequestHandler(join_request_handler))

    logger.info('All handlers registered')


# --- Helpers ---

def _is_set_dm(update):
    if update.callback_query and update.callback_query.data:
        return update.callback_query.data.startswith('set_dm:')
    return False

def _is_broadcast(update):
    if update.callback_query and update.callback_query.data:
        return update.callback_query.data.startswith('broadcast:')
    return False

def _is_admin_callback(update, context):
    if update.callback_query and update.callback_query.data:
        d = update.callback_query.data
        return d.startswith(('admin_', 'tier_', 'ban_', 'unban_'))
    return False

def _is_batch_callback(update, context):
    if update.callback_query and update.callback_query.data:
        d = update.callback_query.data
        return d.startswith(('batch_', 'bapprove_', 'bdecline_'))
    return False

def _is_general_callback(update, context):
    return update.callback_query is not None


async def _dm_entry(update, context):
    """Entry point for DM template conversation."""
    query = update.callback_query
    await query.answer()
    chat_id = query.data.split(':')[1]
    context.user_data['dm_chat_id'] = int(chat_id)
    await query.edit_message_text(
        "<b>📝 Send me the DM template text</b>\n\n"
        "Variables:\n"
        "<code>{name}</code> — User's first name\n"
        "<code>{username}</code> — Username\n"
        "<code>{channel}</code> — Channel title\n\n"
        "/cancel to abort",
        parse_mode='HTML'
    )
    return 0


async def _bcast_entry(update, context):
    """Entry point for broadcast conversation."""
    query = update.callback_query
    await query.answer()
    chat_id = query.data.split(':')[1]
    context.user_data['bcast_chat_id'] = int(chat_id)
    await query.edit_message_text(
        "<b>📢 Send your broadcast message</b>\n\n"
        "Supported: text, photo, document\n"
        "This will be sent to all approved users.\n\n"
        "/cancel to abort",
        parse_mode='HTML'
    )
    return 0


async def _cancel(update, context):
    """Cancel conversation."""
    await update.message.reply_text("❌ Cancelled")
    return ConversationHandler.END
