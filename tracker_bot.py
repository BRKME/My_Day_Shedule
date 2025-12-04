#!/usr/bin/env python3
"""
Task Tracker Bot v3.0 — WITH DEBUG LOGS
Добавлены логи для диагностики галочек
"""

import asyncio
import aiohttp
from aiohttp import web
import json
import logging
from datetime import datetime, timedelta
import os
import re
import signal
import sys
import html
import time
import hashlib
import ipaddress
import random
from typing import Dict, List, Set
from collections import OrderedDict
from asyncio import Lock

# ============================================================================
# КОНФИГ
# ============================================================================

MAX_STATE_SIZE = 1000
STATE_TTL_SECONDS = 86400
MAX_TASK_DISPLAY_LENGTH = 30
MAX_CALLBACK_DATA_BYTES = 64
MAX_MESSAGE_LENGTH = 4000
TELEGRAM_API_TIMEOUT = 30
MAX_RETRIES = 3
RETRY_BASE_DELAY = 1.0

# Telegram IP ranges (2025)
TELEGRAM_IP_RANGES = [
    ipaddress.ip_network('149.154.160.0/20'),
    ipaddress.ip_network('91.108.4.0/22'),
    ipaddress.ip_network('91.108.8.0/22'),
    ipaddress.ip_network('91.108.12.0/22'),
    ipaddress.ip_network('91.108.16.0/22'),
    ipaddress.ip_network('91.108.20.0/22'),
    ipaddress.ip_network('91.108.56.0/22'),
    ipaddress.ip_network('91.105.192.0/23'),
    ipaddress.ip_network('91.108.60.0/22'),
]

# УНИВЕРСАЛЬНЫЕ ПАТТЕРНЫ — ловят "задачи", "задача", "Задачи:", "задачи" и т.д.
SECTION_PATTERNS = {
    'day':     re.compile(r'(?:☀️\s*)?(?:Дневные\s+)?[Зз]адач[аи]?\s*:?\s*(.*?)(?=(?:⛔|Нельзя|🌙|Вечерние|🎯|Цель|$))', re.IGNORECASE | re.DOTALL),
    'cant_do': re.compile(r'(?:⛔\s*)?(?:Нельзя\s+)?[Дд]елать\s*:?\s*(.*?)(?=(?:🌙|Вечерние|🎯|Цель|$))', re.IGNORECASE | re.DOTALL),
    'evening': re.compile(r'(?:🌙\s*)?(?:Вечерние\s+)?[Зз]адач[аи]?\s*:?\s*(.*?)(?=(?:🎯|Цель|$))', re.IGNORECASE | re.DOTALL),
}

TASK_PATTERN = re.compile(r'•\s*(.+?)(?:\s*\([^)]+\))?\s*$')

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ============================================================================
# ВСПОМОГАТЕЛЬНЫЕ КЛАССЫ
# ============================================================================

class RateLimiter:
    def __init__(self):
        self.requests: Dict[str, List[float]] = {}
        self.lock = Lock()

    async def allow(self, key: str) -> bool:
        async with self.lock:
            now = time.time()
            self.requests[key] = [t for t in self.requests.get(key, []) if now - t < 60]
            if len(self.requests.get(key, [])) >= 100:
                return False
            self.requests.setdefault(key, []).append(now)
            return True

class StateManager:
    def __init__(self):
        self.store: OrderedDict[str, tuple[float, Set[int]]] = OrderedDict()
        self.lock = Lock()

    async def get(self, key: str) -> Set[int]:
        async with self.lock:
            if key in self.store:
                ts, state = self.store[key]
                if time.time() - ts < STATE_TTL_SECONDS:
                    self.store.move_to_end(key)
                    return state.copy()
                del self.store[key]
            return set()

    async def set(self, key: str, state: Set[int]):
        async with self.lock:
            if len(self.store) >= MAX_STATE_SIZE:
                self.store.popitem(last=False)
            self.store[key] = (time.time(), state.copy())
            self.store.move_to_end(key)

class TelegramAPIClient:
    def __init__(self, token: str, chat_id: int):
        self.token = token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{token}"

    async def request(self, method: str, **kwargs):
        for i in range(MAX_RETRIES):
            try:
                timeout = aiohttp.ClientTimeout(total=TELEGRAM_API_TIMEOUT)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.post(f"{self.base_url}/{method}", json=kwargs) as resp:
                        data = await resp.json()
                        if data.get('ok'):
                            return data['result']
                        logger.error(f"TG error: {data}")
            except Exception as e:
                if i == MAX_RETRIES - 1:
                    logger.error(f"Failed after retries: {e}")
                else:
                    await asyncio.sleep(RETRY_BASE_DELAY * (2 ** i) + random.uniform(0, 0.5))
        return None

    async def send(self, text: str, **kwargs):
        if len(text) > MAX_MESSAGE_LENGTH:
            text = text[:MAX_MESSAGE_LENGTH-100] + "\n...[обрезано]"
        payload = {'chat_id': self.chat_id, 'text': text, 'parse_mode': 'HTML', 'disable_web_page_preview': True, **kwargs}
        return await self.request('sendMessage', **payload)

    async def edit(self, message_id: int, text: str, **kwargs):
        payload = {'chat_id': self.chat_id, 'message_id': message_id, 'text': text, 'parse_mode': 'HTML', **kwargs}
        return await self.request('editMessageText', **payload)

    async def answer_cb(self, cb_id: str, **kwargs):
        await self.request('answerCallbackQuery', callback_query_id=cb_id, **kwargs)

    async def set_webhook(self, url: str):
        return await self.request('setWebhook', url=url, drop_pending_updates=True, max_connections=40)

# ============================================================================
# БОТ
# ============================================================================

class TaskTrackerBot:
    def __init__(self):
        self.token = os.getenv('TELEGRAM_TOKEN')
        self.chat_id = int(os.getenv('TELEGRAM_CHAT_ID', '0'))
        if not self.token or self.chat_id == 0:
            raise ValueError("Set TELEGRAM_TOKEN and TELEGRAM_CHAT_ID")
        domain = os.getenv('RAILWAY_PUBLIC_DOMAIN')
        self.webhook_url = f"https://{domain}/webhook" if domain else None
        self.port = int(os.getenv('PORT', '8080'))
        self.state = StateManager()
        self.limiter = RateLimiter()
        self.start_time = time.time()
        signal.signal(signal.SIGINT, lambda *_: asyncio.create_task(self.shutdown()))
        signal.signal(signal.SIGTERM, lambda *_: asyncio.create_task(self.shutdown()))
        logger.info("Bot initialized")

    async def shutdown(self):
        logger.info("Shutting down...")
        asyncio.get_event_loop().stop()

    def parse_tasks(self, text: str) -> Dict[str, List[str]]:
        tasks = {'day': [], 'cant_do': [], 'evening': []}
        safe = '\n'.join(html.escape(l.strip()) for l in text.splitlines() if l.strip())
        logger.info(f"Parsing text: {text[:100]}...")  # DEBUG
        for sec, pat in SECTION_PATTERNS.items():
            m = pat.search(safe)
            if m:
                logger.info(f"Match for {sec}: {m.group(1)[:100]}...")  # DEBUG
                for line in m.group(1).split('\n'):
                    line = line.strip()
                    if line.startswith('•'):
                        tm = TASK_PATTERN.search(line)
                        if tm:
                            tasks[sec].append(tm.group(1).strip())
        logger.info(f"Parsed → Day: {len(tasks['day'])}, Can't do: {len(tasks['cant_do'])}, Evening: {len(tasks['evening'])}")
        return tasks

    def truncate(self, t: str) -> str:
        return t if len(t) <= MAX_TASK_DISPLAY_LENGTH else t[:MAX_TASK_DISPLAY_LENGTH-3].rsplit(' ', 1)[0] + '...'

    def keyboard(self, tasks: Dict[str, List[str]], done: Dict[str, Set[int]]) -> Dict:
        kb = []
        sections = [
            ('day', 'ДНЕВНЫЕ ЗАДАЧИ', 'day'),
            ('cant_do', 'НЕЛЬЗЯ ДЕЛАТЬ', 'cant'),
            ('evening', 'ВЕЧЕРНИЕ ЗАДАЧИ', 'eve')
        ]
        for key, title, prefix in sections:
            if tasks[key]:
                kb.append([{'text': title, 'callback_data': 'noop'}])
                for i, task in enumerate(tasks[key]):
                    emoji = '✅' if i in done.get(key, set()) else '⬜'
                    data = f"toggle_{prefix}_{i}"
                    logger.info(f"Callback data for {task}: {data} (len: {len(data.encode())})")  # DEBUG
                    kb.append([{'text': f'{emoji} {i+1}. {self.truncate(task)}', 'callback_data': data}])
        kb.append([{'text': 'Сохранить прогресс', 'callback_data': 'save'},
                   {'text': 'Отменить', 'callback_data': 'cancel'}])
        return {'inline_keyboard': kb}

    def message_text(self, tasks: Dict[str, List[str]], done: Dict[str, Set[int]]) -> str:
        lines = ["<b>Отметь выполненные задачи:</b>\n"]
        total = completed = 0
        titles = {'day': 'ДНЕВНЫЕ ЗАДАЧИ:', 'cant_do': 'НЕЛЬЗЯ ДЕЛАТЬ:', 'evening': 'ВЕЧЕРНИЕ ЗАДАЧИ:'}
        for key in titles:
            if tasks[key]:
                lines.append(f"\n<b>{titles[key]}</b>")
                for i, t in enumerate(tasks[key]):
                    emoji = '✅' if i in done.get(key, set()) else '⬜'
                    lines.append(f"{emoji} {self.truncate(t)}")
                    total += 1
                    if i in done.get(key, set()):
                        completed += 1
        if total:
            perc = int(completed / total * 100)
            bar = '▓' * (perc // 10) + '░' * (10 - perc // 10)
            lines.append(f"\n<b>ПРОГРЕСС:</b> {bar} {completed}/{total} ({perc}%)")
        lines.append("\n<i>Нажми на задачу → отметится</i>")
        return '\n'.join(lines)

    async def process_message(self, text: str):
        logger.info(f"Processing message: {text[:100]}...")  # DEBUG
        tasks = self.parse_tasks(text)
        if not any(tasks.values()):
            logger.info("No tasks found — ignoring")
            return
        msg = self.message_text(tasks, {})
        kb = self.keyboard(tasks, {})
        client = TelegramAPIClient(self.token, self.chat_id)
        result = await client.send(msg, reply_markup=kb)
        logger.info(f"Message sent, result: {result}")  # DEBUG

    async def handle_callback(self, query):
        data = query.get('data', '')
        qid = query['id']
        msg = query['message']
        msg_id = msg['message_id']
        old_text = msg.get('text', '')
        client = TelegramAPIClient(self.token, self.chat_id)

        logger.info(f"Callback received: data={data}, msg_id={msg_id}")  # DEBUG

        if data == 'save':
            logger.info("Save pressed")  # DEBUG
            await client.answer_cb(qid, text="Прогресс сохранён!")
            new_text = old_text.replace("Отметь выполненные задачи:", "ПРОГРЕСС СОХРАНЁН\n\nВЫПОЛНЕННЫЕ ЗАДАЧИ:")
            result = await client.edit(msg_id, new_text)
            logger.info(f"Save result: {result}")  # DEBUG
            return

        if data == 'cancel':
            logger.info("Cancel pressed")  # DEBUG
            await client.answer_cb(qid, text="Отменено")
            result = await client.edit(msg_id, "ОБНОВЛЕНИЕ ОТМЕНЕНО")
            logger.info(f"Cancel result: {result}")  # DEBUG
            return

        if data.startswith('toggle_'):
            logger.info(f"Toggle pressed: {data}")  # DEBUG
            prefix = data.split('_')[1]
            idx = int(data.split('_')[-1])
            section_map = {'day': 'day', 'cant': 'cant_do', 'eve': 'evening'}
            section = section_map.get(prefix)
            if not section:
                logger.error(f"Unknown section: {prefix}")  # DEBUG
                return

            key = f"{msg_id}_{section}"
            state = await self.state.get(key)
            state.symmetric_difference_update([idx])
            await self.state.set(key, state)
            logger.info(f"State updated for {key}: {state}")  # DEBUG

            # ВСЁ СОСТОЯНИЕ ВСЕХ СЕКЦИЙ
            full_done = {}
            for sec in ['day', 'cant_do', 'evening']:
                saved = await self.state.get(f"{msg_id}_{sec}")
                if saved:
                    full_done[sec] = saved
            full_done[section] = state

            tasks = self.parse_tasks(old_text)
            new_text = self.message_text(tasks, full_done)
            new_kb = self.keyboard(tasks, full_done)

            await client.answer_cb(qid)
            result = await client.edit(msg_id, new_text, reply_markup=new_kb)
            logger.info(f"Toggle edit result: {result}")  # DEBUG

    async def webhook_handler(self, request: web.Request) -> web.Response:
        try:
            client_ip = (request.headers.get('X-Forwarded-For', '').split(',')[0].strip() or request.remote)
            logger.info(f"Webhook from IP: {client_ip}")  # DEBUG
            if not any(ipaddress.ip_address(client_ip) in net for net in TELEGRAM_IP_RANGES):
                logger.warning(f"Blocked IP: {client_ip}")
                return web.Response(status=403)

            if not await self.limiter.allow(client_ip):
                return web.Response(status=429)

            update = await request.json()
            logger.info(f"Update type: {list(update.keys())}")  # DEBUG

            if 'callback_query' in update:
                await self.handle_callback(update['callback_query'])
            elif 'message' in update:
                msg = update['message']
                if msg.get('chat', {}).get('id') == self.chat_id and 'text' in msg:
                    text = msg['text']
                    if any(x in text.lower() for x in ['задач', 'делать']):
                        await self.process_message(text)

            return web.Response(text="OK")
        except Exception as e:
            logger.error(f"Webhook error: {e}", exc_info=True)
            return web.Response(status=500)

    async def start(self):
        logger.info("Starting bot...")
        app = web.Application()
        app.router.add_get('/', lambda r: web.Response(text="Task Tracker Bot v3.0 alive"))
        app.router.add_post('/webhook', self.webhook_handler)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', self.port)
        await site.start()
        logger.info(f"Server on port {self.port}")

        if self.webhook_url:
            client = TelegramAPIClient(self.token, self.chat_id)
            ok = await client.set_webhook(self.webhook_url)
            logger.info("Webhook set" if ok else "Webhook FAILED")

        logger.info("Bot ready!")
        await asyncio.Event().wait()

if __name__ == "__main__":
    bot = TaskTrackerBot()
    asyncio.run(bot.start())
