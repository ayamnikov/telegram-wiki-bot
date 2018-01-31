
import logging
from functools import lru_cache, wraps
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
import asyncio
from urllib.parse import quote

from tornado.concurrent import run_on_executor
import wikipedia

from .settings import LRU_MAX_SIZE


def wrap_future(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        return asyncio.wrap_future(func(*args, **kwargs))
    return wrapper


class WikipediaClient:
    lock = Lock()
    executor = ThreadPoolExecutor(4)

    @wrap_future
    @run_on_executor
    @lru_cache(maxsize=LRU_MAX_SIZE)
    def search(self, lang, text):
        with self.lock:
            wikipedia.set_lang(lang)
            return wikipedia.search(text, suggestion=True)

    @wrap_future
    @run_on_executor
    @lru_cache(maxsize=LRU_MAX_SIZE)
    def article(self, lang, title):
        with self.lock:
            wikipedia.set_lang(lang)
            for _ in range(3):
                try:
                    summary = wikipedia.summary(title, sentences=6)
                    return summary
                except wikipedia.exceptions.DisambiguationError as exc:
                    title = exc.options[0]
                except wikipedia.exceptions.PageError:
                    return

    @wrap_future
    @run_on_executor
    @lru_cache(maxsize=LRU_MAX_SIZE)
    def link(self, lang, title):
        with self.lock:
            wikipedia.set_lang(lang)
            try:
                page = wikipedia.page(title)
                path = page.title.replace(' ', '_')
                return f'https://{lang}.wikipedia.org/wiki/{path}'
            except Exception:
                logging.exception('Error while making link')


search = WikipediaClient().search
article = WikipediaClient().article
link = WikipediaClient().link
