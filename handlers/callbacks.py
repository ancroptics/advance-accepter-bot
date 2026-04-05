import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database.models import db, TIER_LIMITS

logger = logging.getLogger(__name__)


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Main callback query handler - routes to appropriate handler."""
    query = update.callback_query
    data = query.data
    user_id = query.from_user.id

    # Route based on callback data prefix
    if data.startswith('approve_mode:'):
        await handle_approve_mode(query, data)
    elif data.startswith('set_drip:'):
        await handle_drip_settings(query, data)
    elif data.startswith('toggle_dm:'):
        await handle_toggle_dm(query, data)
    elif data.startswith('channel:'):
        await handle_channel_select(query, data, user_id)
    elif data.startswith('settings:'):
        await handle_settings(query, data, user_id)
    elif data.startswith('batch_select:') or data.startswith('bapprove_') or data.startswith('bdecline_') or data == 'batch_all' or data == 'batch_back':
        from handlers.batch_approve import batch_button_handler
        await batch_button_handler(update, context)
    elif data.startswith('tier:'):
        await handle_tier_select(query, data)
    elif data.startswith('admin:'):
        await handle_admin_action(query, data, user_id, context)
    elif data.startswith('clone:'):
        from handlers.clone_bot import clone_callback_handler
        await clone_callback_handler(update, context)
    elif data.startswith('export:'):
        await handle_export(query, data, user_id, context)
    elif data.startswith('analytics:'):
        from handlers.analytics_view import analytics_callback_handler
        await analytics_callback_handler(update, context)
    elif data.startswith('broadcast:'):
        from handlers.broadcast import broadcast_callback_handler
        await broadcast_callback_handler(update, context)
    elif data.startswith('lang:'):
        from handlers.language_mgmt import language_callback_handler
        await language_callback_handler(update, context)
    elif data.startswith('template:'):
        from handlers.template_mgmt import template_callback_handler
        await template_callback_handler(update, context)
    elif data.startswith('premium:'):
        from handlers.premium import premium_callback_handler
        await premium_callback_handler(update, context)
    elif data == 'my_channels':
        await show_my_channels(query, user_id)
    elif data == 'main_menu':
        await show_main_menu(query, user_id)
    elif data == 'help':
        await show_help(query)
    else:
        await query.answer("Unknown action")


async def handle_approve_mode(query, data):
    """Handle approve mode changes."""
    parts = data.split(':')
    if len(parts) < 3:
        await query.answer("Invalid data")
        return

    chat_id = int(parts[1])
    mode = parts[2]

    await db.update_channel(chat_id, approve_mode=mode)
    await query.answer(f"Mode set to: {mode}")

    # Refresh settings view
    channel = await db.get_channel(chat_id)
    if channel:
        await _show_channel_settings(query, channel)


async def handle_drip_settings(query, data):
    """Handle drip rate/interval changes."""
    parts = data.split(':')
    if len(parts) < 4:
        await query.answer("Invalid data")
        return

    chat_id = int(parts[1])
    setting = parts[2]  # 'rate' or 'interval'
    value = int(parts[3])

    if setting == 'rate':
        await db.update_channel(chat_id, drip_rate=value)
        await query.answer(f"Drip rate set to: {value}")
    elif setting == 'interval':
        await db.update_channel(chat_id, drip_interval=value)
        await query.answer(f"Drip interval set to: {value}s")

    channel = await db.get_channel(chat_id)
    if channel:
        await _show_channel_settings(query, channel)


async def handle_toggle_dm(query, data):
    """Toggle DM for a channel."""
    parts = data.split(':')
    chat_id = int(parts[1])

    channel = await db.get_channel(chat_id)
    if not channel:
        await query.answer("Channel not found")
        return

    new_state = not channel.get('dm_enabled', False)
    await db.update_channel(chat_id, dm_enabled=new_state)
    state_text = "enabled" if new_state else "disabled"
    await query.answer(f"Welcome DM {state_text}")

    channel = await db.get_channel(chat_id)
    if channel:
        await _show_channel_settings(query, channel)


async def handle_channel_select(query, data, user_id):
    """Handle channel selection from list."""
    parts = data.split(':')
    chat_id = int(parts[1])

    channel = await db.get_channel(chat_id)
    if not channel:
        await query.answer("Channel not found")
        return

    if channel.get('owner_id') != user_id:
        await query.answer("Not your channel")
        return

    await _show_channel_settings(query, channel)


async def handle_settings(query, data, user_id):
    """Handle settings sub-menu navigation."""
    parts = data.split(':')
    action = parts[1]
    chat_id = int(parts[2]) if len(parts) > 2 else None

    if action == 'mode' and chat_id:
        await _show_mode_options(query, chat_id)
    elif action == 'drip' and chat_id:
        await _show_drip_options(query, chat_id)
    elif action == 'dm' and chat_id:
        await _show_dm_settings(query, chat_id)
    elif action == 'back' and chat_id:
        channel = await db.get_channel(chat_id)
        if channel:
            await _show_channel_settings(query, channel)


async def handle_tier_select(query, data):
    """Handle tier selection (admin only)."""
    parts = data.split(':')
    user_id = int(parts[1])
    tier = parts[2]

    await db.set_user_tier(user_id, tier)
    await query.answer(f"Tier set to: {tier}")
    await query.edit_message_text(f"\u2705 User {user_id} tier updated to <b>{tier}</b>", parse_mode='HTML')


async def handle_admin_action(query, data, user_id, context):
    """Handle admin panel actions."""
    import os
    ADMIN_IDS = [int(x) for x in os.getenv('ADMIN_IDS', '').split(',') if x.strip()]
    if user_id not in ADMIN_IDS:
        await query.answer("Not authorized")
        return

    parts = data.split(':')
    action = parts[1]

    if action == 'stats':
        stats = await db.get_global_stats()
        text = (
            "<b>\U0001f4ca Global Statistics</b>\n\n"
            f"\U0001f465 Users: <b>{stats['total_users']}</b>\n"
            f"\U0001f4e2 Channels: <b>{stats['total_channels']}</b>\n"
            f"\U0001f4e8 Total requests: <b>{stats['total_requests']}</b>\n"
            f"\u2705 Approved: <b>{stats['total_approved']}</b>\n"
            f"\u23f3 Pending: <b>{stats['total_pending']}</b>\n"
            f"\U0001f4c5 Today approved: <b>{stats['today_approved']}</b>"
        )
        await query.edit_message_text(text, parse_mode='HTML')

    elif action == 'users':
        users = await db.get_all_users(limit=20)
        if not users:
            await query.edit_message_text("No users found.")
            return

        text = "<b>\U0001f465 Recent Users</b>\n\n"
        for u in users:
            tier_emoji = {'free': '\U0001f7e2', 'pro': '\U0001f535', 'enterprise': '\U0001f7e1'}.get(u.get('tier', 'free'), '\u26aa')
            text += f"{tier_emoji} <code>{u['user_id']}</code> - {u.get('username', 'N/A')} ({u.get('tier', 'free')})\n"

        await query.edit_message_text(text, parse_mode='HTML')

    elif action == 'broadcast':
        from handlers.broadcast import start_broadcast
        await start_broadcast(query, context)


async def handle_export(query, data, user_id, context):
    """Handle data export requests."""
    parts = data.split(':')
    chat_id = int(parts[1])

    # Check tier
    user = await db.get_user(user_id)
    tier = user.get('tier', 'free') if user else 'free'
    limits = TIER_LIMITS.get(tier, TIER_LIMITS['free'])

    if not limits.get('export'):
        await query.answer("Export requires Pro tier!", show_alert=True)
        return

    csv_data = await db.export_requests_csv(chat_id)
    if not csv_data:
        await query.answer("No data to export")
        return

    import io
    file = io.BytesIO(csv_data.encode())
    file.name = f"requests_{chat_id}.csv"

    await context.bot.send_document(
        chat_id=query.from_user.id,
        document=file,
        caption=f"\U0001f4e4 Export for channel {chat_id}"
    )
    await query.answer("Export sent!")


async def show_my_channels(query, user_id):
    """Show user's channels list."""
    channels = await db.get_user_channels(user_id)

    if not channels:
        await query.edit_message_text(
            "You haven't added any channels yet.\nAdd me as admin to your channel and I'll detect it automatically!"
        )
        return

    text = "<b>\U0001f4e2 Your Channels</b>\n\n"
    keyboard = []

    for ch in channels:
        title = ch.get('chat_title', 'Unknown')
        mode = ch.get('approve_mode', 'instant')
        pending = ch.get('pending_requests', 0)
        approved = ch.get('total_approved', 0)
        mode_emoji = {'instant': '\u26a1', 'drip': '\U0001f4a7', 'manual': '\u270b'}.get(mode, '\u2753')

        text += f"{mode_emoji} <b>{title}</b>\n"
        text += f"   Pending: {pending} | Approved: {approved}\n\n"

        keyboard.append([InlineKeyboardButton(
            f"\u2699\ufe0f {title}", callback_data=f"channel:{ch['chat_id']}"
        )])

    keyboard.append([InlineKeyboardButton("\u2b05 Back", callback_data="main_menu")])

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )


async def show_main_menu(query, user_id):
    """Show main menu."""
    user = await db.get_user(user_id)
    tier = user.get('tier', 'free') if user else 'free'
    tier_emoji = {'free': '\U0001f7e2 Free', 'pro': '\U0001f535 Pro', 'enterprise': '\U0001f7e1 Enterprise'}.get(tier, 'Free')

    text = (
        f"<b>\U0001f916 Advance Accepter Bot</b>\n\n"
        f"Tier: <b>{tier_emoji}</b>\n\n"
        f"Manage your channels and auto-approve settings."
    )

    keyboard = [
        [InlineKeyboardButton("\U0001f4e2 My Channels", callback_data="my_channels")],
        [InlineKeyboardButton("\U0001f4cb Batch Approve", callback_data="batch_back")],
        [InlineKeyboardButton("\U0001f4ca Analytics", callback_data="analytics:overview")],
        [InlineKeyboardButton("\U0001f4e3 Broadcast", callback_data="broadcast:start")],
        [InlineKeyboardButton("\u2753 Help", callback_data="help")],
    ]

    import os
    ADMIN_IDS = [int(x) for x in os.getenv('ADMIN_IDS', '').split(',') if x.strip()]
    if user_id in ADMIN_IDS:
        keyboard.append([InlineKeyboardButton("\U0001f6e0 Admin Panel", callback_data="admin:panel")])

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )


async def show_help(query):
    """Show help message."""
    text = (
        "<b>\u2753 Help & Commands</b>\n\n"
        "<b>Basic Commands:</b>\n"
        "/start - Start bot & main menu\n"
        "/help - Show this help\n"
        "/batch - Batch approve panel\n"
        "/stats - Your statistics\n"
        "/settings - Channel settings\n\n"
        "<b>How it works:</b>\n"
        "1. Add me as admin to your channel\n"
        "2. I'll auto-detect the channel\n"
        "3. Set your preferred approve mode\n"
        "4. I'll handle join requests automatically!\n\n"
        "<b>Approve Modes:</b>\n"
        "\u26a1 Instant - Approve immediately\n"
        "\U0001f4a7 Drip - Approve in batches over time\n"
        "\u270b Manual - Queue for manual review\n\n"
        "<b>Pro Features:</b>\n"
        "\u2022 Welcome DM messages\n"
        "\u2022 Broadcast to members\n"
        "\u2022 Analytics & export\n"
        "\u2022 Clone settings across channels"
    )

    keyboard = [[InlineKeyboardButton("\u2b05 Back", callback_data="main_menu")]]

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )


async def _show_channel_settings(query, channel):
    """Show settings for a specific channel."""
    chat_id = channel['chat_id']
    title = channel.get('chat_title', 'Unknown')
    mode = channel.get('approve_mode', 'instant')
    drip_rate = channel.get('drip_rate', 50)
    drip_interval = channel.get('drip_interval', 30)
    dm_enabled = channel.get('dm_enabled', False)
    pending = channel.get('pending_requests', 0)
    total_approved = channel.get('total_approved', 0)
    total_declined = channel.get('total_declined', 0)

    mode_emoji = {'instant': '\u26a1', 'drip': '\U0001f4a7', 'manual': '\u270b'}.get(mode, '\u2753')
    dm_status = '\u2705 ON' if dm_enabled else '\u274c OFF'

    text = (
        f"<b>\u2699\ufe0f {title}</b>\n\n"
        f"{mode_emoji} Mode: <b>{mode}</b>\n"
        f"\U0001f4a7 Drip: {drip_rate} per {drip_interval}s\n"
        f"\U0001f4e8 DM: {dm_status}\n\n"
        f"<b>Stats:</b>\n"
        f"\u23f3 Pending: {pending}\n"
        f"\u2705 Approved: {total_approved}\n"
        f"\u274c Declined: {total_declined}"
    )

    keyboard = [
        [InlineKeyboardButton(f"{mode_emoji} Approve Mode", callback_data=f"settings:mode:{chat_id}")],
        [InlineKeyboardButton("\U0001f4a7 Drip Settings", callback_data=f"settings:drip:{chat_id}")],
        [InlineKeyboardButton(f"\U0001f4e8 Welcome DM ({dm_status})", callback_data=f"toggle_dm:{chat_id}")],
        [InlineKeyboardButton("\U0001f4ca Analytics", callback_data=f"analytics:channel:{chat_id}")],
        [InlineKeyboardButton("\U0001f4e4 Export Data", callback_data=f"export:{chat_id}")],
        [InlineKeyboardButton("\U0001f4cb Batch Approve", callback_data=f"batch_select:{chat_id}")],
        [InlineKeyboardButton("\u2b05 Back", callback_data="my_channels")],
    ]

    try:
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )
    except Exception:
        pass


async def _show_mode_options(query, chat_id):
    """Show approve mode selection."""
    text = "<b>Select Approve Mode:</b>"
    keyboard = [
        [InlineKeyboardButton("\u26a1 Instant", callback_data=f"approve_mode:{chat_id}:instant")],
        [InlineKeyboardButton("\U0001f4a7 Drip Feed", callback_data=f"approve_mode:{chat_id}:drip")],
        [InlineKeyboardButton("\u270b Manual", callback_data=f"approve_mode:{chat_id}:manual")],
        [InlineKeyboardButton("\u2b05 Back", callback_data=f"settings:back:{chat_id}")],
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')


async def _show_drip_options(query, chat_id):
    """Show drip rate and interval options."""
    channel = await db.get_channel(chat_id)
    current_rate = channel.get('drip_rate', 50) if channel else 50
    current_interval = channel.get('drip_interval', 30) if channel else 30

    text = (
        f"<b>\U0001f4a7 Drip Settings</b>\n\n"
        f"Current: <b>{current_rate}</b> approvals every <b>{current_interval}s</b>\n\n"
        f"Set batch size:"
    )

    keyboard = [
        [
            InlineKeyboardButton("10", callback_data=f"set_drip:{chat_id}:rate:10"),
            InlineKeyboardButton("25", callback_data=f"set_drip:{chat_id}:rate:25"),
            InlineKeyboardButton("50", callback_data=f"set_drip:{chat_id}:rate:50"),
            InlineKeyboardButton("100", callback_data=f"set_drip:{chat_id}:rate:100"),
        ],
        [InlineKeyboardButton("\u23f1 Interval:", callback_data="noop")],
        [
            InlineKeyboardButton("15s", callback_data=f"set_drip:{chat_id}:interval:15"),
            InlineKeyboardButton("30s", callback_data=f"set_drip:{chat_id}:interval:30"),
            InlineKeyboardButton("60s", callback_data=f"set_drip:{chat_id}:interval:60"),
            InlineKeyboardButton("120s", callback_data=f"set_drip:{chat_id}:interval:120"),
        ],
        [InlineKeyboardButton("\u2b05 Back", callback_data=f"settings:back:{chat_id}")],
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')


async def _show_dm_settings(query, chat_id):
    """Show DM template settings."""
    channel = await db.get_channel(chat_id)
    dm_enabled = channel.get('dm_enabled', False) if channel else False
    template = channel.get('dm_template', '') if channel else ''

    status = '\u2705 Enabled' if dm_enabled else '\u274c Disabled'
    template_preview = template[:100] + '...' if len(template) > 100 else (template or 'Not set')

    text = (
        f"<b>\U0001f4e8 Welcome DM Settings</b>\n\n"
        f"Status: {status}\n"
        f"Template: <code>{template_preview}</code>\n\n"
        f"Use /setdm {{channel_id}} {{message}} to set template"
    )

    keyboard = [
        [InlineKeyboardButton(
            f"{'\u274c Disable' if dm_enabled else '\u2705 Enable'} DM",
            callback_data=f"toggle_dm:{chat_id}"
        )],
        [InlineKeyboardButton("\u2b05 Back", callback_data=f"settings:back:{chat_id}")],
    ]

    try:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
    except Exception:
        pass
