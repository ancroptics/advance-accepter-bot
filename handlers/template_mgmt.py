import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, MessageHandler, filters, CallbackQueryHandler

logger = logging.getLogger(__name__)


async def show_templates_menu(update, context):
    query = update.callback_query
    db = context.application.bot_data.get('db')
    user_id = query.from_user.id
    templates = await db.get_templates(user_id)
    text = '📝 MESSAGE TEMPLATES\n\n'
    if templates:
        for t in templates:
            text += f"• {t['name']} (used {t['use_count']} times)\n"
    else:
        text += 'No templates yet. Create one during broadcast.\n'
    buttons = [
        [InlineKeyboardButton('🔙 Back', callback_data='dashboard')]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))

template_conv_handler = None
