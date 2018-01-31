
from functools import lru_cache
from base64 import b64encode
from hashlib import sha1

from .db import redis
from .settings import LRU_MAX_SIZE, MAX_HISTORY_SIZE


@lru_cache(maxsize=LRU_MAX_SIZE)
def get_title_id(title):
    title = title.encode('utf-8')
    key = b'title:' + b64encode(title)

    title_id = redis.get(key)
    if not title_id:
        title_id = sha1(title).hexdigest()
        redis.set(key, title_id)
        redis.set(f'title_id:{title_id}', title)

    if isinstance(title_id, bytes):
        title_id = title_id.decode('utf-8')

    return title_id


@lru_cache(maxsize=LRU_MAX_SIZE)
def get_title(title_id):
    title = redis.get(f'title_id:{title_id}')
    if title:
        return title.decode('utf-8')


def mark_as_read(title, user_id):
    key = f'user:{user_id}:articles'
    redis.lpush(key, title)
    redis.ltrim(key, 0, MAX_HISTORY_SIZE - 1)


def get_user_articles(user_id):
    key = f'user:{user_id}:articles'
    return [
        title.decode('utf-8')
        for title in redis.lrange(key, 0, MAX_HISTORY_SIZE - 1)
    ]
