import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

CATEGORIES = ['Tech', 'Crypto', 'Education', 'Entertainment', 'News', 'Finance', 'Lifestyle', 'Gaming', 'Other']


async def show_cross_promo_menu(update, context, chat_id):
    query = update.callback_query
    db = context.application.bot_data.get('db')
    channel = await db.get_channel(chat_id)
    if not channel:
        return
    enabled = channel.get('cross_promo_enabled', False)
    category = channel.get('cross_promo_category', 'Other')
    promo_text = channel.get('cross_promo_text', '')
    status = '🟢 Enabled' if enabled else '🔴 Disabled'
    text = (f"🔄 CROSS-PROMOTION\n\n"
            f"Status: {status}\n"
            f"Category: {category}\n"
            f"Promo text: {promo_text or 'Not set'}\n\n"
            f"When another channel in your category sends welcome DMs, "
            f"your channel gets mentioned. And vice versa!")
    buttons = [
        [InlineKeyboardButton(f"{'🔴 Disable' if enabled else '🟢 Enable'}", callback_data=f'toggle_cross_promo:{chat_id}')],
    ]
    cat_buttons = []
    for cat in CATEGORIES:
        marker = ' ✅' if cat == category else ''
        cat_buttons.append(InlineKeyboardButton(f"{cat}{marker}", callback_data=f'set_promo_cat:{chat_id}:{cat}'))
    for i in range(0, len(cat_buttons), 3):
        buttons.append(cat_buttons[i:i+3])
    buttons.append([InlineKeyboardButton('🔙 Back', callback_data=f'manage_channel:{chat_id}')])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))
