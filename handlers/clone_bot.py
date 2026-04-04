import logging
import aiohttp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, MessageHandler, filters, CallbackQueryHandler
from utils.decorators import channel_owner_only, premium_required

logger = logging.getLogger(__name__)

WAITING_TOKEN = 1


async def show_clone_menu(update, context):
    query = update.callback_query
    user_id = query.from_user.id
    db = context.application.bot_data.get('db')
    owner = await db.get_owner(user_id)
    clones = await db.get_owner_clones(user_id)

    text = '\U0001f9ec BOT CLONING\n\n'
    if clones:
        for clone in clones:
            status = '\U0001f7e2 Active' if clone['is_active'] else '\U0001f534 Inactive'
            text += (f"\U0001f916 @{clone['bot_username'] or 'Unknown'}\n"
                     f"   Status: {status}\n"
                     f"   Errors: {clone.get('error_count', 0)}\n"
                     f"   Created: {str(clone.get('created_at', ''))[:10]}\n\n")
        buttons = []
        for clone in clones:
            cid = clone['clone_id']
            if clone['is_active']:
                buttons.append([InlineKeyboardButton(f"\u23f8\ufe0f Pause @{clone['bot_username']}", callback_data=f'pause_clone:{cid}')])
            else:
                buttons.append([InlineKeyboardButton(f"\u25b6\ufe0f Activate @{clone['bot_username']}", callback_data=f'activate_clone:{cid}')])
            buttons.append([InlineKeyboardButton(f"\U0001f5d1\ufe0f Delete @{clone['bot_username']}", callback_data=f'delete_clone:{cid}')])
    else:
        text += ('Create your own branded version of this bot!\n\n'
                 'Your clone will have:\n'
                 '\u2705 Auto-approve join requests\n'
                 '\u2705 Custom welcome DMs\n'
                 '\u2705 Analytics dashboard\n'
                 '\u2705 Broadcast to users\n'
                 '\u2705 Your branding\n\n'
                 'How to create:\n'
                 '1. Open @BotFather\n'
                 '2. Create a new bot (/newbot)\n'
                 '3. Copy the token\n'
                 '4. Click Send Bot Token below\n')
        buttons = []

    tier = owner['tier'] if owner else 'free'
    max_clones = {'free': 0, 'premium': 1, 'business': 5}.get(tier, 0)
    current_count = len(clones) if clones else 0

    if current_count < max_clones:
        buttons.append([InlineKeyboardButton('\U0001f4cb Send Bot Token', callback_data='clone_send_token')])
    elif tier == 'free':
        buttons.append([InlineKeyboardButton('\U0001f48e Upgrade to Clone', callback_data='premium_info')])

    buttons.append([InlineKeyboardButton('\U0001f519 Back', callback_data='dashboard')])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))


async def prompt_clone_token(update, context):
    query = update.callback_query
    user_id = query.from_user.id
    db = context.application.bot_data.get('db')
    owner = await db.get_owner(user_id)
    tier = owner['tier'] if owner else 'free'
    if tier == 'free':
        await query.edit_message_text(
            '\U0001f512 Bot cloning requires Premium or Business plan.',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton('\U0001f48e Upgrade', callback_data='premium_info')],
                [InlineKeyboardButton('\U0001f519 Back', callback_data='clone_bot_menu')]
            ])
        )
        return ConversationHandler.END

    context.user_data['awaiting_clone_token'] = True
    await query.edit_message_text(
        '\U0001f916 Send me the bot token from @BotFather.\n\n'
        'Format: 123456789:ABCdefGHIjklMNOpqrsTUVwxyz\n\n'
        'Type /cancel to cancel.',
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton('\u274c Cancel', callback_data='clone_bot_menu')]
        ])
    )
    return WAITING_TOKEN


async def receive_clone_token(update, context):
    token = update.message.text.strip()
    user_id = update.effective_user.id
    db = context.application.bot_data.get('db')

    # Validate token
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f'https://api.telegram.org/bot{token}/getMe', timeout=aiohttp.ClientTimeout(total=10)) as resp:
                data = await resp.json()
                if not data.get('ok'):
                    await update.message.reply_text(
                        '\u274c Invalid token. Please check and resend.',
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton('\U0001f519 Back', callback_data='clone_bot_menu')]
                        ])
                    )
                    return ConversationHandler.END
                bot_info = data['result']
    except Exception as e:
        logger.error(f'Token validation error: {e}')
        await update.message.reply_text('\u274c Could not validate token. Try again later.')
        return ConversationHandler.END

    # Check if token already registered
    existing = await db.get_clone_by_token(token)
    if existing:
        await update.message.reply_text(
            '\u274c This bot token is already registered.',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton('\U0001f519 Back', callback_data='clone_bot_menu')]
            ])
        )
        return ConversationHandler.END

    # Save clone
    clone_id = await db.create_clone(
        owner_id=user_id,
        bot_token=token,
        bot_user_id=bot_info['id'],
        bot_username=bot_info.get('username', ''),
        bot_first_name=bot_info.get('first_name', ''),
    )

    await update.message.reply_text(
        f"\U0001f916 Bot Found!\n"
        f"Name: {bot_info.get('first_name', '')}\n"
        f"Username: @{bot_info.get('username', '')}\n\n"
        f"Click Activate to start your clone.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton('\u2705 Activate Clone', callback_data=f'activate_clone:{clone_id}')],
            [InlineKeyboardButton('\u274c Cancel', callback_data='clone_bot_menu')]
        ])
    )
    return ConversationHandler.END


async def activate_clone(update, context, clone_id):
    query = update.callback_query
    db = context.application.bot_data.get('db')
    clone_manager = context.application.bot_data.get('clone_manager')

    clone = await db.get_clone(clone_id)
    if not clone:
        await query.edit_message_text('Clone not found.')
        return

    try:
        await clone_manager.start_clone(clone_id, clone['bot_token'], clone['owner_id'])
        await db.update_clone_status(clone_id, is_active=True)
        await query.edit_message_text(
            f"\u2705 Clone Activated!\n\n"
            f"Your bot @{clone['bot_username']} is now live!\n\n"
            f"\u2022 Add it as admin to your channels\n"
            f"\u2022 It will handle join requests automatically\n"
            f"\u2022 Manage it from this dashboard",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton('\U0001f519 Back', callback_data='clone_bot_menu')]
            ])
        )
    except Exception as e:
        logger.exception(f'Failed to activate clone {clone_id}: {e}')
        await query.edit_message_text(
            f'\u274c Failed to activate clone: {str(e)[:100]}',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton('\U0001f519 Back', callback_data='clone_bot_menu')]
            ])
        )


async def pause_clone(update, context, clone_id):
    query = update.callback_query
    db = context.application.bot_data.get('db')
    clone_manager = context.application.bot_data.get('clone_manager')
    try:
        await clone_manager.stop_clone(clone_id)
        await db.update_clone_status(clone_id, is_active=False)
        await query.edit_message_text('\u23f8\ufe0f Clone paused.',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('\U0001f519 Back', callback_data='clone_bot_menu')]]))
    except Exception as e:
        logger.error(f'Error pausing clone: {e}')


async def delete_clone(update, context, clone_id):
    query = update.callback_query
    db = context.application.bot_data.get('db')
    clone_manager = context.application.bot_data.get('clone_manager')
    try:
        await clone_manager.stop_clone(clone_id)
        await db.delete_clone(clone_id)
        await query.edit_message_text('\U0001f5d1\ufe0f Clone deleted.',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('\U0001f519 Back', callback_data='clone_bot_menu')]]))
    except Exception as e:
        logger.error(f'Error deleting clone: {e}')


async def cancel_clone(update, context):
    context.user_data.pop('awaiting_clone_token', None)
    await update.message.reply_text('Clone setup cancelled.')
    return ConversationHandler.END


clone_conv_handler = ConversationHandler(
    entry_points=[CallbackQueryHandler(prompt_clone_token, pattern='^clone_send_token$')],
    states={
        WAITING_TOKEN: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_clone_token)],
    },
    fallbacks=[MessageHandler(filters.COMMAND, cancel_clone)],
    per_user=True,
    per_chat=True,
)
