import logging
import io
import csv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


async def show_channel_analytics(update, context, chat_id):
    query = update.callback_query
    db = context.application.bot_data.get('db')
    channel = await db.get_channel(chat_id)
    if not channel:
        return
    stats = await db.get_channel_analytics(chat_id)
    text = (f'\U0001f4ca ANALYTICS \u2014 {channel["chat_title"]}\n\n'
            f'\u2501\u2501\u2501 GROWTH \u2501\u2501\u2501\n'
            f'Today: +{stats.get("today", 0)}\nThis Week: +{stats.get("week", 0)}\n'
            f'This Month: +{stats.get("month", 0)}\nAll Time: +{stats.get("total", 0)}\n\n'
            f'\u2501\u2501\u2501 JOIN REQUESTS \u2501\u2501\u2501\n'
            f'Pending: {channel.get("pending_requests", 0)}\n'
            f'Approved: {channel.get("total_approved", 0)}\n\n'
            f'\u2501\u2501\u2501 WELCOME DM \u2501\u2501\u2501\n'
            f'Sent: {channel.get("total_dms_sent", 0)}\n'
            f'Failed: {channel.get("total_dms_failed", 0)}\n')
    buttons = [
        [InlineKeyboardButton('\U0001f504 Refresh', callback_data=f'refresh_analytics:{chat_id}')],
        [InlineKeyboardButton('\U0001f4e4 Export CSV', callback_data=f'export_csv:{chat_id}')],
        [InlineKeyboardButton('\U0001f519 Back', callback_data=f'manage_channel:{chat_id}')],
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))


async def show_analytics_overview(update, context):
    query = update.callback_query
    user_id = query.from_user.id
    db = context.application.bot_data.get('db')
    channels = await db.get_owner_channels(user_id)
    text = '\U0001f4ca ANALYTICS OVERVIEW\n\n'
    for ch in (channels or []):
        text += f"\U0001f4e2 {ch['chat_title']}: +{ch.get('total_approved', 0)} approved\n"
    buttons = []
    for ch in (channels or []):
        buttons.append([InlineKeyboardButton(f"\U0001f4ca {ch['chat_title']}", callback_data=f"analytics:{ch['chat_id']}")])
    buttons.append([InlineKeyboardButton('\U0001f519 Back', callback_data='dashboard')])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))


async def export_channel_csv(update, context, chat_id):
    query = update.callback_query
    db = context.application.bot_data.get('db')
    data = await db.get_channel_export_data(chat_id)
    if not data:
        await query.answer('No data to export.', show_alert=True)
        return
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=data[0].keys())
    writer.writeheader()
    writer.writerows(data)
    output.seek(0)
    buf = io.BytesIO(output.getvalue().encode())
    buf.name = f'channel_{chat_id}_export.csv'
    await context.bot.send_document(query.from_user.id, buf, caption='\U0001f4e4 Channel data export')
    await query.answer('Export sent!')
