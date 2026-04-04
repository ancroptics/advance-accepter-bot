import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


async def ban_user(update, context, user_id, reason=''):
    db = context.application.bot_data.get('db')
    await db.ban_end_user(user_id, reason)
    await update.effective_message.reply_text(f'User {user_id} has been banned.')


async def unban_user(update, context, user_id):
    db = context.application.bot_data.get('db')
    await db.unban_end_user(user_id)
    await update.effective_message.reply_text(f'User {user_id} has been unbanned.')


async def find_user(update, context, search_term):
    db = context.application.bot_data.get('db')
    users = await db.search_users(search_term)
    if not users:
        await update.effective_message.reply_text('No users found.')
        return
    text = 'Search Results:\n\n'
    for u in users[:10]:
        text += f"ID: {u['user_id']} | @{u.get('username', 'N/A')} | {u.get('first_name', '')}\n"
    await update.effective_message.reply_text(text)
