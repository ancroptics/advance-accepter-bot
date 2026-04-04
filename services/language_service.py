import logging
import json

logger = logging.getLogger(__name__)


def get_welcome_for_language(channel, language_code):
    if not language_code:
        return None
    i18n = channel.get('welcome_messages_i18n')
    if not i18n:
        return None
    if isinstance(i18n, str):
        try:
            i18n = json.loads(i18n)
        except Exception:
            return None
    lang_data = i18n.get(language_code)
    if lang_data and isinstance(lang_data, dict):
        return lang_data.get('text')
    elif lang_data and isinstance(lang_data, str):
        return lang_data
    return None
