
import logging
import json
import re

from tornado.httpclient import AsyncHTTPClient
from tornado.ioloop import IOLoop

from . import wikipedia
from . import localization
from . import history
from .settings import TELEGRAM_API_TOKEN, SUPPORTED_LANGS, MAX_HISTORY_SIZE


BASE_URL = f'https://api.telegram.org/bot{TELEGRAM_API_TOKEN}'
GREETING = (
    'Я телеграм-бот, который умеет искать статьи в Википедии. '
    'Просто отправьте фразу, и я постараюсь что-нибудь найти.'
    '\n\n'
    'По умолчанию поиск производится в той языковой версии Википедии, ' 
    'которая соответствует языку вашего интерфейса. Чтобы поменять ' 
    'язык поиска, наберите команду `/setlang {lang_code}`, ' 
    'где `{lang_code}` это двухбуквенный код языка, например `en`. '
    '\n\n'
    'Другие команды:\n'
    f'/history - выводит {MAX_HISTORY_SIZE} последних прочитанных статей\n'
    '/getlang - возвращает текущий язык поиска'
)


class InlineButton:
    def __init__(self, text, callback_data):
        self.text = text
        self.callback_data = callback_data

    def as_dict(self):
        return {
            'text': self.text,
            'callback_data': self.callback_data
        }


class TelegramClient:
    client = AsyncHTTPClient()

    async def _fetch(self, url, args, timeout=10):
        logging.debug(f'Dumpimg {args}')
        body = json.dumps(args, ensure_ascii=False)
        headers = {'content-type': 'application/json'}
        logging.debug(f'Sending request: {url} {body}')
        response = await self.client.fetch(
            url,
            method='POST',
            body=body,
            headers=headers,
            request_timeout=timeout,
            raise_error=False,
        )

        code = response.code
        reason = response.reason
        body = response.body

        if code >= 500:
            logging.exception(f'Server error: {code} {reason} {body}')
            return
        elif response.code != 200:
            logging.exception(f'Bad request: {code} {reason} {body}')
            return

        response = json.loads(response.body)
        assert response['ok']
        return response['result']

    async def get_updates(self, offset, timeout=300):
        url = f'{BASE_URL}/getUpdates'
        args = dict(offset=offset, timeout=timeout)
        return await self._fetch(url, args, timeout + 10)

    async def send_message(self, chat_id, text, inline_buttons=None):
        url = f'{BASE_URL}/sendMessage'

        args = dict(chat_id=chat_id, text=text, parse_mode='markdown')
        if inline_buttons:
            args['reply_markup'] = {
                'inline_keyboard': [
                    [btn.as_dict()]
                    for btn in inline_buttons
                ]
            }
        return await self._fetch(url, args)


async def receive_updates():
    client = TelegramClient()
    offset = 0
    ioloop = IOLoop.current()

    while True:
        updates = await client.get_updates(offset)

        if not updates:
            continue

        for update in updates:
            try:
                ioloop.add_callback(UpdateHandler(update).handle)
            except Exception:
                logging.exception(f'Error while handling update '
                                  f'{json.dumps(update, sort_keys=True, indent=4)}')

        offset = updates[-1]['update_id'] + 1


class UpdateHandler:
    def __init__(self, update):
        logging.debug(
            f'Handling update:\n'
            f'{json.dumps(update, sort_keys=True, indent=4)}'
        )

        if 'message' in update:
            self.type = 'message'
            message = update['message']
            self.text = message['text']
            self.chat_id = message['chat']['id']
        elif 'callback_query' in update:
            self.type = 'callback_query'
            message = update['callback_query']
            self.callback_data = message['data']
            self.chat_id = message['message']['chat']['id']
        else:
            raise Exception('Unknown message type')

        self.user_id = message['from']['id']
        self.language_code = message['from']['language_code']

    async def _handle(self):
        if self.type == 'message':
            mo = re.match(r'(^/\w+)\s*(.*)', self.text)
            logging.debug(f'Matched command: {bool(mo)}')
            if mo:
                cmd = mo.groups()[0][1:]
                args = mo.groups()[1].split()
                return await self.execute_command(cmd, *args)

            return await self.search()

        elif self.type == 'callback_query':
            await self.on_callback()

    async def handle(self):
        try:
            return await self._handle()
        except Exception:
            logging.exception('Error while handling message')

    async def search(self, text=None):
        lang = localization.get_lang(self.user_id, self.language_code)
        text = text or self.text
        results, suggestion = await wikipedia.search(lang, text)
        client = TelegramClient()
        response = 'Ничего не найдено'

        if results:
            title = results[0]
            if suggestion:
                suggestions = results[1:3] + [suggestion]
            else:
                suggestions = results[1:4]
        else:
            title = suggestion
            suggestions = results[:3]

        if title:
            summary = await wikipedia.article(lang, title)
            if summary:
                history.mark_as_read(title, self.user_id)
                response = summary + '..'
                url = await wikipedia.link(lang, title)
                if url:
                    response += f'\n\n[{url}]({url})'

        inline_buttons = [
            InlineButton(title, history.get_title_id(title))
            for title in suggestions
        ]

        await client.send_message(self.chat_id, response, inline_buttons)

    async def execute_command(self, cmd, *args):
        client = TelegramClient()

        if cmd == 'setlang':
            if not args:
                return await client.send_message(self.chat_id, 'Укажите язык')
            lang = args[0].lower()
            if localization.set_lang(self.user_id, lang):
                return await client.send_message(
                    self.chat_id,
                    f'Установлен язык: `{lang}`'
                )
            else:
                lang_list = '\n'.join(sorted(SUPPORTED_LANGS))
                return await client.send_message(
                    self.chat_id,
                    'Выбранный язык не поддерживается.\n'
                    f'Список поддерживаемых языков:\n{lang_list}'
                )

        elif cmd == 'getlang':
            lang = localization.get_lang(self.user_id, self.language_code)
            return await client.send_message(
                self.chat_id,
                f'Язык поиска: `{lang}`'
            )

        elif cmd == 'history':
            titles = history.get_user_articles(self.user_id)
            inline_buttons = [
                InlineButton(title, history.get_title_id(title))
                for title in titles
            ]
            if not titles:
                response = 'Вы ничего не читали.'
            else:
                response = 'Последние статьи, которые вы читали:'
            return await client.send_message(self.chat_id, response, inline_buttons)

        else:
            return await client.send_message(self.chat_id, GREETING)

    async def on_callback(self):
        title_id = self.callback_data
        title = history.get_title(title_id)
        return await self.search(title)
