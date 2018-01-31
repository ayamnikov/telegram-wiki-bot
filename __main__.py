import logging
import sys

from tornado.platform.asyncio import AsyncIOMainLoop
AsyncIOMainLoop().install()
from tornado.ioloop import IOLoop

from .telegram import receive_updates


def setup_logging():
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.DEBUG)
    formatter = logging.Formatter('[%(asctime)s][%(name)s][%(levelname)s] %(message)s')
    ch.setFormatter(formatter)
    root.addHandler(ch)


def main():
    setup_logging()
    loop = IOLoop.current()
    loop.add_callback(receive_updates)
    loop.start()


if __name__ == '__main__':
    main()
