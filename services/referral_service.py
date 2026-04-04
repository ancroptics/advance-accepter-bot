import logging

logger = logging.getLogger(__name__)


async def generate_referral_link(db, user_id, bot_username):
    """Generate a referral link for a user."""
    return f"https://t.me/{bot_username}?start=ref_{user_id}"


async def handle_referral(db, referrer_id, referred_id):
    """Process a referral - award coins to referrer."""
    try:
        await db.set_referrer(referred_id, referrer_id)
        await db.award_referral_coins(referrer_id, 10)
        return True
    except Exception as e:
        logger.error(f'Referral error: {e}')
        return False


async def get_referral_report(db, user_id):
    """Get referral stats for a user."""
    user = await db.get_end_user(user_id)
    if not user:
        return '\U0001f4ca No referrals yet.'
    count = user.get('referral_count', 0) if user else 0
    coins = user.get('coins', 0) if user else 0
    return f"\U0001f4ca *Referral Stats*\n\n\U0001f465 Total Referrals: {count}\n\U0001f4b0 Coins Earned: {coins}"
