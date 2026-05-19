import config

TIER_LIMITS = {
    'free': {
        'max_channels': config.MAX_FREE_CHANNELS,
        'max_clones': config.MAX_FREE_CLONES,
        'business_features': False,
        'premium_features': False,
    },
    'premium': {
        'max_channels': config.MAX_PREMIUM_CHANNELS,
        'max_clones': config.MAX_PREMIUM_CLONES,
        'business_features': False,
        'premium_features': True,
    },
    'business': {
        'max_channels': config.MAX_BUSINESS_CHANNELS,
        'max_clones': config.MAX_BUSINESS_CLONES,
        'business_features': True,
        'premium_features': True,
    },
}

def check_feature(tier, feature):
    limits = TIER_LIMITS.get(tier, TIER_LIMITS['free'])
    return limits.get(feature, False)

def get_tier_limit(tier, feature):
    limits = TIER_LIMITS.get(tier, TIER_LIMITS['free'])
    return limits.get(feature, 0)
