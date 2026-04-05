import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

async def show_channel_settings(update, context, chat_id, edit=False):
    db = context.application.bot_data.get('db')
    channel = await db.get_channel(chat_id)
    if not channel:
        text = 'Channel not found.'
        kb = InlineKeyboardMarkup([[InlineKeyboardButton('\U0001f519 Back', callback_data='dashboard')]])
        if edit and update.callback_query:
            await update.callback_query.edit_message_text(text, reply_markup=kb)
        else:
            await update.effective_message.reply_text(text, reply_markup=kb)
        return

    auto_approve = '\u2705 ON' if channel.get('auto_approve') else '\u274c OFF'
    approve_mode = channel.get('approve_mode', 'instant').capitalize()
    welcome_dm = '\u2705 ON' if channel.get('welcome_dm_enabled') else '\u274c OFF'
    watermark = '\u2705 ON' if channel.get('watermark_enabled') else '\u274c OFF'
    force_sub = '\u2705 ON' if channel.get('force_subscribe_enabled') else '\u274c OFF'
    cross_promo = '\u2705 ON' if channel.get('cross_promo_enabled') else '\u274c OFF'

    # Get REAL pending count from database
    pending = await db.get_pending_count(chat_id)
    # Also update the cached column
    try:
        await db.update_channel_setting(chat_id, 'pending_requests', pending)
    except Exception:
        pass

    # Drip settings display
    drip_info = ''
    if approve_mode.lower() == 'drip':
        drip_speed = channel.get('drip_speed', 'medium')
        drip_quantity = channel.get('drip_quantity', 50)
        drip_interval = channel.get('drip_interval', 30)
        drip_info = f'Drip Speed: {drip_speed.capitalize()} | Batch: {drip_quantity} every {drip_interval}min\n'

    text = (
        f'\u2699\ufe0f MANAGE: {channel["chat_title"]}\n\n'
        f'\u2501\u2501\u2501 JOIN REQUESTS \u2501\u2501\u2501\n'
        f'Auto-Approve: {auto_approve}\n'
        f'Mode: {approve_mode}\n'
        f'{drip_info}'
        f'Pending: {pending:,}\n\n'
        f'\u2501\u2501\u2501 WELCOME DM \u2501\u2501\u2501\n'
        f'Welcome DM: {welcome_dm}\n\n'
        f'\u2501\u2501\u2501 GROWTH TOOLS \u2501\u2501\u2501\n'
        f'Force Subscribe: {force_sub}\n'
        f'Cross-Promotion: {cross_promo}\n'
        f'Watermark: {watermark}\n'
    )

    cid = chat_id
    auto_approve_text = ('\u274c Disable' if channel.get('auto_approve') else '\u2705 Enable') + ' Auto-Approve'
    welcome_dm_text = ('\u274c' if channel.get('welcome_dm_enabled') else '\u2705') + ' Toggle Welcome DM'
    buttons = [
        # Join requests
        [InlineKeyboardButton(auto_approve_text, callback_data=f'toggle_auto_approve:{cid}')],
        [
            InlineKeyboardButton('\U0001f552 Instant', callback_data=f'approve_mode:{cid}:instant'),
            InlineKeyboardButton('\U0001f4a7 Drip', callback_data=f'approve_mode:{cid}:drip'),
            InlineKeyboardButton('\u270b Manual', callback_data=f'approve_mode:{cid}:manual'),
        ],
    ]
    # FIX 1: Show Drip Settings button when mode is drip
    if approve_mode.lower() == 'drip':
        buttons.append([InlineKeyboardButton('\U0001f4a7 Drip Settings', callback_data=f'drip_settings:{cid}')])
    buttons.extend([
        [InlineKeyboardButton(f'\U0001f4cb Pending: {pending:,}', callback_data=f'pending_requests:{cid}')],
        # Welcome DM
        [InlineKeyboardButton('\U0001f4ac Edit Welcome Message', callback_data=f'edit_welcome:{cid}')],
        [InlineKeyboardButton('\U0001f30e Multi-Language Messages', callback_data=f'language_setup:{cid}')],
        [InlineKeyboardButton('\U0001f441 Preview Welcome DM', callback_data=f'preview_welcome:{cid}')],
        [InlineKeyboardButton(welcome_dm_text, callback_data=f'toggle_welcome_dm:{cid}')],
        # Growth tools
        [InlineKeyboardButton('\U0001f512 Force Subscribe Setup', callback_data=f'force_sub_setup:{cid}')],
        [InlineKeyboardButton('\U0001f504 Cross-Promotion', callback_data=f'cross_promo_setup:{cid}')],
        [InlineKeyboardButton(f'\U0001f3f7\ufe0f Watermark: {watermark}', callback_data=f'toggle_watermark:{cid}')],
        # Analytics
        [InlineKeyboardButton('\U0001f4ca Channel Analytics', callback_data=f'analytics:{cid}')],
        [InlineKeyboardButton('\U0001f4e4 Export Data (CSV)', callback_data=f'export_csv:{cid}')],
        [InlineKeyboardButton('\U0001f519 Back to Dashboard', callback_data='dashboard')],
    ])

    kb = InlineKeyboardMarkup(buttons)
    if edit and update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=kb)
    else:
        await update.effective_message.reply_text(text, reply_markup=kb)
