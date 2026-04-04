BOT_VERSION = '1.0.0'

MAX_CHANNELS_FREE = 3
MAX_CHANNELS_BASIC = 10
MAX_CHANNELS_PRO = 50
MAX_CHANNELS_ENTERPRISE = 999

MAX_WELCOME_MSG_LENGTH = 4096
MAX_BROADCAST_RECIPIENTS = 10000

CAPTCHA_TIMEOUT = 300
DEFAULT_ACCEPT_DELAY = 0

SUPPORTED_LANGUAGES = ['en', 'hi', 'es', 'pt', 'ru', 'ar', 'id']
DEFAULT_LANGUAGE = 'en'

CALLBACK_PREFIXES = {
    'channel': 'ch_',
    'toggle_auto_accept': 'toggle_aa_',
    'set_welcome': 'set_welcome_',
    'analytics': 'analytics_',
    'captcha': 'captcha_',
    'confirm': 'confirm_',
    'cancel': 'cancel_',
}
