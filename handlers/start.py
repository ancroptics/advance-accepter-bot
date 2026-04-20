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

        # Maintenance mode check
        if user_id not in config.SUPERADMIN_IDS:
            try:
                maint_raw = await db.get_platform_setting('MAINTENANCE_MODE', 'false')
                if isinstance(maint_raw, str) and maint_raw.lower() == 'true':
                    await update.message.reply_text(
                        '\U0001f6a7 Bot is currently under maintenance.\n\n'
                        'Please try again later. We apologize for the inconvenience.'
                    )
                    return
            except Exception:
                pass

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

        # Upsert owner so dashboard is accessible for this user
        try:
            await db.upsert_owner(
                user_id=user_id,
                username=user.username,
                first_name=user.first_name,
                last_name=user.last_name,
            )
        except Exception as e:
            logger.error(f'upsert_owner failed: {e}')

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
                    referrer_data = await db.get_end_user(referrer_id)
                    ref_count = referrer_data.get('referral_count', 0) if referrer_data else 0
                    refs_per_slot = getattr(config, 'REFERRALS_PER_SLOT', 3)
                    slot_msg = ''
                    if ref_count > 0 and ref_count % refs_per_slot == 0:
                        bonus_slots = ref_count // refs_per_slot
                        slot_msg = f'\n\n\U0001f513 NEW SLOT UNLOCKED! You now have {bonus_slots} bonus channel slot(s)!'
                    try:
                        await context.bot.send_message(
                            referrer_id,
                            f'\U0001f389 New referral! {user.first_name} joined via your link.\n'
                            f'+{config.DEFAULT_REFERRAL_COINS} coins!{slot_msg}'
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
