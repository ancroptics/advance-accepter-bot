import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import ContextTypes
from database.models import Database
import config

logger = logging.getLogger(__name__)

async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    logger.info(f"Callback received: {data}")
    
    if data == 'list_channels':
        await list_channels(update, context)
    elif data == 'help':
        await show_help(update, context)
    elif data == 'back_main':
        await back_to_main(update, context)
    elif data.startswith('ch_'):
        await channel_menu(update, context, data)
    elif data.startswith('approve_all_'):
        await approve_all_pending(update, context, data)
    elif data.startswith('pending_'):
        await show_pending_requests(update, context, data)
    elif data.startswith('set_'):
        await handle_settings(update, context, data)
    elif data.startswith('drip_'):
        await handle_drip(update, context, data)
    elif data.startswith('batch_'):
        await handle_batch(update, context, data)
    elif data.startswith('sync_'):
        await handle_sync(update, context, data)
    elif data.startswith('stats_'):
        await show_channel_stats(update, context, data)
    elif data.startswith('toggle_'):
        await handle_toggle(update, context, data)
    elif data.startswith('remove_'):
        await handle_remove(update, context, data)
    elif data.startswith('confirm_remove_'):
        await confirm_remove(update, context, data)
    else:
        logger.warning(f"Unknown callback: {data}")


async def list_channels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    db = context.application.bot_data.get('db')
    user_id = query.from_user.id
    
    if user_id not in config.SUPERADMIN_IDS:
        await query.edit_message_text("\u26d4 You are not authorized.")
        return
    
    channels = await db.get_all_channels()
    if not channels:
        keyboard = [[InlineKeyboardButton("\u00ab Back", callback_data='back_main')]]
        await query.edit_message_text(
            "\ud83d\udcad No channels registered yet.\n\nAdd me as admin to a channel and I'll detect it automatically.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    keyboard = []
    for ch in channels:
        status = "\u2705" if ch.get('auto_approve') else "\u23f8\ufe0f"
        pending = ch.get('pending_count', 0)
        pending_text = f" ({pending} pending)" if pending else ""
        title = ch.get('title', f"Chat {ch['chat_id']}")
        keyboard.append([InlineKeyboardButton(
            f"{status} {title}{pending_text}",
            callback_data=f"ch_{ch['chat_id']}"
        )])
    keyboard.append([InlineKeyboardButton("\u00ab Back", callback_data='back_main')])
    
    await query.edit_message_text(
        "\ud83d\udcfa **Your Channels:**\n\nSelect a channel to manage:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )


async def channel_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, data: str):
    query = update.callback_query
    db = context.application.bot_data.get('db')
    chat_id = int(data.replace('ch_', ''))
    channel = await db.get_channel(chat_id)
    
    if not channel:
        await query.edit_message_text("Channel not found.")
        return
    
    title = channel.get('title', f"Chat {chat_id}")
    auto_approve = channel.get('auto_approve', False)
    pending_count = channel.get('pending_count', 0)
    total_approved = channel.get('total_approved', 0)
    drip_enabled = channel.get('drip_enabled', False)
    
    status_emoji = "\u2705 Active" if auto_approve else "\u23f8\ufe0f Paused"
    drip_status = "\ud83d\udca7 Drip ON" if drip_enabled else "\ud83d\udca7 Drip OFF"
    
    text = (
        f"\ud83d\udcfa **{title}**\n"
        f"\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n"
        f"Status: {status_emoji}\n"
        f"Pending: {pending_count} requests\n"
        f"Total Approved: {total_approved}\n"
        f"Drip Mode: {drip_status}\n"
    )
    
    keyboard = []
    
    toggle_text = "\u23f8\ufe0f Pause Auto-Approve" if auto_approve else "\u25b6\ufe0f Enable Auto-Approve"
    keyboard.append([InlineKeyboardButton(toggle_text, callback_data=f"toggle_{chat_id}")])
    
    if pending_count > 0:
        keyboard.append([InlineKeyboardButton(f"\u2705 Approve All ({pending_count})", callback_data=f"approve_all_{chat_id}")])
        keyboard.append([InlineKeyboardButton(f"\ud83d\udcdd View Pending", callback_data=f"pending_{chat_id}")])
    
    keyboard.append([InlineKeyboardButton(f"\ud83d\udca7 Drip Settings", callback_data=f"drip_{chat_id}")])
    keyboard.append([InlineKeyboardButton(f"\u2699\ufe0f Settings", callback_data=f"set_{chat_id}")])
    keyboard.append([InlineKeyboardButton(f"\ud83d\udcca Stats", callback_data=f"stats_{chat_id}")])
    keyboard.append([InlineKeyboardButton(f"\ud83d\udd04 Sync Pending", callback_data=f"sync_{chat_id}")])
    keyboard.append([InlineKeyboardButton(f"\ud83d\uddd1 Remove", callback_data=f"remove_{chat_id}")])
    keyboard.append([InlineKeyboardButton("\u00ab Back to Channels", callback_data='list_channels')])
    
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )


async def show_pending_requests(update: Update, context: ContextTypes.DEFAULT_TYPE, data: str):
    query = update.callback_query
    db = context.application.bot_data.get('db')
    chat_id = int(data.replace('pending_', ''))
    
    pending = await db.get_pending_requests(chat_id, limit=20)
    channel = await db.get_channel(chat_id)
    title = channel.get('title', f"Chat {chat_id}") if channel else f"Chat {chat_id}"
    
    if not pending:
        keyboard = [[InlineKeyboardButton("\u00ab Back", callback_data=f"ch_{chat_id}")]]
        await query.edit_message_text(
            f"\u2705 No pending requests for **{title}**",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return
    
    text = f"\ud83d\udcdd **Pending Requests for {title}:**\n\n"
    for i, req in enumerate(pending, 1):
        user_name = req.get('user_name', 'Unknown')
        user_id = req.get('user_id', '?')
        requested_at = req.get('requested_at', '?')
        text += f"{i}. {user_name} (ID: `{user_id}`) - {requested_at}\n"
    
    total_pending = channel.get('pending_count', len(pending))
    if total_pending > 20:
        text += f"\n_...and {total_pending - 20} more_\n"
    
    keyboard = [
        [InlineKeyboardButton(f"\u2705 Approve All ({total_pending})", callback_data=f"approve_all_{chat_id}")],
        [InlineKeyboardButton("\u00ab Back", callback_data=f"ch_{chat_id}")]
    ]
    
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )


async def approve_all_pending(update: Update, context: ContextTypes.DEFAULT_TYPE, data: str):
    query = update.callback_query
    db = context.application.bot_data.get('db')
    chat_id = int(data.replace('approve_all_', ''))
    channel = await db.get_channel(chat_id)
    title = channel.get('title', f"Chat {chat_id}") if channel else f"Chat {chat_id}"
    
    pending = await db.get_pending_requests(chat_id)
    if not pending:
        keyboard = [[InlineKeyboardButton("\u00ab Back", callback_data=f"ch_{chat_id}")]]
        await query.edit_message_text(
            f"\u2705 No pending requests for **{title}**",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return
    
    await query.edit_message_text(f"\u23f3 Approving {len(pending)} requests for **{title}**...\nThis may take a moment.", parse_mode='Markdown')
    
    approved = 0
    failed = 0
    for req in pending:
        try:
            await context.bot.approve_chat_join_request(
                chat_id=chat_id,
                user_id=req['user_id']
            )
            await db.update_request_status(req['id'], 'approved')
            approved += 1
        except BadRequest as e:
            logger.warning(f"Failed to approve {req['user_id']}: {e}")
            await db.update_request_status(req['id'], 'failed', error=str(e))
            failed += 1
        except Exception as e:
            logger.error(f"Error approving {req['user_id']}: {e}")
            failed += 1
    
    await db.update_channel_stats(chat_id, approved=approved)
    
    result_text = f"\u2705 **Approval Complete for {title}**\n\n"
    result_text += f"Approved: {approved}\n"
    if failed:
        result_text += f"Failed: {failed}\n"
    
    keyboard = [[InlineKeyboardButton("\u00ab Back", callback_data=f"ch_{chat_id}")]]
    await query.edit_message_text(
        result_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )


async def handle_settings(update: Update, context: ContextTypes.DEFAULT_TYPE, data: str):
    from handlers.channel_settings import show_channel_settings
    chat_id = int(data.replace('set_', ''))
    await show_channel_settings(update, context, chat_id, edit=True)


async def handle_drip(update: Update, context: ContextTypes.DEFAULT_TYPE, data: str):
    from handlers.batch_approve import show_drip_menu
    chat_id = int(data.replace('drip_', ''))
    await show_drip_menu(update, context, chat_id)


async def handle_batch(update: Update, context: ContextTypes.DEFAULT_TYPE, data: str):
    from handlers.batch_approve import handle_batch_callback
    await handle_batch_callback(update, context, data)


async def handle_sync(update: Update, context: ContextTypes.DEFAULT_TYPE, data: str):
    query = update.callback_query
    db = context.application.bot_data.get('db')
    chat_id = int(data.replace('sync_', ''))
    channel = await db.get_channel(chat_id)
    title = channel.get('title', f"Chat {chat_id}") if channel else f"Chat {chat_id}"
    
    await query.edit_message_text(f"\ud83d\udd04 Syncing pending requests for **{title}**...\nThis uses Telethon to fetch pending members.", parse_mode='Markdown')
    
    try:
        telethon_client = context.application.bot_data.get('telethon_client')
        if not telethon_client:
            keyboard = [[InlineKeyboardButton("\u00ab Back", callback_data=f"ch_{chat_id}")]]
            await query.edit_message_text(
                "\u26a0\ufe0f Telethon client not configured. Cannot sync.",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return
        
        pending_users = await telethon_client.get_pending_join_requests(chat_id)
        
        if pending_users is None:
            keyboard = [[InlineKeyboardButton("\u00ab Back", callback_data=f"ch_{chat_id}")]]
            await query.edit_message_text(
                "\u26a0\ufe0f Failed to fetch pending requests. Check bot permissions.",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return
        
        existing_ids = await db.get_pending_request_user_ids(chat_id)
        new_count = 0
        for user in pending_users:
            if user['user_id'] not in existing_ids:
                await db.save_pending_request(
                    chat_id=chat_id,
                    user_id=user['user_id'],
                    user_name=user.get('first_name', 'Unknown'),
                    requested_at=user.get('date')
                )
                new_count += 1
        
        await db.update_pending_count(chat_id)
        updated_channel = await db.get_channel(chat_id)
        total = updated_channel.get('pending_count', 0)
        
        keyboard = [[InlineKeyboardButton("\u00ab Back", callback_data=f"ch_{chat_id}")]]
        await query.edit_message_text(
            f"\u2705 **Sync Complete for {title}**\n\n"
            f"New requests found: {new_count}\n"
            f"Total pending: {total}",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Sync error for {chat_id}: {e}")
        keyboard = [[InlineKeyboardButton("\u00ab Back", callback_data=f"ch_{chat_id}")]]
        await query.edit_message_text(
            f"\u274c Sync failed: {str(e)}",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


async def show_channel_stats(update: Update, context: ContextTypes.DEFAULT_TYPE, data: str):
    query = update.callback_query
    db = context.application.bot_data.get('db')
    chat_id = int(data.replace('stats_', ''))
    channel = await db.get_channel(chat_id)
    
    if not channel:
        await query.edit_message_text("Channel not found.")
        return
    
    title = channel.get('title', f"Chat {chat_id}")
    stats = await db.get_channel_stats(chat_id)
    
    text = (
        f"\ud83d\udcca **Stats for {title}**\n"
        f"\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n"
        f"Total Approved: {stats.get('total_approved', 0)}\n"
        f"Total Declined: {stats.get('total_declined', 0)}\n"
        f"Pending: {stats.get('pending_count', 0)}\n"
        f"Today Approved: {stats.get('today_approved', 0)}\n"
        f"Today Declined: {stats.get('today_declined', 0)}\n"
        f"\n"
        f"Auto-Approve: {'\u2705 ON' if channel.get('auto_approve') else '\u274c OFF'}\n"
        f"Drip Mode: {'\u2705 ON' if channel.get('drip_enabled') else '\u274c OFF'}\n"
    )
    
    keyboard = [[InlineKeyboardButton("\u00ab Back", callback_data=f"ch_{chat_id}")]]
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )


async def handle_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE, data: str):
    query = update.callback_query
    db = context.application.bot_data.get('db')
    chat_id = int(data.replace('toggle_', ''))
    channel = await db.get_channel(chat_id)
    
    if not channel:
        await query.edit_message_text("Channel not found.")
        return
    
    new_state = not channel.get('auto_approve', False)
    await db.update_channel(chat_id, auto_approve=new_state)
    
    status = "\u2705 enabled" if new_state else "\u23f8\ufe0f paused"
    await query.answer(f"Auto-approve {status}")
    
    await channel_menu(update, context, f"ch_{chat_id}")


async def handle_remove(update: Update, context: ContextTypes.DEFAULT_TYPE, data: str):
    query = update.callback_query
    chat_id = int(data.replace('remove_', ''))
    db = context.application.bot_data.get('db')
    channel = await db.get_channel(chat_id)
    title = channel.get('title', f"Chat {chat_id}") if channel else f"Chat {chat_id}"
    
    keyboard = [
        [InlineKeyboardButton("\u2705 Yes, Remove", callback_data=f"confirm_remove_{chat_id}")],
        [InlineKeyboardButton("\u274c Cancel", callback_data=f"ch_{chat_id}")]
    ]
    
    await query.edit_message_text(
        f"\u26a0\ufe0f **Remove {title}?**\n\nThis will stop tracking this channel and delete all pending requests.",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )


async def confirm_remove(update: Update, context: ContextTypes.DEFAULT_TYPE, data: str):
    query = update.callback_query
    chat_id = int(data.replace('confirm_remove_', ''))
    db = context.application.bot_data.get('db')
    channel = await db.get_channel(chat_id)
    title = channel.get('title', f"Chat {chat_id}") if channel else f"Chat {chat_id}"
    
    await db.remove_channel(chat_id)
    
    keyboard = [[InlineKeyboardButton("\u00ab Back to Channels", callback_data='list_channels')]]
    await query.edit_message_text(
        f"\u2705 **{title}** has been removed.",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )


async def show_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    
    help_text = (
        "\ud83d\udcd6 **Help & Commands**\n"
        "\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n\n"
        "**Getting Started:**\n"
        "1. Add this bot as admin to your channel\n"
        "2. The bot will auto-detect the channel\n"
        "3. Use /start to manage your channels\n\n"
        "**Commands:**\n"
        "/start - Main menu\n"
        "/help - This help message\n"
        "/channels - List your channels\n"
        "/stats - Quick stats overview\n\n"
        "**Features:**\n"
        "\u2022 \u2705 Auto-approve join requests\n"
        "\u2022 \ud83d\udca7 Drip mode (gradual approvals)\n"
        "\u2022 \ud83d\udcca Channel statistics\n"
        "\u2022 \ud83d\udd04 Sync pending requests via Telethon\n"
        "\u2022 \ud83d\udee1\ufe0f Superadmin controls\n\n"
        "**Tips:**\n"
        "\u2022 Enable auto-approve to handle requests automatically\n"
        "\u2022 Use drip mode to avoid Telegram rate limits\n"
        "\u2022 Sync periodically to catch requests made while bot was offline\n"
    )
    
    keyboard = [[InlineKeyboardButton("\u00ab Back", callback_data='back_main')]]
    await query.edit_message_text(
        help_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )


async def back_to_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    db = context.application.bot_data.get('db')
    
    channels = await db.get_all_channels()
    total_channels = len(channels) if channels else 0
    total_pending = sum(ch.get('pending_count', 0) for ch in channels) if channels else 0
    
    text = (
        f"\ud83c\udf1f **Telegram Growth Engine**\n"
        f"\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n"
        f"Channels: {total_channels}\n"
        f"Pending Requests: {total_pending}\n"
    )
    
    keyboard = [
        [InlineKeyboardButton("\ud83d\udcfa My Channels", callback_data='list_channels')],
        [InlineKeyboardButton("\u2753 Help", callback_data='help')]
    ]
    
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
