import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler
import config

logger = logging.getLogger(__name__)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_dashboard(update, context, edit=False)

async def show_dashboard(update, context, edit=False):
    user_id = update.effective_user.id
    db = context.application.bot_data.get('db')
    if not db:
        text = 'Bot is still initializing...'
        if edit and update.callback_query:
            await update.callback_query.edit_message_text(text)
        else:
            await update.effective_message.reply_text(text)
        return
    owner = await db.get_owner(user_id)
    if not owner:
        text = ('\U0001f44b Welcome!\n\nTo get started, add this bot as admin to your channel.\n'
                'The bot will automatically detect it and set up management.')
        if edit and update.callback_query:
            await update.callback_query.edit_message_text(text)
        else:
            await update.effective_message.reply_text(text)
        return
    channels = await db.get_owner_channels(user_id)
    tier = owner.get('tier', 'free').upper()
    text = f'\U0001f4ca GROWTH ENGINE DASHBOARD\n\n\U0001f44b Hey {update.effective_user.first_name}!\n\U0001f3f7\ufe0f Plan: {tier}\n\n\u2501\u2501\u2501 YOUR CHANNELS \u2501\u2501\u2501\n\n'
    buttons = []
    if channels:
        for ch in channels:
            auto = '\u2705 Auto: ON' if ch.get('auto_approve') else '\u23f8\ufe0f Auto: OFF'
            text += (f"\U0001f4e2 {ch['chat_title']}\n"
                     f"   \U0001f465 {ch.get('member_count', 0)} | \U0001f4cb {ch.get('pending_requests', 0)} pending\n"
                     f"   {auto}\n\n")        
    else:
        text += 'No channels yet. Add the bot as admin to a channel!\n\n'
    buttons.extend([
        [InlineKeyboardButton('\U0001f4e2 My Channels', callback_data='my_channels')],
        [InlineKeyboardButton('\U0001f4e2 Broadcast', callback_data='broadcast'),
         InlineKeyboardButton('\U0001f4ca Analytics', callback_data='analytics_overview')],
        [InlineKeyboardButton('\U0001f4dd Templates', callback_data='templates_menu'),
         InlineKeyboardButton('\U0001f916 Auto Poster', callback_data='auto_poster_menu')],
    ])
    # Conditionally show Cross-Promo and Clone Bot based on feature flags
    row4 = []
    row4.append(InlineKeyboardButton('\U0001f517 Referral', callback_data='referral_info'))
    if config.ENABLE_CROSS_PROMO:
        row4.append(InlineKeyboardButton('\U0001f504 Cross-Promo', callback_data='cross_promo_setup:0'))
    buttons.append(row4)
    row5 = []
    if config.ENABLE_CLONING:
        row5.append(InlineKeyboardButton('\U0001f9ec Clone Bot', callback_data='clone_bot_menu'))
    row5.append(InlineKeyboardButton('\U0001f48e Premium', callback_data='premium_info'))
    buttons.append(row5)
    buttons.extend([
        [InlineKeyboardButton('\U0001f4ac Support', callback_data='edit_support_overview'),
         InlineKeyboardButton('\u2699\ufe0f Settings', callback_data='settings'),
         InlineKeyboardButton('\u2753 Help', callback_data='help')],
    ])
    # Add superadmin button for superadmins
    if user_id in config.SUPERADMIN_IDS:
        buttons.append([InlineKeyboardButton('\U0001f451 Superadmin Panel', callback_data='superadmin_panel')])

    total_channels = await db.get_total_channel_count()
    text += f'\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\U0001f4ca Platform: {total_channels} channels using Growth Engine'

    reply_markup = InlineKeyboardMarkup(buttons)
    if edit and update.callback_query:
        try:
            await update.callback_query.edit_message_text(text, reply_markup=reply_markup)
        except Exception as e:
            if 'message is not modified' not in str(e).lower():
                raise
    else:
        await update.effective_message.reply_text(text, reply_markup=reply_markup)
