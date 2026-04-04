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

# Deployment
PORT = int(os.getenv('PORT', '10000'))
WEBHOOK_URL = os.getenv('WEBHOOK_URL', '')
USE_WEBHOOK = os.getenv('USE_WEBHOOK', 'true').lower() == 'true'

# Defaults
DEFAULT_REFERRAL_COINS = int(os.getenv('DEFAULT_REFERRAL_COINS', '10'))
DEFAULT_BROADCAST_RATE = int(os.getenv('DEFAULT_BROADCAST_RATE', '25'))
DEFAULT_APPROVE_RATE = int(os.getenv('DEFAULT_APPROVE_RATE', '2'))
MAX_FREE_CHANNELS = int(os.getenv('MAX_FREE_CHANNELS', '1'))
MAX_PREMIUM_CHANNELS = int(os.getenv('MAX_PREMIUM_CHANNELS', '5'))
MAX_BUSINESS_CHANNELS = int(os.getenv('MAX_BUSINESS_CHANNELS', '999'))

# Premium
PREMIUM_PRICE_MONTHLY = int(os.getenv('PREMIUM_PRICE_MONTHLY', '199'))
BUSINESS_PRICE_MONTHLY = int(os.getenv('BUSINESS_PRICE_MONTHLY', '499'))

# Clone
MAX_FREE_CLONES = int(os.getenv('MAX_FREE_CLONES', '0'))
MAX_PREMIUM_CLONES = int(os.getenv('MAX_PREMIUM_CLONES', '1'))
MAX_BUSINESS_CLONES = int(os.getenv('MAX_BUSINESS_CLONES', '5'))
CLONE_WEBHOOK_BASE_URL = os.getenv('CLONE_WEBHOOK_BASE_URL', '')
CLONE_ENCRYPTION_KEY = os.getenv('CLONE_ENCRYPTION_KEY', '')

# Rate limiting
RATE_LIMIT_PER_USER = int(os.getenv('RATE_LIMIT_PER_USER', '2'))  # per second

# Feature flags
ENABLE_CROSS_PROMO = os.getenv('ENABLE_CROSS_PROMO', 'true').lower() == 'true'
ENABLE_CLONING = os.getenv('ENABLE_CLONING', 'true').lower() == 'true'

# UPI Payment
UPI_ID = os.getenv('UPI_ID', 'payment@upi')
