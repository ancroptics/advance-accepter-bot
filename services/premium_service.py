from config import TIER_LIMITS

def check_feature(tier, feature):
    limits = TIER_LIMITS.get(tier, TIER_LIMITS['free'])
    return limits.get(feature, False)

def get_tier_limit(tier, feature):
    limits = TIER_LIMITS.get(tier, TIER_LIMITS['free'])
    return limits.get(feature, 0)
