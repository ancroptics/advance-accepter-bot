import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
import config

logger = logging.getLogger(__name__)


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user = update.effective_user
        user_id = user.id
        db = context.application.bot_data.get('db')
        if not db:
            await update.message.reply_text('Bot is initializing. Please try again in a moment.')
            return

        # Process deep link parameters
        args = context.args
        referrer_id = None
        if args:
            param = args[0]
            if param.startswith('ref_'):
                try:
                    referrer_id = int(param[4:])
                    if referrer_id == user_id:
                        referrer_id = None
                except ValueError:
                    pass

        # Upsert end user
        await db.upsert_end_user(
            user_id=user_id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
            language_code=user.language_code,
            source='referral' if referrer_id else 'direct',
        )

        # Process referral
        if referrer_id:
            try:
                existing = await db.get_end_user(user_id)
                if existing and not existing.get('referrer_id'):
                    await db.set_referrer(user_id, referrer_id)
                    await db.award_referral_coins(referrer_id, config.DEFAULT_REFERRAL_COINS)
                    try:
                        await context.bot.send_message(
                            referrer_id,
                            f'\U0001f389 New referral! {user.first_name} joined via your link.\n'
                            f'+{config.DEFAULT_REFERRAL_COINS} coins!'
                        )
                    except Exception:
                        pass
            except Exception as e:
                logger.error(f'Error processing referral: {e}')

        # Check if user is a channel owner
        owner = await db.get_owner(user_id)
        is_superadmin = user_id in config.SUPERADMIN_IDS

        if is_superadmin:
            text = (
                f'\U0001f451 Welcome back, Superadmin!\n\n'
                f'\U0001f680 Growth Engine is running.\n'
            )
            buttons = [
                [InlineKeyboardButton('\U0001f4ca Dashboard', callback_data='dashboard')],
                [InlineKeyboardButton('\U0001f451 Superadmin Panel', callback_data='superadmin_panel')],
            ]
            await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))
        elif owner:
            # Redirect to dashboard
            from handlers.admin_panel import show_dashboard
            await show_dashboard(update, context, edit=False)
        else:
            ref_link = f'https://t.me/{config.BOT_USERNAME}?start=ref_{user_id}'
            text = (
                f'\U0001f44b Hey {user.first_name}!\n\n'
                f'\U0001f680 Welcome to Growth Engine!\n\n'
                f'\U0001f4e2 Channel Owner?\nAdd this bot as admin to your channel to get started!\n\n'
                f'\U0001f517 Your Referral Link:\n{ref_link}\n\n'
                f'Commands:\n'
                f'/help - Help & guide\n'
                f'/referral - Your referral link\n'
                f'/leaderboard - Top referrers\n'
                f'/balance - Check coins\n'
            )
            buttons = [
                [InlineKeyboardButton('\u2753 Help', callback_data='help')],
                [InlineKeyboardButton('\U0001f517 Referral Link', callback_data='referral_info')],
            ]
            await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))

    except Exception as e:
        logger.exception(f'Error in start_handler: {e}')
        try:
            await update.message.reply_text('Something went wrong. Please try /start again.')
        except Exception:
            pass
