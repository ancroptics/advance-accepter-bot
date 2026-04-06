import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler
import config
from utils.decorators import superadmin_only

logger = logging.getLogger(__name__)

TIER_FEATURES = {
    'free': {
        'max_channels': 1, 'max_clones': 0, 'welcome_media': False,
        'analytics_days': 7, 'watermark_removable': False, 'force_subscribe': False,
        'broadcast_limit': 1000, 'broadcast_daily': 1, 'drip_approve': False,
        'multi_language': False, 'cross_promo': False, 'export': False, 'auto_poster': False,
    },
    'premium': {
        'max_channels': 5, 'max_clones': 1, 'welcome_media': True,
        'analytics_days': 30, 'watermark_removable': True, 'force_subscribe': True,
        'broadcast_limit': 999999, 'broadcast_daily': 999, 'drip_approve': True,
        'multi_language': True, 'cross_promo': True, 'export': True, 'auto_poster': True,
    },
    'business': {
        'max_channels': 999, 'max_clones': 5, 'welcome_media': True,
        'analytics_days': 90, 'watermark_removable': True, 'force_subscribe': True,
        'broadcast_limit': 999999, 'broadcast_daily': 999, 'drip_approve': True,
        'multi_language': True, 'cross_promo': True, 'export': True, 'auto_poster': True,
    },
}


async def show_premium_info(update, context):
    query = update.callback_query
    user_id = query.from_user.id
    db = context.application.bot_data.get('db')
    owner = await db.get_owner(user_id)
    current_tier = owner['tier'] if owner else 'free'
    is_superadmin = user_id in config.SUPERADMIN_IDS
    if is_superadmin:
        current_tier = 'superadmin'
    text = (
        '\U0001f48e PREMIUM PLANS\n\n'
        f'Current Plan: {current_tier.upper()}\n\n'
        '\u2501\u2501\u2501 FREE \u2501\u2501\u2501\n'
        '\u2022 1 channel\n\u2022 Basic welcome DM (text only)\n'
        '\u2022 7-day analytics\n\u2022 Watermark always on\n\n'
        '\u2501\u2501\u2501 PREMIUM - \u20b9199/mo \u2501\u2501\u2501\n'
        '\u2022 5 channels\n\u2022 1 bot clone\n'
        '\u2022 Rich welcome DM (photo/video/buttons)\n'
        '\u2022 30-day analytics + charts\n'
        '\u2022 Remove watermark\n\u2022 Force subscribe\n'
        '\u2022 Unlimited broadcasts\n\u2022 Drip approve\n'
        '\u2022 Multi-language DMs\n\u2022 Cross-promotion\n\u2022 CSV export\n\n'
        '\u2501\u2501\u2501 BUSINESS - \u20b9499/mo \u2501\u2501\u2501\n'
        '\u2022 Unlimited channels\n\u2022 5 bot clones\n'
        '\u2022 90-day analytics\n\u2022 Custom branding\n'
        '\u2022 Priority support\n\u2022 Everything in Premium\n'
    )
    buttons = []
    if is_superadmin:
        buttons.append([InlineKeyboardButton('\U0001f451 SUPERADMIN - All Features Unlocked', callback_data='dashboard')])
    elif current_tier == 'free':
        buttons.append([InlineKeyboardButton('\U0001f48e Upgrade to Premium', callback_data='upgrade_to:premium')])
        buttons.append([InlineKeyboardButton('\U0001f4bc Upgrade to Business', callback_data='upgrade_to:business')])
    elif current_tier == 'premium':
        buttons.append([InlineKeyboardButton('\U0001f4bc Upgrade to Business', callback_data='upgrade_to:business')])
    buttons.append([InlineKeyboardButton('\U0001f519 Back', callback_data='dashboard')])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))


async def handle_upgrade(update, context):
    query = update.callback_query
    tier = query.data.split(':')[1]
    price = '199' if tier == 'premium' else '499'
    upi_id = getattr(config, 'UPI_ID', 'payment@upi')
    text = (
        f'\U0001f48e {tier.upper()} Plan - \u20b9{price}/month\n\n'
        'Pay via UPI:\n'
        f'\U0001f4f1 UPI ID: {upi_id}\n\n'
        'After payment, send screenshot here.\n'
        'Admin will verify and activate within 1 hour.\n\n'
        '\u26a0\ufe0f Do NOT send fake screenshots.'
    )
    buttons = [
        [InlineKeyboardButton('\U0001f519 Back', callback_data='premium_info')],
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))


def get_tier_features(tier):
    # When premium is disabled globally, everyone gets premium features
    if not getattr(config, 'ENABLE_PREMIUM', True):
        return TIER_FEATURES.get('premium', TIER_FEATURES['free'])
    return TIER_FEATURES.get(tier, TIER_FEATURES['free'])


def get_effective_tier(owner, user_id):
    """Get effective tier considering premium toggle."""
    if not getattr(config, 'ENABLE_PREMIUM', True):
        return 'premium'  # Everyone is premium when disabled
    if user_id in config.SUPERADMIN_IDS:
        return 'superadmin'
    return owner.get('tier', 'free') if owner else 'free'


@superadmin_only
async def activate_premium_handler(update, context):
    args = context.args
    if len(args) < 2:
        await update.message.reply_text('Usage: /activate_premium <user_id> <tier> [days]')
        return
    try:
        target_id = int(args[0])
        tier = args[1].lower()
        days = int(args[2]) if len(args) > 2 else 30
        if tier not in ('premium', 'business'):
            await update.message.reply_text('Tier must be premium or business.')
            return
        db = context.application.bot_data.get('db')
        await db.activate_premium(target_id, tier, days)
        await update.message.reply_text(f'\u2705 Activated {tier} for user {target_id} for {days} days.')
    except Exception as e:
        await update.message.reply_text(f'Error: {e}')


@superadmin_only
async def deactivate_premium_handler(update, context):
    args = context.args
    if not args:
        await update.message.reply_text('Usage: /deactivate_premium <user_id>')
        return
    try:
        target_id = int(args[0])
        db = context.application.bot_data.get('db')
        await db.deactivate_premium(target_id)
        await update.message.reply_text(f'\u2705 Deactivated premium for user {target_id}.')
    except Exception as e:
        await update.message.reply_text(f'Error: {e}')
