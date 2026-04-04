import logging
import functools
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
import config

logger = logging.getLogger(__name__)


def channel_owner_only(func):
    @functools.wraps(func)
    async def wrapper(update, context, *args, **kwargs):
        user_id = update.effective_user.id
        db = context.application.bot_data.get('db')
        if not db:
            return
        owner = await db.get_owner(user_id)
        if not owner and user_id not in config.SUPERADMIN_IDS:
            text = 'This feature is for channel owners only. Add me as admin to your channel first!'
            if update.callback_query:
                await update.callback_query.answer(text, show_alert=True)
            else:
                await update.effective_message.reply_text(text)
            return
        return await func(update, context, *args, **kwargs)
    return wrapper


def superadmin_only(func):
    @functools.wraps(func)
    async def wrapper(update, context, *args, **kwargs):
        user_id = update.effective_user.id
        if user_id not in config.SUPERADMIN_IDS:
            return
        return await func(update, context, *args, **kwargs)
    return wrapper


def track_user(func):
    @functools.wraps(func)
    async def wrapper(update, context, *args, **kwargs):
        try:
            user = update.effective_user
            if user:
                db = context.application.bot_data.get('db')
                if db:
                    await db.upsert_end_user(
                        user_id=user.id,
                        username=user.username,
                        first_name=user.first_name,
                        last_name=user.last_name,
                        language_code=user.language_code,
                    )
        except Exception as e:
            logger.error(f'Track user error: {e}')
        return await func(update, context, *args, **kwargs)
    return wrapper


def premium_required(feature):
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(update, context, *args, **kwargs):
            user_id = update.effective_user.id
            if user_id in config.SUPERADMIN_IDS:
                return await func(update, context, *args, **kwargs)
            db = context.application.bot_data.get('db')
            if not db:
                return
            owner = await db.get_owner(user_id)
            tier = owner.get('tier', 'free') if owner else 'free'
            PREMIUM_FEATURES = {
                'force_subscribe', 'drip_approve', 'multi_language',
                'cross_promo', 'export', 'auto_poster', 'clone',
                'remove_watermark', 'scheduled_broadcast'
            }
            if tier == 'free' and feature in PREMIUM_FEATURES:
                text = (
                    '\U0001f512 This feature requires Premium!\n\n'
                    'Upgrade to unlock:\n'
                    '\u2705 Force Subscribe\n'
                    '\u2705 Drip Approve\n'
                    '\u2705 Remove Watermark\n'
                    '\u2705 Multi-Language DMs\n'
                    '\u2705 Cross-Promotion\n'
                    '...and more!\n'
                )
                buttons = [
                    [InlineKeyboardButton('\U0001f48e Upgrade to Premium', callback_data='upgrade_to:premium')],
                    [InlineKeyboardButton('\U0001f4bc Upgrade to Business', callback_data='upgrade_to:business')],
                    [InlineKeyboardButton('\U0001f519 Back', callback_data='dashboard')],
                ]
                if update.callback_query:
                    await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))
                else:
                    await update.effective_message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))
                return
            return await func(update, context, *args, **kwargs)
        return wrapper
    return decorator
