import logging
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, MessageHandler, filters, CallbackQueryHandler

logger = logging.getLogger(__name__)

LANGUAGES = {
    'en': '🇬🇧 English', 'hi': '🇮🇳 Hindi', 'ar': '🇸🇦 Arabic',
    'es': '🇪🇸 Spanish', 'pt': '🇧🇷 Portuguese', 'ru': '🇷🇺 Russian',
    'fr': '🇫🇷 French', 'de': '🇩🇪 German', 'zh': '🇨🇳 Chinese',
    'ja': '🇯🇵 Japanese', 'ko': '🇰🇷 Korean', 'tr': '🇹🇷 Turkish',
}

WAITING_LANG_MESSAGE = 1


async def show_language_menu(update, context, chat_id):
    query = update.callback_query
    db = context.application.bot_data.get('db')
    channel = await db.get_channel(chat_id)
    if not channel:
        return
    i18n = channel.get('welcome_messages_i18n') or {}
    text = f"🌐 Multi-Language Welcome DMs\nChannel: {channel['chat_title']}\n\n"
    text += f"Default (English): ✅ Set\n"
    for code, name in LANGUAGES.items():
        if code == 'en':
            continue
        status = '✅ Set' if code in i18n else '❌ Not set'
        text += f"{name}: {status}\n"
    buttons = []
    for code, name in LANGUAGES.items():
        if code == 'en':
            continue
        buttons.append([InlineKeyboardButton(f"{'✏️' if code in i18n else '➕'} {name}", callback_data=f"set_lang_msg:{chat_id}:{code}")])
    buttons.append([InlineKeyboardButton('🔙 Back', callback_data=f'manage_channel:{chat_id}')])
    if query:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))
    else:
        await update.effective_message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))

language_conv_handler = None
