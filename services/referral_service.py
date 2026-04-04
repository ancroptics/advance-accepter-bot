import logging
import config

logger = logging.getLogger(__name__)


class ReferralService:
    def __init__(self, db):
        self.db = db

    async def process_referral(self, user_id, referrer_id, bot=None):
        if user_id == referrer_id:
            return False
        existing = await self.db.get_end_user(user_id)
        if existing and existing.get('referrer_id'):
            return False  # already referred
        await self.db.set_referrer(user_id, referrer_id)
        coins = config.DEFAULT_REFERRAL_COINS
        await self.db.award_referral_coins(referrer_id, coins)
        if bot:
            try:
                referrer = await self.db.get_end_user(referrer_id)
                ref_name = referrer.get('first_name', 'Someone') if referrer else 'Someone'
                user = await self.db.get_end_user(user_id)
                user_name = user.get('first_name', 'Someone') if user else 'Someone'
                await bot.send_message(
                    referrer_id,
                    f'\U0001f389 {user_name} joined via your referral link!\n+{coins} coins!'
                )
            except Exception:
                pass
        return True

    async def get_referral_link(self, user_id):
        return f'https://t.me/{config.BOT_USERNAME}?start=ref_{user_id}'
