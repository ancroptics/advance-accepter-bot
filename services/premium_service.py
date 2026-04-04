import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def check_feature_access(tier, feature):
    TIER_FEATURES = {
        'free': {'force_subscribe', 'drip_approve', 'multi_language', 'cross_promo', 'export', 'auto_poster', 'clone'},
        'premium': {'clone_5'},
        'business': set(),
    }
    blocked = TIER_FEATURES.get(tier, TIER_FEATURES['free'])
    return feature not in blocked
