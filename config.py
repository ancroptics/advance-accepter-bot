import os
from dotenv import load_dotenv

load_dotenv()

# Core
BOT_TOKEN = os.getenv('BOT_TOKEN', '')
SUPERADMIN_IDS = [int(x.strip()) for x in os.getenv('SUPERADMIN_IDS', '').split(',') if x.strip()]
BOT_USERNAME = os.getenv('BOT_USERNAME', '')
BOT_DISPLAY_NAME = os.getenv('BOT_DISPLAY_NAME', 'Growth Engine')
SUPPORT_USERNAME = os.getenv('SUPPORT_USERNAME', '')

# Database
DATABASE_URL = os.getenv('DATABASE_URL', '')

# Webhook
USE_WEBHOOK = os.getenv('USE_WEBHOOK', 'false').lower() == 'true'
WEBHOOK_URL = os.getenv('WEBHOOK_URL', '')
PORT = int(os.getenv('PORT', '10000'))

# Premium tiers
TIER_LIMITS = {
    'free': {
        'channels': 2,
        'clones': 0,
        'broadcasts_per_day': 1,
        'max_broadcast_audience': 500,
        'drip_approve': False,
        'force_subscribe': False,
        'cross_promo': False,
        'watermark_removable': False,
        'analytics_export': False,
    },
    'pro': {
        'channels': 10,
        'clones': 3,
        'broadcasts_per_day': 10,
        'max_broadcast_audience': 10000,
        'drip_approve': True,
        'force_subscribe': True,
        'cross_promo': True,
        'watermark_removable': True,
        'analytics_export': True,
    },
    'enterprise': {
        'channels': 50,
        'clones': 10,
        'broadcasts_per_day': 999,
        'max_broadcast_audience': 999999,
        'drip_approve': True,
        'force_subscribe': True,
        'cross_promo': True,
        'watermark_removable': True,
        'analytics_export': True,
    }
}
