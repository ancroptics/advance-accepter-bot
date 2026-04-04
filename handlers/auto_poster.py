import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

logger = logging.getLogger(__name__)


async def show_auto_poster_menu(update, context):
    query = update.callback_query
    db = context.application.bot_data.get('db')
    user_id = query.from_user.id
    groups = await db.get_auto_post_groups(user_id)
    text = '🤖 AUTO POSTER\n\n'
    if groups:
        for g in groups:
            status = '✅ Active' if g['is_active'] else '⏸️ Paused'
            text += f"👥 {g['chat_title']} — {status}\n"
    else:
        text += 'No groups configured yet.\nAdd the bot to a group to get started.\n'
    buttons = [[InlineKeyboardButton('🔙 Back', callback_data='dashboard')]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))

auto_poster_conv_handler = None
