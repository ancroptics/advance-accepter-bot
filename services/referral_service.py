import logging
from database.models import get_referral_stats, create_referral, process_referral_reward

logger = logging.getLogger(__name__)


async def generate_referral_link(db, user_id, channel_id):
    ref = await create_referral(db, user_id, channel_id)
    return f"https://t.me/{{bot_username}}?start=ref_{ref['code']}"


async def handle_referral(db, referrer_id, referred_id, channel_id):
    try:
        await process_referral_reward(db, referrer_id, referred_id, channel_id)
        return True
    except Exception as e:
        logger.error(f'Referral error: {e}')
        return False


async def get_referral_report(db, user_id):
    stats = await get_referral_stats(db, user_id)
    if not stats:
        return '📊 No referrals yet.'
    total = stats.get('total', 0)
    successful = stats.get('successful', 0)
    return f"📊 *Referral Stats*\n\n👥 Total Referrals: {total}\n✅ Successful: {successful}"
