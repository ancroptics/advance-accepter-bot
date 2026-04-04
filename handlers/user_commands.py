import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
import config

logger = logging.getLogger(__name__)


async def help_handler(update, context):
    text = (
        '\u2753 HELP\n\n'
        '\U0001f680 Growth Engine Bot\n\n'
        'Commands:\n'
        '/start - Start the bot\n'
        '/dashboard - Channel owner dashboard\n'
        '/help - This help message\n'
        '/referral - Your referral link & stats\n'
        '/leaderboard - Top referrers\n'
        '/balance - Your coin balance\n'
        '/mystats - Your activity stats\n'
        '/broadcast - Send broadcast (channel owners)\n\n'
        'To get started as a channel owner, add this bot as admin to your channel!\n'
    )
    if update.callback_query:
        await update.callback_query.edit_message_text(text,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('\U0001f519 Back', callback_data='dashboard')]]))
    else:
        await update.message.reply_text(text)


async def referral_handler(update, context):
    user_id = update.effective_user.id
    db = context.application.bot_data.get('db')
    user = await db.get_end_user(user_id)
    ref_link = f'https://t.me/{config.BOT_USERNAME}?start=ref_{user_id}'
    coins = user.get('coins', 0) if user else 0
    ref_count = user.get('referral_count', 0) if user else 0
    text = (
        f'\U0001f517 YOUR REFERRAL LINK\n\n'
        f'{ref_link}\n\n'
        f'\U0001f465 Referrals: {ref_count}\n'
        f'\U0001f4b0 Coins: {coins}\n\n'
        f'Share this link to earn coins!\n'
        f'Each referral = {config.DEFAULT_REFERRAL_COINS} coins'
    )
    if update.callback_query:
        await update.callback_query.edit_message_text(text,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('\U0001f519 Back', callback_data='dashboard')]]))
    else:
        await update.message.reply_text(text)


async def leaderboard_handler(update, context):
    db = context.application.bot_data.get('db')
    top = await db.get_top_referrers(limit=10)
    text = '\U0001f3c6 TOP REFERRERS\n\n'
    for i, u in enumerate(top or [], 1):
        name = u.get('first_name', 'Anonymous')
        text += f'{i}. {name} - {u.get("referral_count", 0)} referrals ({u.get("coins", 0)} coins)\n'
    if not top:
        text += 'No referrals yet!\n'
    await update.message.reply_text(text)


async def balance_handler(update, context):
    user_id = update.effective_user.id
    db = context.application.bot_data.get('db')
    user = await db.get_end_user(user_id)
    coins = user.get('coins', 0) if user else 0
    tier = user.get('tier', '\U0001f949 Bronze') if user else '\U0001f949 Bronze'
    text = f'\U0001f4b0 BALANCE\n\nCoins: {coins}\nTier: {tier}\n'
    await update.message.reply_text(text)


async def mystats_handler(update, context):
    user_id = update.effective_user.id
    db = context.application.bot_data.get('db')
    user = await db.get_end_user(user_id)
    if not user:
        await update.message.reply_text('No stats yet. Join a channel to get started!')
        return
    text = (
        f'\U0001f4ca MY STATS\n\n'
        f'Channels Joined: {user.get("total_channels_joined", 0)}\n'
        f'Referrals: {user.get("referral_count", 0)}\n'
        f'Coins: {user.get("coins", 0)}\n'
        f'Tier: {user.get("tier", "Bronze")}\n'
        f'Member Since: {user.get("first_seen_at", "Unknown")}\n'
    )
    await update.message.reply_text(text)
