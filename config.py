import os
from dotenv import load_dotenv

load_dotenv()

# Core
BOT_TOKEN = os.getenv('BOT_TOKEN')
DATABASE_URL = os.getenv('DATABASE_URL')

# Superadmin IDs (comma-separated)
SUPERADMIN_IDS = [
    int(x) for x in os.getenv('SUPERADMIN_IDS', '').split(',') if x.strip()
]

# Rate Limiting
DEFAULT_APPROVE_RATE = int(os.getenv('DEFAULT_APPROVE_RATE', '2'))
MAX_FREE_CHANNELS = int(os.getenv('MAX_FREE_CHANNELS', '1'))
MAX_PREMIUM_CHANNELS = int(os.getenv('MAX_PREMIUM_CHANNELS', '5'))
MAX_BUSINESS_CHANNELS = int(os.getenv('MAX_BUSINESS_CHANNELS', '999'))

# Broadcast
MAX_BROADCAST_PER_DAY = int(os.getenv('MAX_BROADCAST_PER_DAY', '3'))

# Premium
PREMIUM_PAYMENT_UPI_ID = os.getenv('PREMIUM_PAYMENT_UPI_ID', '')
PREMIUM_MONTHLY_PRICE = int(os.getenv('PREMIUM_MONTHLY_PRICE', '99'))
PREMIUM_YEARLY_PRICE = int(os.getenv('PREMIUM_YEARLY_PRICE', '999'))

# Referral
DEFAULT_REFERRAL_COINS = int(os.getenv('DEFAULT_REFERRAL_COINS', '10'))
REFERRALS_PER_SLOT = int(os.getenv('REFERRALS_PER_SLOT', '3'))

# Feature Toggles
ENABLE_CROSS_PROMO = os.getenv('ENABLE_CROSS_PROMO', 'true').lower() == 'true'
ENABLE_CLONING = os.getenv('ENABLE_CLONING', 'true').lower() == 'true'
ENABLE_PREMIUM = os.getenv('ENABLE_PREMIUM', 'true').lower() == 'true'

# Health Server
PORT = int(os.getenv('PORT', '8443'))

# Welcome DM
DEFAULT_WELCOME_MESSAGE = os.getenv(
    'DEFAULT_WELCOME_MESSAGE',
    'Welcome {name} to {channel_name}! We are glad to have you.'
)

# Drip DM
DRIPDM_MAX_STEPS_FREE = int(os.getenv('DRIPDM_MAX_STEPS_FREE', '3'))
DRIPDM_MAX_STEPS_PREMIUM = int(os.getenv('DRIPDM_MAX_STEPS_PREMIUM', '10'))
DRIPDM_MIN_DELAY = int(os.getenv('DRIPDM_MIN_DELAY', '60'))  # minutes