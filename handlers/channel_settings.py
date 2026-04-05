import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

logger = logging.getLogger(__name__)

# Drip presets
DRIP_PRESETS = {
    'slow': {'rate': 10, 'interval': 60, 'label': '🐌 Slow (10/60 min)'},
    'medium': {'rate': 50, 'interval': 30, 'label': '⚡ Medium (50/30 min)'},
    'fast': {'rate': 200, 'interval': 15, 'label': '🚨 Fast (200/15 min)'},
    'turbo': {'rate': 500, 'interval': 10, 'label': '🚀 Turbo (500/10 min)'},
}


async def show_channel_settings(update, context, channel):
    """Show settings panel for a specific channel."""
    query = update.callback_query
    chat_id = channel['chat_id']
    title = channel.get('chat_title', 'Unknown')
    mode = channel.get('approve_mode', 'instant')
    pending = channel.get('pending_requests', 0)
    dm_enabled = channel.get('dm_enabled', False)
    dm_template = channel.get('dm_template', '')
    drip_rate = channel.get('drip_rate', 50)
    drip_interval = channel.get('drip_interval', 30)

    mode_emoji = {'instant': '⚡', 'drip': '💧', 'manual': '✋'}.get(mode, '⚡')

    text = (
        f"<⃣🔁️ <b>{title}</b>\n\n"
        f"📛 Chat ID: <code>{chat_id}</code>\n"
        f"{mode_emoji} Mode: <b>{mode.title()}</b>\n"
        f"⏳️ Pending: <b>{pending}</b>\n"
    )

    if mode == 'drip':
        text += f"💧 Drip: <b>{drip_rate}</b> per <b>{drip_interval}</b> min\n"

    text += f"\n✉ DM: <b>{'ON' if dm_enabled else 'OFF'}</b>\n"

    if dm_enabled and dm_template:
        preview = dm_template[:60] + '...' if len(dm_template) > 60 else dm_template
        text += f"📝 <i>{preview}</i>\n"

    # Build keyboard
    keyboard = []

    # Mode buttons
    keyboard.append([
        InlineKeyboardButton("<⚡ Instant" if mode == 'instant' else "⚡ Instant",
                             callback_data=f"set_mode:{chat_id}:instant"),
        InlineKeyboardButton("<💧 Drip" if mode == 'drip' else "💧 Drip",
                             callback_data=f"set_mode:{chat_id}:drip"),
        InlineKeyboardButton("<✋ Manual" if mode == 'manual' else "✋ Manual",
                             callback_data=f"set_mode:{chat_id}:manual"),
    ])

    # Drip presets (show only in drip mode)
    if mode == 'drip':
        preset_row = []
        for key, preset in DRIP_PRESETS.items():
            is_active = drip_rate == preset['rate'] and drip_interval == preset['interval']
            label = f"<{preset['label']}" if is_active else preset['label']
            preset_row.append(InlineKeyboardButton(
                label, callback_data=f"drip_preset:{chat_id}:{key}"))
        # Split into 2 rows
        keyboard.append(preset_row[:2])
        keyboard.append(preset_row[2:])

    # DM toggle
    dm_label = "❌ Disable DM" if dm_enabled else "✩ Enable DM"
    keyboard.append([
        InlineKeyboardButton(dm_label, callback_data=f"toggle_dm:{chat_id}"),
        InlineKeyboardButton("✏ Set DM Text", callback_data=f"set_dm:{chat_id}"),
    ])

    # Action buttons
    keyboard.append([
        InlineKeyboardButton("📊 Analytics", callback_data=f"analytics:{chat_id}"),
        InlineKeyboardButton("📤 Export CSV", callback_data=f"export:{chat_id}"),
    ])

    keyboard.append([
        InlineKeyboardButton("📢 Broadcast", callback_data=f"broadcast:{chat_id}"),
        InlineKeyboardButton("<✭ Remove", callback_data=f"remove_ch:{chat_id}"),
    ])

    keyboard.append([InlineKeyboardButton("⬅ Back", callback_data="my_channels")])

    await query.edit_message_text(
        text=text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )
