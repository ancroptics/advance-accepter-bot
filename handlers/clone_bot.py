import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

logger = logging.getLogger(__name__)

# Conversation states
CLONE_TOKEN = 0
CLONE_CONFIRM = 1


async def clone_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Entry point: /clone command."""
    db = context.application.bot_data.get('db')
    if not db:
        await update.message.reply_text('Bot is initializing, try again later.')
        return ConversationHandler.END

    user_id = update.effective_user.id
    owner = await db.get_owner(user_id)
    if not owner:
        await update.message.reply_text(
            'You need to be a registered channel owner first.\n'
            'Add this bot as admin to your channel.'
        )
        return ConversationHandler.END

    # Check clone limits
    tier = owner.get('tier', 'free')
    existing_clones = await db.get_owner_clones(user_id)
    clone_count = len(existing_clones) if existing_clones else 0

    limits = {'free': 1, 'basic': 3, 'pro': 10, 'enterprise': 50}
    max_clones = limits.get(tier, 1)

    if clone_count >= max_clones:
        await update.message.reply_text(
            f'You have reached your clone limit ({clone_count}/{max_clones}).\n'
            f'Upgrade your plan for more clones.'
        )
        return ConversationHandler.END

    await update.message.reply_text(
        '\U0001f916 CREATE CLONE BOT\n\n'
        'To create a clone, you need a bot token from @BotFather.\n\n'
        'Steps:\n'
        '1. Go to @BotFather\n'
        '2. Send /newbot\n'
        '3. Follow the steps to create a new bot\n'
        '4. Copy the bot token and send it here\n\n'
        f'Clones used: {clone_count}/{max_clones}\n\n'
        'Send the bot token now, or /cancel to abort.',
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton('\u274c Cancel', callback_data='clone_cancel')]
        ])
    )
    return CLONE_TOKEN


async def clone_receive_token(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive and validate the bot token."""
    token = update.message.text.strip()

    # Basic token format validation
    if ':' not in token or len(token) < 30:
        await update.message.reply_text(
            'That does not look like a valid bot token.\n'
            'It should look like: 123456789:ABCdefGHIjklMNOpqrSTUvwxYZ\n\n'
            'Try again or /cancel'
        )
        return CLONE_TOKEN

    # Test the token
    from telegram import Bot
    try:
        test_bot = Bot(token=token)
        bot_info = await test_bot.get_me()
    except Exception as e:
        await update.message.reply_text(
            f'Invalid token. Could not connect to Telegram API.\n'
            f'Error: {str(e)[:100]}\n\n'
            f'Try again or /cancel'
        )
        return CLONE_TOKEN

    # Check if token already registered
    db = context.application.bot_data.get('db')
    existing = await db.get_clone_by_token(token)
    if existing:
        await update.message.reply_text(
            f'This bot (@{bot_info.username}) is already registered as a clone.\n'
            'Use a different bot token or /cancel'
        )
        return CLONE_TOKEN

    # Store in context for confirmation
    context.user_data['clone_token'] = token
    context.user_data['clone_bot_username'] = bot_info.username
    context.user_data['clone_bot_id'] = bot_info.id

    await update.message.reply_text(
        f'\u2705 Token verified!\n\n'
        f'Bot: @{bot_info.username}\n'
        f'Bot ID: {bot_info.id}\n\n'
        f'This clone will handle join requests for your channels '
        f'using the same settings as the main bot.\n\n'
        f'Confirm creation?',
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton('\u2705 Create Clone', callback_data='clone_confirm'),
             InlineKeyboardButton('\u274c Cancel', callback_data='clone_cancel')]
        ])
    )
    return CLONE_CONFIRM


async def clone_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Confirm and create the clone."""
    query = update.callback_query
    await query.answer()

    token = context.user_data.get('clone_token')
    bot_username = context.user_data.get('clone_bot_username')
    bot_id = context.user_data.get('clone_bot_id')
    user_id = query.from_user.id

    if not token:
        await query.edit_message_text('Session expired. Use /clone to start again.')
        return ConversationHandler.END

    db = context.application.bot_data.get('db')

    try:
        # Create clone in database
        clone_id = await db.create_clone(
            owner_id=user_id,
            bot_token=token,
            bot_username=bot_username,
            bot_name=bot_username,
        )

        # Start the clone
        clone_mgr = context.application.bot_data.get('clone_manager')
        if clone_mgr:
            try:
                await clone_mgr.start_clone(clone_id, token, user_id)
                status_text = '\u2705 Clone is now ACTIVE and handling join requests!'
            except Exception as e:
                logger.error(f'Failed to start clone {clone_id}: {e}')
                status_text = (f'\u26a0\ufe0f Clone created but failed to start: {str(e)[:100]}\n'
                              f'You can try activating it from the dashboard.')
        else:
            status_text = '\u26a0\ufe0f Clone created but clone manager not available. Restart may be needed.'

        await query.edit_message_text(
            f'\U0001f916 CLONE CREATED\n\n'
            f'Bot: @{bot_username}\n'
            f'Clone ID: {clone_id}\n\n'
            f'{status_text}\n\n'
            f'Important: Make sure to add @{bot_username} as admin '
            f'to the channels you want it to manage.',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton('\U0001f4ca Dashboard', callback_data='admin_panel')]
            ])
        )

    except Exception as e:
        logger.exception(f'Error creating clone: {e}')
        await query.edit_message_text(
            f'\u274c Failed to create clone: {str(e)[:200]}\n\n'
            f'Please try again with /clone',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton('\U0001f4ca Dashboard', callback_data='admin_panel')]
            ])
        )

    # Clean up
    context.user_data.pop('clone_token', None)
    context.user_data.pop('clone_bot_username', None)
    context.user_data.pop('clone_bot_id', None)

    return ConversationHandler.END


async def clone_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel clone creation."""
    context.user_data.pop('clone_token', None)
    context.user_data.pop('clone_bot_username', None)
    context.user_data.pop('clone_bot_id', None)

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            'Clone creation cancelled.',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton('\U0001f4ca Dashboard', callback_data='admin_panel')]
            ])
        )
    else:
        await update.message.reply_text('Clone creation cancelled.')

    return ConversationHandler.END


# ConversationHandler for clone creation
clone_conv_handler = ConversationHandler(
    entry_points=[CommandHandler('clone', clone_command)],
    states={
        CLONE_TOKEN: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, clone_receive_token),
            CallbackQueryHandler(clone_cancel, pattern='^clone_cancel$'),
        ],
        CLONE_CONFIRM: [
            CallbackQueryHandler(clone_confirm, pattern='^clone_confirm$'),
            CallbackQueryHandler(clone_cancel, pattern='^clone_cancel$'),
        ],
    },
    fallbacks=[
        CommandHandler('cancel', clone_cancel),
        CallbackQueryHandler(clone_cancel, pattern='^clone_cancel$'),
    ],
    per_message=False,
)
