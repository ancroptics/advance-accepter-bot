from telegram.ext import (
    Application,
    CommandHandler,
    ChatJoinRequestHandler,
    ChatMemberHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    filters,
)

from handlers.start import start_handler
from handlers.user_commands import (
    help_handler,
    referral_handler,
    leaderboard_handler,
    balance_handler,
    mystats_handler,
)
from handlers.admin_panel import dashboard_handler, superadmin_handler, channels_handler
from handlers.join_request import join_request_handler
from handlers.channel_detection import channel_detection_handler
from handlers.callbacks import callback_router
from handlers.broadcast import broadcast_conv_handler
from handlers.welcome_dm import welcome_dm_conv_handler
from handlers.clone_bot import clone_conv_handler
from handlers.batch_approve import batch_approve_conv_handler
from handlers.force_subscribe import force_subscribe_conv_handler
from handlers.template_mgmt import template_conv_handler
from handlers.auto_poster import auto_poster_conv_handler
from handlers.language_mgmt import language_conv_handler
from handlers.premium import activate_premium_handler, deactivate_premium_handler


def register_all_handlers(application: Application):
    """Register all handlers in correct priority order."""
    
    # 1. Conversation handlers (highest priority)
    conv_handlers = [
        broadcast_conv_handler,
        welcome_dm_conv_handler,
        clone_conv_handler,
        batch_approve_conv_handler,
        force_subscribe_conv_handler,
        template_conv_handler,
        auto_poster_conv_handler,
        language_conv_handler,
    ]
    for conv in conv_handlers:
        if conv is not None:
            application.add_handler(conv)

    # 2. Command handlers
    application.add_handler(CommandHandler('start', start_handler))
    application.add_handler(CommandHandler('help', help_handler))
    application.add_handler(CommandHandler('dashboard', dashboard_handler))
    application.add_handler(CommandHandler('channels', channels_handler))
    application.add_handler(CommandHandler('referral', referral_handler))
    application.add_handler(CommandHandler('leaderboard', leaderboard_handler))
    application.add_handler(CommandHandler('balance', balance_handler))
    application.add_handler(CommandHandler('mystats', mystats_handler))
    application.add_handler(CommandHandler('superadmin', superadmin_handler))
    application.add_handler(CommandHandler('activate_premium', activate_premium_handler))
    application.add_handler(CommandHandler('deactivate_premium', deactivate_premium_handler))

    # 3. Chat join request handler (CRITICAL)
    application.add_handler(ChatJoinRequestHandler(join_request_handler))

    # 4. Chat member handler (detect bot added/removed)
    application.add_handler(ChatMemberHandler(channel_detection_handler, ChatMemberHandler.MY_CHAT_MEMBER))

    # 5. Callback query handler (catch-all for buttons)
    application.add_handler(CallbackQueryHandler(callback_router))

    # 6. Fallback message handler
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, fallback_handler))


async def fallback_handler(update, context):
    """Handle unrecognized messages."""
    pass  # Silently ignore
