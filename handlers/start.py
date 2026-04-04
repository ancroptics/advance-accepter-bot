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

        # Always show dashboard for all users
        from handlers.admin_panel import show_dashboard
        await show_dashboard(update, context, edit=False)

    except Exception as e:
        logger.exception(f'Error in start_handler: {e}')
        try:
            await update.message.reply_text('Something went wrong. Please try /start again.')
        except Exception:
            pass
