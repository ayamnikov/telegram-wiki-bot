
from .db import redis
from .settings import SUPPORTED_LANGS


def get_lang(user_id, language_code):
    lang = redis.get(f'user:{user_id}:lang') or language_code[:2]
    if isinstance(lang, bytes):
        lang = lang.decode('utf-8')
    return lang


def set_lang(user_id, lang):
    lang = lang.lower()
    if lang in SUPPORTED_LANGS:
        return redis.set(f'user:{user_id}:lang', lang)
