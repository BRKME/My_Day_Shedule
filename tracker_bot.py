#!/usr/bin/env python3
"""
Telegram бот для отслеживания выполнения задач - v2.0
Исправления v2.0:
1. Все HTTP → aiohttp (не блокирует event loop)
2. message_states синхронизируются с GitHub (переживает рестарт сервиса)
3. Исправлен check_schedule (.seconds → .total_seconds())
4. Деплой: systemd на VPS (Railway отключён 07.2026)
"""

import asyncio
import aiohttp
from aiohttp import web
import json
import logging
from datetime import date, datetime, timedelta
import os
import re
import base64

from core import (GITHUB_REPO, STATE_KEEP_LAST, get_level as _core_get_level,
                  task_of_the_day, weight_verdict,
                  is_bracelet_day, page_of_the_day, page_url,
                  parse_ddmmyyyy,
                  github_contents_url, github_headers, merge_stats,
                  normalize_task, prune_message_states, summarize_day)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# merge_stats, get_level, prune_message_states — в core.py (04.08.2026),
# общие с notifier.py.


class TaskTrackerBot:
    def __init__(self):
        self.telegram_token = os.getenv('TELEGRAM_TOKEN', '')
        if not self.telegram_token:
            raise ValueError("❌ TELEGRAM_TOKEN не найден в переменных окружения!")
        
        self.chat_id = os.getenv('TELEGRAM_CHAT_ID', '')
        if not self.chat_id:
            raise ValueError("❌ TELEGRAM_CHAT_ID не найден в переменных окружения!")
        
        self.github_token = os.getenv('GITHUB_TOKEN', '')
        self.github_repo = GITHUB_REPO

        # Программа «365 дней»: отметки заданий храним ОТДЕЛЬНО от stats.json.
        # Задание не входит в процент дня — иначе в тяжёлый день сольётся
        # именно развитие, оно дороже прочего и первым идёт под нож.
        self.program_file = "program.json"
        self.program = self.load_program()
        
        self.stats_file = "stats.json"
        self.message_state_file = "message_states.json"
        self.last_update_id = 0
        
        # aiohttp session — создаётся в run()
        self.session = None
        
        # Хранилище текущего состояния для каждого сообщения
        # {message_id: {'tasks': {...}, 'completed': {...}, 'original_text': '...'}}
        self.message_state = self.load_message_states()
        
    def parse_tasks(self, message_text):
        """Парсит задачи из сообщения notifier.py"""
        tasks = {
            'morning': [],  # Оставляем для обратной совместимости, но не используем
            'day': [],
            'cant_do': [],  # Новая секция "Нельзя делать"
            'evening': []
        }
        
        lines = message_text.split('\n')
        current_section = None
        
        for line in lines:
            line = line.strip()
            
            # Определяем секцию (убираем HTML теги для проверки)
            clean_line = line.replace('<b>', '').replace('</b>', '').replace('<i>', '').replace('</i>', '')
            
            # НАЧАЛО СЕКЦИЙ (включаем парсинг)
            if ('📋' in clean_line or '☀️' in clean_line) and 'Дневн' in clean_line:
                current_section = 'day'
                continue
            elif any(marker in clean_line for marker in ['⛔', '⛔️', 'Нельзя делать']):
                current_section = 'cant_do'
                continue
            elif ('🌙' in clean_line and 'Вечерн' in clean_line) or ('📋' in clean_line and 'Вечерн' in clean_line) or 'Вечерние задачи' in clean_line:
                current_section = 'evening'
                continue
            
            # КОНЕЦ СЕКЦИЙ (выключаем парсинг)
            elif any(marker in clean_line for marker in [
                'Мудрость дня',
                '🙏 Утренняя молитва',
                '🎉 СЕГОДНЯ',
                '📅 События',
                'Занятия детей'  # НОВОЕ: пропускаем расписание детей
            ]):
                current_section = None
                continue
            
            # Собираем задачи
            if current_section and line.startswith('•'):
                task_text = line[1:].strip()  # Убираем •
                if task_text:
                    tasks[current_section].append(task_text)
        
        logger.info(f"📋 Распарсено задач: день={len(tasks['day'])}, нельзя={len(tasks['cant_do'])}, вечер={len(tasks['evening'])}")
        return tasks
    
    def create_checklist_keyboard(self, tasks, completed):
        """Создаёт inline-клавиатуру с задачами"""
        keyboard = []
        
        # Дневные задачи
        if tasks['day']:
            keyboard.append([{'text': '☀️ ДНЕВНЫЕ ЗАДАЧИ', 'callback_data': 'header'}])
            for idx, task in enumerate(tasks['day']):
                is_done = idx in completed.get('day', [])
                emoji = '⭐' if is_done else '☆'
                # Обрезаем длинный текст для кнопки
                short_task = task[:35] + '...' if len(task) > 35 else task
                keyboard.append([{
                    'text': f'{emoji} {idx+1}. {short_task}',
                    'callback_data': f'toggle_day_{idx}'
                }])
        
        # Нельзя делать
        if tasks['cant_do']:
            keyboard.append([{'text': '⛔ НЕЛЬЗЯ ДЕЛАТЬ', 'callback_data': 'header'}])
            for idx, task in enumerate(tasks['cant_do']):
                is_done = idx in completed.get('cant_do', [])
                emoji = '⭐' if is_done else '☆'
                short_task = task[:32] + '...' if len(task) > 32 else task
                keyboard.append([{
                    'text': f'{emoji} {idx+1}. {short_task}',
                    'callback_data': f'toggle_cant_do_{idx}'
                }])
        
        # Вечерние задачи  
        if tasks['evening']:
            keyboard.append([{'text': '🌙 ВЕЧЕРНИЕ ЗАДАЧИ', 'callback_data': 'header'}])
            for idx, task in enumerate(tasks['evening']):
                is_done = idx in completed.get('evening', [])
                emoji = '⭐' if is_done else '☆'
                short_task = task[:35] + '...' if len(task) > 35 else task
                keyboard.append([{
                    'text': f'{emoji} {idx+1}. {short_task}',
                    'callback_data': f'toggle_evening_{idx}'
                }])
        
        # Кнопки управления
        keyboard.append([
            {'text': '💾 Сохранить', 'callback_data': 'save_progress'},
            {'text': '❌ Отмена', 'callback_data': 'cancel_update'}
        ])
        
        return {'inline_keyboard': keyboard}
    
    def format_checklist_message(self, tasks, completed):
        """Форматирует текст сообщения с чек-листом"""
        msg = "✅ <b>Отметь выполненные задачи:</b>\n"
        
        total_tasks = 0
        total_done = 0
        
        if tasks['day']:
            msg += "\n☀️ <b>ДНЕВНЫЕ:</b>\n"
            for idx, task in enumerate(tasks['day']):
                emoji = '⭐' if idx in completed.get('day', []) else '☆'
                msg += f"{emoji} {task}\n"
                total_tasks += 1
                if idx in completed.get('day', []):
                    total_done += 1
        
        if tasks['cant_do']:
            msg += "\n⛔ <b>НЕЛЬЗЯ ДЕЛАТЬ:</b>\n"
            for idx, task in enumerate(tasks['cant_do']):
                emoji = '⭐' if idx in completed.get('cant_do', []) else '☆'
                msg += f"{emoji} {task}\n"
                total_tasks += 1
                if idx in completed.get('cant_do', []):
                    total_done += 1
        
        if tasks['evening']:
            msg += "\n🌙 <b>ВЕЧЕРНИЕ:</b>\n"
            for idx, task in enumerate(tasks['evening']):
                emoji = '⭐' if idx in completed.get('evening', []) else '☆'
                msg += f"{emoji} {task}\n"
                total_tasks += 1
                if idx in completed.get('evening', []):
                    total_done += 1
        
        # Прогресс
        percentage = int((total_done / total_tasks * 100)) if total_tasks > 0 else 0
        bar = self.get_progress_bar(percentage)
        msg += f"\n📊 <b>Прогресс:</b> {bar} {total_done}/{total_tasks} ({percentage}%)\n"
        
        return msg
    
    def update_original_message_with_progress(self, original_text, tasks, completed):
        """ЭТАП 3: Обновляет исходное сообщение с прогресс-барами"""
        lines = original_text.split('\n')
        
        # ШАГ 1: ОЧИСТКА - удаляем ВСЕ старые прогресс-бары и галочки
        cleaned_lines = []
        for line in lines:
            stripped = line.strip()
            
            # Пропускаем старые прогресс-бары
            if stripped.startswith('📊') or stripped.startswith('🎯 Общий прогресс'):
                continue
            
            # Убираем старые звёздочки из задач
            if line.startswith('•') and '⭐' in line:
                # Удаляем все звёздочки и восстанавливаем оригинал
                cleaned = line.replace('⭐ ', '').replace(' ⭐', '')
                # Убираем лишние пробелы
                parts = cleaned.split('•', 1)
                if len(parts) == 2:
                    cleaned = '• ' + parts[1].strip()
                cleaned_lines.append(cleaned)
            else:
                cleaned_lines.append(line)
        
        # ШАГ 2: ДОБАВЛЕНИЕ - добавляем новые прогресс-бары и галочки
        updated_lines = []
        current_section = None
        task_counters = {'morning': 0, 'day': 0, 'cant_do': 0, 'evening': 0}
        
        for line in cleaned_lines:
            clean_line = line.replace('<b>', '').replace('</b>', '').replace('<i>', '').replace('</i>', '')
            
            # Определяем секцию
            if ('📋' in clean_line or '☀️' in clean_line) and 'Дневн' in clean_line:
                current_section = 'day'
                updated_lines.append(line)
                continue
            elif 'Вечерние задачи' in clean_line or ('🌙' in clean_line and 'Вечерн' in clean_line) or ('📋' in clean_line and 'Вечерн' in clean_line):
                current_section = 'evening'
                updated_lines.append(line)
                continue
            elif any(marker in clean_line for marker in ['⛔', '⛔️', 'Нельзя делать']):
                current_section = 'cant_do'
                updated_lines.append(line)
                continue
            elif 'мудрость' in clean_line.lower() and 'дня' in clean_line.lower():
                current_section = None
                
                total_done = 0
                total_tasks = 0
                
                for section in ['morning', 'day', 'evening']:
                    if len(tasks[section]) > 0:
                        total_done += len(completed.get(section, []))
                        total_tasks += len(tasks[section])
                
                if total_tasks > 0:
                    total_perc = int((total_done / total_tasks * 100))
                    total_bar = self.get_progress_bar(total_perc, length=10)
                    updated_lines.append(f"🎯 <b>Общий прогресс:</b> {total_bar} {total_done}/{total_tasks} ({total_perc}%)")
                
                updated_lines.append("")
                updated_lines.append(line)
                continue
            
            # Обрабатываем задачи
            if current_section and line.startswith('•'):
                idx = task_counters[current_section]
                is_done = idx in completed.get(current_section, [])
                
                # Получаем чистый текст задачи (без • и звёздочек)
                task_text = line[1:].strip()  # Убираем •
                task_text = task_text.replace('⭐ ', '').replace(' ⭐', '').replace('⭐', '')  # Убираем ВСЕ звёздочки
                task_text = task_text.replace('☆ ', '').replace(' ☆', '').replace('☆', '')  # И пустые тоже
                task_text = task_text.strip()  # Убираем лишние пробелы
                
                if is_done:
                    # Только жёлтая звёздочка, без •
                    updated_lines.append(f"⭐ {task_text}")
                else:
                    # Пустая звёздочка, без •
                    updated_lines.append(f"☆ {task_text}")
                
                task_counters[current_section] += 1
            else:
                updated_lines.append(line)
        
        return '\n'.join(updated_lines)
    
    def load_stats(self):
        """Загружает статистику из файла"""
        try:
            if os.path.exists(self.stats_file):
                with open(self.stats_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    # Убираем _info и _format если они есть
                    data = json.loads(content)
                    # Отбрасываем только служебные ключи. Раньше здесь
                    # стоял фильтр «оставить всё с дефисом», то есть
                    # только даты — и секции pullups и weight пропадали.
                    # История подтягиваний уцелела лишь потому, что
                    # читается в обход этой функции.
                    stats = {k: v for k, v in data.items()
                             if k not in ('_info', '_format')}
                    return stats
            return {}
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки статистики: {e}")
            return {}
    
    async def save_stats(self, stats):
        """Сохраняет статистику в файл и синхронизирует с GitHub"""
        try:
            with open(self.stats_file, 'w', encoding='utf-8') as f:
                json.dump(stats, f, ensure_ascii=False, indent=2)
            logger.info("✅ Статистика сохранена локально")
            
            # Синхронизируем с GitHub (async)
            sync_result = await self.sync_stats_to_github(stats)
            if not sync_result:
                logger.warning("⚠️ Синхронизация с GitHub не удалась! Проверь GITHUB_TOKEN")
            
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения статистики: {e}")
            return False
    
    async def save_pullups(self, count):
        """Сохраняет результат подтягиваний"""
        stats = self.load_stats()
        today_key = self.get_today_key()
        
        # Создаём секцию pullups если нет
        if 'pullups' not in stats:
            stats['pullups'] = {}
        
        stats['pullups'][today_key] = count
        logger.info(f"💪 Подтягивания за {today_key}: {count}")
        
        await self.save_stats(stats)
    
    async def save_weight(self, value):
        """Сохраняет контрольное взвешивание. Отдельная секция stats.json,
        как у подтягиваний: это история, а не задача дня."""
        stats = self.load_stats()
        today_key = self.get_today_key()
        stats.setdefault('weight', {})[today_key] = value
        logger.info(f"⚖️ Вес за {today_key}: {value} кг")
        await self.save_stats(stats)

    def get_last_weight(self, days=7):
        """Последний вес за N дней — для сравнения «со вчера».

        Старше недели не берём: сравнивать сегодняшний вес с месячной
        давностью и называть это «со вчера» — врать самому себе.
        """
        weight_data = self.load_stats().get('weight', {})
        today = datetime.now()
        for i in range(days):
            day_key = (today - timedelta(days=i)).strftime("%Y-%m-%d")
            if day_key in weight_data:
                return weight_data[day_key], day_key
        return None, None

    def get_last_pullups(self, days=7):
        """Получает последний результат подтягиваний за N дней"""
        stats = self.load_stats()
        pullups_data = stats.get('pullups', {})
        
        today = datetime.now()
        for i in range(days):
            day = today - timedelta(days=i)
            day_key = day.strftime("%Y-%m-%d")
            if day_key in pullups_data:
                return pullups_data[day_key], day_key
        
        return None, None
    
    async def _github_get_file(self, path):
        """Получает содержимое файла с GitHub (async)"""
        if not self.github_token:
            return None
        try:
            url = github_contents_url(path, self.github_repo)
            headers = github_headers(self.github_token)
            async with self.session.get(url, headers=headers, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    content = base64.b64decode(data['content']).decode('utf-8')
                    return content
                return None
        except Exception as e:
            logger.warning(f"⚠️ GitHub GET {path}: {e}")
            return None
    
    async def _github_put_file(self, path, content, message="auto update"):
        """Записывает файл на GitHub (async)"""
        if not self.github_token:
            logger.warning("⚠️ GITHUB_TOKEN не найден! Проверь /etc/systemd/system/myday-bot.service")
            return False
        try:
            url = github_contents_url(path, self.github_repo)
            headers = github_headers(self.github_token)
            
            # Получаем текущий SHA файла
            sha = None
            async with self.session.get(url, headers=headers, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    sha = data.get('sha')
                elif response.status == 401:
                    logger.error("❌ GitHub: токен невалиден (401 Unauthorized)")
                    return False
                elif response.status == 403:
                    logger.error("❌ GitHub: доступ запрещён (403 Forbidden) - проверь права токена")
                    return False
            
            # Кодируем содержимое
            content_b64 = base64.b64encode(content.encode('utf-8')).decode('utf-8')
            
            payload = {
                "message": message,
                "content": content_b64,
                "branch": "main"
            }
            if sha:
                payload["sha"] = sha
            
            async with self.session.put(url, headers=headers, json=payload, timeout=10) as response:
                if response.status in [200, 201]:
                    logger.info(f"✅ {path} синхронизирован с GitHub")
                    return True
                else:
                    error_text = await response.text()
                    logger.warning(f"⚠️ GitHub PUT {path}: {response.status} - {error_text[:100]}")
                    return False
                
        except Exception as e:
            logger.warning(f"⚠️ Ошибка синхронизации {path} с GitHub: {e}")
            return False
    
    async def sync_stats_to_github(self, stats):
        """Синхронизирует stats.json с GitHub репозиторием"""
        content = json.dumps(stats, ensure_ascii=False, indent=2)
        return await self._github_put_file(
            "stats.json", 
            content, 
            f"stats: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        )
    
    async def sync_program_to_github(self):
        """Отметки заданий в репозиторий — отдельным файлом от stats.json."""
        content = json.dumps(self.program, ensure_ascii=False, indent=2)
        return await self._github_put_file(
            "program.json",
            content,
            f"program: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        )

    async def edit_message_keyboard(self, message_id, keyboard):
        """Заменить только клавиатуру, не трогая текст сообщения.

        editMessageText переписал бы текст целиком, а прогресс в нём
        хранится по индексам строк — правка текста ради кнопки сломала бы
        отметки задач.
        """
        try:
            url = (f"https://api.telegram.org/bot{self.telegram_token}"
                   f"/editMessageReplyMarkup")
            payload = {'chat_id': self.chat_id, 'message_id': message_id,
                       'reply_markup': json.dumps(keyboard)}
            async with self.session.post(url, json=payload) as resp:
                if resp.status != 200:
                    logger.error("❌ Клавиатура не обновлена: %s", resp.status)
                    return False
                return True
        except Exception as e:
            logger.error(f"❌ Ошибка обновления клавиатуры: {e}")
            return False

    def load_message_states(self):
        """Загружает состояния сообщений из файла"""
        try:
            if os.path.exists(self.message_state_file):
                with open(self.message_state_file, 'r', encoding='utf-8') as f:
                    # Преобразуем строковые ключи обратно в int
                    data = json.load(f)
                    return {int(k): v for k, v in data.items()}
            return {}
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки состояний сообщений: {e}")
            return {}
    
    async def load_tasks_from_stats(self):
        """
        Загружает задачи из stats.json
        Сначала пробует с GitHub (основной источник), потом локально
        """
        today_key = self.get_today_key()
        
        # 1. Пробуем загрузить с GitHub (актуальные данные от notifier.py)
        try:
            content = await self._github_get_file("stats.json")
            if content:
                stats = json.loads(content)
                if today_key in stats and '_tasks' in stats[today_key]:
                    tasks = stats[today_key]['_tasks']
                    if 'morning' not in tasks:
                        tasks['morning'] = []
                    logger.info(f"✅ Задачи загружены с GitHub: day={len(tasks.get('day', []))}, evening={len(tasks.get('evening', []))}")
                    return tasks
                else:
                    logger.warning(f"⚠️ На GitHub нет задач за {today_key}")
        except Exception as e:
            logger.warning(f"⚠️ Ошибка загрузки с GitHub: {e}")
        
        # 2. Fallback: локальный файл
        try:
            stats = self.load_stats()
            
            if today_key in stats and '_tasks' in stats[today_key]:
                tasks = stats[today_key]['_tasks']
                if 'morning' not in tasks:
                    tasks['morning'] = []
                logger.info(f"✅ Задачи загружены из локального stats: day={len(tasks.get('day', []))}, evening={len(tasks.get('evening', []))}")
                return tasks
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки из локального stats: {e}")
        
        return {'morning': [], 'day': [], 'cant_do': [], 'evening': []}
    
    def save_message_states(self):
        """Сохраняет состояния сообщений ЛОКАЛЬНО (быстро, для toggle).

        Перед записью — прополка (04.08.2026): держим только последние
        STATE_KEEP_LAST состояний. Прогресс правится лишь у свежих
        сообщений, а файл целиком уезжал в каждый коммит синка."""
        try:
            # Прополка и в памяти тоже — иначе процесс помнит одно,
            # а рестарт поднимает другое.
            self.message_state = prune_message_states(self.message_state)
            # Преобразуем int ключи в строки для JSON
            data = {str(k): v for k, v in self.message_state.items()}
            with open(self.message_state_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения состояний сообщений: {e}")
            return False
    
    async def sync_message_states_to_github(self):
        """Синхронизирует message_states.json с GitHub (переживает рестарт сервиса)"""
        try:
            self.message_state = prune_message_states(self.message_state)
            data = {str(k): v for k, v in self.message_state.items()}
            content = json.dumps(data, ensure_ascii=False, indent=2)
            return await self._github_put_file(
                "message_states.json",
                content,
                f"states: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            )
        except Exception as e:
            logger.warning(f"⚠️ Ошибка синхронизации states с GitHub: {e}")
            return False
    
    async def load_message_states_from_github(self):
        """Загружает message_states.json с GitHub при старте"""
        try:
            content = await self._github_get_file("message_states.json")
            if content:
                data = json.loads(content)
                # Прополка на загрузке: репо-версия может быть старой и
                # раздутой — незачем тащить её обратно в память и в синк.
                data = prune_message_states(data)
                states = {int(k): v for k, v in data.items()}
                logger.info(f"✅ Загружено {len(states)} состояний сообщений с GitHub")
                return states
        except Exception as e:
            logger.warning(f"⚠️ Ошибка загрузки states с GitHub: {e}")
        return {}
    
    def merge_github_states(self, github_states):
        """Догрузить состояния из репо-реплики к локальным и прополоть.

        Локальные новее (процесс пишет их на каждое нажатие), поэтому с
        GitHub берём только отсутствующие ключи. Прополка сразу после
        слияния: иначе процесс держит в памяти весь исторический набор до
        первого нажатия кнопки (04.08: «Загружено 20 … Всего: 64»)."""
        for k, v in github_states.items():
            if k not in self.message_state:
                self.message_state[k] = v
        self.message_state = prune_message_states(self.message_state)
        return self.message_state

    async def load_stats_from_github(self):
        """Загружает stats.json с GitHub при старте и СЛИВАЕТ с локальным.

        Раньше репо-версия перезаписывала локальный файл — если синк на
        запись падал (протухший токен, 401), рестарт бота откатывал
        стату к последнему удачному пушу. Теперь при конфликте дня
        побеждает локальная запись (см. merge_stats)."""
        try:
            content = await self._github_get_file("stats.json")
            if content:
                data = json.loads(content)
                # Фильтруем только реальные даты
                github_stats = {k: v for k, v in data.items()
                                if k not in ['_info', '_format'] and '-' in k}
                logger.info(f"✅ Загружено {len(github_stats)} дней статистики с GitHub")

                local_stats = {}
                try:
                    with open(self.stats_file, 'r', encoding='utf-8') as f:
                        raw = json.load(f)
                    local_stats = {k: v for k, v in raw.items()
                                   if k not in ['_info', '_format'] and '-' in k}
                except (FileNotFoundError, json.JSONDecodeError):
                    pass

                stats = merge_stats(github_stats, local_stats)
                if local_stats and stats != github_stats:
                    ahead = sorted(set(local_stats) - set(github_stats))
                    logger.info(f"🛡 Локальная стата впереди GitHub "
                                f"({len(ahead)} дн.: {ahead[-3:]}) — слито без отката")

                # Сохраняем локально
                with open(self.stats_file, 'w', encoding='utf-8') as f:
                    json.dump(stats, f, ensure_ascii=False, indent=2)

                return stats
        except Exception as e:
            logger.warning(f"⚠️ Ошибка загрузки stats с GitHub: {e}")
        return {}
    
    def get_today_key(self):
        """Возвращает ключ для сегодняшнего дня"""
        return datetime.now().strftime("%Y-%m-%d")
    
    def calculate_percentage(self, completed, total):
        """Вычисляет процент выполнения"""
        if total == 0:
            return 0
        return int((len(completed) / total) * 100)
    
    def get_progress_bar(self, percentage, length=8):
        """Создаёт прогресс-бар"""
        filled = int((percentage / 100) * length)
        return '▓' * filled + '░' * (length - filled)
    
    def get_motivation(self, percentage):
        """Возвращает мотивационное сообщение в RPG стиле"""
        import random
        
        if percentage >= 100:
            phrases = [
                "👑 100%. День принадлежит тебе полностью.",
                "👑 Абсолютный контроль. Так выглядит порядок.",
                "👑 Ни одной сданной позиции. Красавчик."
            ]
        elif percentage >= 95:
            phrases = [
                "💎 Несгибаемый. Почти идеальный день.",
                "💎 Такой уровень держат единицы.",
                "💎 Ещё чуть-чуть — и корона."
            ]
        elif percentage >= 85:
            phrases = [
                "🦾 Железная воля. День под контролем.",
                "🦾 Ты сильнее своих отговорок.",
                "🦾 Мощно. Завтра — добить до короны."
            ]
        elif percentage >= 70:
            phrases = [
                "🎯 Дисциплина работает. Держи темп.",
                "🎯 Хороший день. Система крепнет.",
                "🎯 Достойно. Следующий уровень рядом."
            ]
        elif percentage >= 50:
            phrases = [
                "⚙ Система запущена. Наращивай обороты.",
                "⚙ Половина взята. Дожимай.",
                "⚙ Рабочий день. Не идеальный — рабочий."
            ]
        elif percentage >= 30:
            phrases = [
                "🚶 Ты в режиме. Шаг за шагом.",
                "🚶 Движение есть. Ускоряйся.",
                "🚶 База заложена. Завтра — больше."
            ]
        else:
            phrases = [
                "😴 День ушёл в хаос. Завтра вернёшь контроль.",
                "😴 Ноль драмы. Просто начни заново утром.",
                "😴 Плохой день — не плохая жизнь. Перезапуск утром."
            ]
        
        return random.choice(phrases)
    
    # ═══════════════════════════════════════════════════════════════════════════════
    # LEVEL SYSTEM
    # ═══════════════════════════════════════════════════════════════════════════════
    
    def get_level(self, percentage):
        """Уровень по проценту выполнения. Таблица уровней — в core.LEVELS,
        общая с notifier (раньше лестница if/elif жила только здесь)."""
        return _core_get_level(percentage)

    def get_level_bar(self, percentage):
        """
        Создаёт визуальную шкалу уровня
        """
        level = self.get_level(percentage)
        return level['bar']
    
    def calculate_streak_90(self, stats):
        """
        Считает текущий streak дней с ≥90%
        Для получения Black level нужно 7 дней подряд
        """
        today = datetime.now()
        streak = 0
        
        # Идём назад от сегодня
        for i in range(30):  # Максимум 30 дней назад
            day = today - timedelta(days=i)
            day_key = day.strftime("%Y-%m-%d")
            
            if day_key in stats:
                percentage = stats[day_key].get('percentage', 0)
                if percentage >= 90:
                    streak += 1
                else:
                    break  # Streak прервался
            else:
                break  # Нет данных = streak прервался
        
        return streak
    
    def is_black_level(self, stats):
        """Проверяет достигнут ли Black level (7 дней ≥90%)"""
        return self.calculate_streak_90(stats) >= 7
    
    def get_level_display(self, percentage, stats):
        """
        Формирует игровое отображение уровня с XP-баром
        """
        level = self.get_level(percentage)
        streak_90 = self.calculate_streak_90(stats)
        is_black = streak_90 >= 7
        
        # Rank bar
        rank_bar = level['bar']
        
        if is_black:
            status = f"🖤 <b>Легенда</b> (Уровень 8)\n"
            status += f"{rank_bar}\n"
            status += f"⚡ {streak_90} дней подряд ≥90%"
        else:
            status = f"{level['emoji']} <b>{level['name']}</b> (Уровень {level['rank']})\n"
            status += f"{rank_bar}\n"
            status += f"→ {level['phrase']}"
            
            # Показываем прогресс до следующего уровня
            if percentage < 100:
                thresholds = [30, 50, 70, 85, 95, 100]
                for next_threshold in thresholds:
                    if percentage < next_threshold:
                        tasks_to_next = max(1, int((next_threshold - percentage) / 3))
                        status += f"\n📈 До следующего: +{tasks_to_next} задач"
                        break
            
            if streak_90 > 0:
                status += f"\n🔥 Серия: {streak_90}/7 дней"
        
        return status
    
    def get_week_stats(self, stats):
        """Считает статистику за неделю"""
        today = datetime.now()
        total = 0
        count = 0
        streak_70 = 0
        current_streak = 0
        days_above_90 = 0
        
        for i in range(7):
            day = today - timedelta(days=i)
            day_key = day.strftime("%Y-%m-%d")
            
            if day_key in stats:
                percentage = stats[day_key].get('percentage', 0)
                total += percentage
                count += 1
                
                if percentage >= 90:
                    days_above_90 += 1
                
                if percentage >= 70:
                    current_streak += 1
                    streak_70 = max(streak_70, current_streak)
                else:
                    current_streak = 0
        
        avg = int(total / count) if count > 0 else 0
        return {
            'avg': avg,
            'days': count,
            'streak_70': streak_70,
            'days_above_90': days_above_90,
            'level': self.get_level(avg)
        }
    
    def get_top_failed_tasks(self, stats, days=7):
        """
        Анализирует какие задачи чаще всего НЕ выполняются за период
        Возвращает топ-3 с процентом выполнения
        """
        today = datetime.now()
        task_stats = {}  # task_name -> {'completed': 0, 'total': 0}
        
        for i in range(days):
            day = today - timedelta(days=i)
            day_key = day.strftime("%Y-%m-%d")
            
            if day_key not in stats:
                continue
            
            day_data = stats[day_key]
            
            # Получаем список задач из _tasks (сохраняется notifier.py)
            all_tasks_dict = day_data.get('_tasks', {})
            
            # Анализируем день и вечер
            for section in ['day', 'evening']:
                section_data = day_data.get(section, {})
                completed_indices = section_data.get('completed', [])
                
                # Задачи для этой секции
                section_tasks = all_tasks_dict.get(section, [])
                if not section_tasks:
                    continue
                
                for idx, task in enumerate(section_tasks):
                    clean_task = task.strip()
                    if not clean_task:
                        continue
                    
                    if clean_task not in task_stats:
                        task_stats[clean_task] = {'completed': 0, 'total': 0}
                    
                    task_stats[clean_task]['total'] += 1
                    
                    # Проверяем выполнена ли задача (по индексу)
                    if idx in completed_indices:
                        task_stats[clean_task]['completed'] += 1
        
        # Считаем процент выполнения и сортируем по невыполнению
        failed_tasks = []
        for task, data in task_stats.items():
            if data['total'] >= 2:  # Минимум 2 раза встречалась
                completion_rate = int((data['completed'] / data['total']) * 100)
                failed_tasks.append({
                    'task': task[:25] + '...' if len(task) > 25 else task,
                    'rate': completion_rate,
                    'completed': data['completed'],
                    'total': data['total']
                })
        
        # Сортируем по проценту выполнения (от меньшего к большему)
        failed_tasks.sort(key=lambda x: x['rate'])
        
        return failed_tasks[:3]  # Топ-3 самых проблемных
    
    def get_week_penalty_stats(self, stats, days=7):
        """
        Собирает статистику штрафов за неделю
        Возвращает: {
            'total_pushups': int,
            'days_with_penalty': int,
            'total_fails': int,
            'top_violations': [{'rule': str, 'count': int}, ...]
        }
        """
        today = datetime.now()
        total_pushups = 0
        days_with_penalty = 0
        total_fails = 0
        violations = {}  # rule_name -> count
        
        for i in range(days):
            day = today - timedelta(days=i)
            day_key = day.strftime("%Y-%m-%d")
            
            if day_key not in stats:
                continue
            
            day_data = stats[day_key]
            
            # Считаем отжимания
            pushups = day_data.get('penalty_pushups', 0)
            if pushups > 0:
                total_pushups += pushups
                days_with_penalty += 1
            
            # Считаем срывы
            cant_do = day_data.get('cant_do', {})
            completed_indices = cant_do.get('completed', [])
            fails_count = len(completed_indices)
            total_fails += fails_count
            
            # Получаем названия нарушенных правил
            tasks_dict = day_data.get('_tasks', {})
            cant_do_tasks = tasks_dict.get('cant_do', [])
            
            for idx in completed_indices:
                if isinstance(idx, int) and idx < len(cant_do_tasks):
                    rule = cant_do_tasks[idx]
                    # Очищаем от "Не " и форматирования
                    clean_rule = rule.replace('НЕ ', '').replace('Не ', '')
                    clean_rule = clean_rule.split('<')[0].strip()  # Убираем <i>...</i>
                    clean_rule = clean_rule[:30]  # Обрезаем длинные
                    
                    if clean_rule not in violations:
                        violations[clean_rule] = 0
                    violations[clean_rule] += 1
        
        # Топ нарушений (сортируем по частоте)
        top_violations = sorted(
            [{'rule': k, 'count': v} for k, v in violations.items()],
            key=lambda x: x['count'],
            reverse=True
        )[:3]
        
        return {
            'total_pushups': total_pushups,
            'days_with_penalty': days_with_penalty,
            'total_fails': total_fails,
            'top_violations': top_violations
        }
    
    def get_month_stats(self, stats):
        """Считает статистику за месяц"""
        today = datetime.now()
        total = 0
        count = 0
        days_above_90 = 0
        days_above_80 = 0
        days_above_70 = 0
        
        for i in range(30):
            day = today - timedelta(days=i)
            day_key = day.strftime("%Y-%m-%d")
            
            if day_key in stats:
                percentage = stats[day_key].get('percentage', 0)
                total += percentage
                count += 1
                
                if percentage >= 90:
                    days_above_90 += 1
                if percentage >= 80:
                    days_above_80 += 1
                if percentage >= 70:
                    days_above_70 += 1
        
        avg = int(total / count) if count > 0 else 0
        return {
            'avg': avg,
            'days': count,
            'days_above_90': days_above_90,
            'days_above_80': days_above_80,
            'days_above_70': days_above_70,
            'level': self.get_level(avg)
        }
    
    def get_section_emoji(self, percentage):
        """Возвращает эмодзи в зависимости от процента выполнения"""
        if percentage >= 90:
            return "✨"  # Идеально
        elif percentage >= 70:
            return "🌟"  # Отлично
        elif percentage >= 50:
            return "👍"  # Хорошо
        elif percentage >= 30:
            return "💪"  # Старайся
        else:
            return "🔥"  # Слабовато
    
    async def send_penalty_message(self, cant_do_count, failed_tasks):
        """Отправляет штрафное сообщение (минималистичный стиль)"""
        try:
            pushups = cant_do_count * 30
            
            penalty_msg = f"<b>ШТРАФ</b>\n\n"
            penalty_msg += f"Срывов: {cant_do_count}\n"
            
            for task in failed_tasks:
                clean_task = task.replace('<i>', '').replace('</i>', '').replace('<b>', '').replace('</b>', '')
                clean_task = clean_task.split('(')[0].strip()
                if clean_task.startswith('НЕ ') or clean_task.startswith('Не '):
                    clean_task = clean_task[3:].strip()
                penalty_msg += f"· {clean_task}\n"
            
            penalty_msg += f"\nЗавтра: {pushups} отжиманий"
            
            await self.send_telegram_message(penalty_msg)
            logger.info(f"⚠️ Штраф: {pushups} отжиманий")
            
        except Exception as e:
            logger.error(f"❌ Ошибка штрафа: {e}")
    
    async def send_daily_summary(self):
        """ЭТАП 4: Отправляет итоги дня в 23:00 - НОВЫЙ ДИЗАЙН"""
        stats = self.load_stats()
        today_key = self.get_today_key()
        
        if today_key not in stats:
            logger.info("📊 Нет данных за сегодня для итогов")
            return
        
        today_data = stats[today_key]
        
        # ОТЛАДКА: Логируем что приходит в today_data
        logger.info(f"📊 DEBUG today_data: {today_data}")
        logger.info(f"📊 DEBUG points={today_data.get('points')}, max_points={today_data.get('max_points')}")
        
        # Получаем данные по секциям
        morning = today_data.get('morning', {})
        day = today_data.get('day', {})
        evening = today_data.get('evening', {})
        cant_do = today_data.get('cant_do', {})
        
        # ОТЛАДКА: Логируем каждую секцию
        logger.info(f"📊 DEBUG morning: completed={morning.get('completed', [])}, total={morning.get('total', 0)}")
        logger.info(f"📊 DEBUG day: completed={day.get('completed', [])}, total={day.get('total', 0)}")
        logger.info(f"📊 DEBUG evening: completed={evening.get('completed', [])}, total={evening.get('total', 0)}")
        logger.info(f"📊 DEBUG cant_do: completed={cant_do.get('completed', [])}, total={cant_do.get('total', 0)}")
        
        # Арифметика — в core.summarize_day (покрыта тестами):
        # «Нельзя делать» в процент не входит, срывы считаются отдельно.
        _s = summarize_day(today_data)
        day_done, day_total = _s['day_done'], _s['day_total']
        evening_done, evening_total = _s['evening_done'], _s['evening_total']
        overall_done, overall_total = _s['overall_done'], _s['overall_total']
        overall_perc = _s['percentage']
        cant_do_fails = _s['fails']
        
        logger.info(f"📊 CALCULATED: day={day_done}/{day_total}, evening={evening_done}/{evening_total}, total={overall_done}/{overall_total} ({overall_perc}%)")
        
        # === ФОРМИРУЕМ СООБЩЕНИЕ (минималистичный стиль) ===
        message = f"<b>ИТОГИ ДНЯ</b> · {datetime.now().strftime('%d.%m.%Y')}\n\n"
        
        # День и Вечер отдельно
        if day_total > 0:
            day_perc = int((day_done / day_total * 100))
            day_bar = self.get_progress_bar(min(100, day_perc), 7)
            message += f"День   {day_bar} {day_done}/{day_total}\n"
        
        if evening_total > 0:
            evening_perc = int((evening_done / evening_total * 100))
            evening_bar = self.get_progress_bar(min(100, evening_perc), 7)
            message += f"Вечер  {evening_bar} {evening_done}/{evening_total}\n"
        
        # ИТОГО
        message += f"\n<b>Итого: {overall_done}/{overall_total} ({overall_perc}%)</b>\n"
        
        # НЕЛЬЗЯ (только если есть срывы)
        if cant_do_fails > 0:
            message += f"Срывов: {cant_do_fails}\n"
        
        message += "\n"
        
        # LEVEL
        level_display = self.get_level_display(overall_perc, stats)
        message += level_display + "\n\n"
        
        # МОТИВАЦИЯ
        message += self.get_motivation(overall_perc)
        
        # Отправляем
        await self.send_telegram_message(message)
        logger.info(f"📊 Итоги дня отправлены: {overall_perc}% (day={day_done}/{day_total}, evening={evening_done}/{evening_total})")
    
    def week_day_row(self, day, stats):
        """Строка одного дня в полоске недели.

        День белого браслета помечается отдельно: задач в этот день нет по
        правилам игры, и рисовать его как «0% 😴» — врать самому себе,
        превращая награду в упрёк.
        """
        name = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'][day.weekday()]
        if is_bracelet_day(day):
            return f"{name} 🤍 белый браслет"
        perc = stats.get(day.strftime("%Y-%m-%d"), {}).get('percentage', 0)
        level = self.get_level(perc)
        return f"{name} {self.get_progress_bar(perc, 7)} {perc}% {level['emoji']}"

    async def send_weekly_summary(self):
        """Отправляет итоги недели с Level System и топ-3 проблемных задач"""
        stats = self.load_stats()
        week_stats = self.get_week_stats(stats)
        streak_90 = self.calculate_streak_90(stats)
        is_black = streak_90 >= 7
        
        # Получаем последние 7 дней
        today = datetime.now()
        week_data = []
        
        for i in range(6, -1, -1):
            day = today - timedelta(days=i)
            week_data.append({'row': self.week_day_row(day, stats),
                              'percentage': stats.get(
                                  day.strftime("%Y-%m-%d"), {}).get(
                                      'percentage', 0)})
        
        # Формируем сообщение
        week_start = (today - timedelta(days=6)).strftime('%d.%m')
        week_end = today.strftime('%d.%m')
        
        message = f"⚔️ <b>ИТОГИ НЕДЕЛИ</b>\n{week_start} — {week_end}\n\n"
        
        # Дни недели с эмодзи уровня
        for day_data in week_data:
            message += f"{day_data['row']}\n"
        
        # Программа «365 дней» — отдельной строкой: у неё свой учёт и она
        # не влияет ни на процент, ни на уровень.
        _prog = self.program_week_line(today.date() if hasattr(today, 'date') else today)
        if _prog:
            message += f"\n{_prog}\n"

        # Средний уровень
        avg_level = week_stats['level']
        message += f"\n<b>Средний:</b> {week_stats['avg']}%\n"
        message += f"{avg_level['emoji']} <b>{avg_level['name']}</b> (Уровень {avg_level['rank']})\n"
        message += f"{avg_level['bar']}\n"
        
        # Streak
        if streak_90 > 0:
            message += f"\n🔥 Серия: {streak_90}/7 дней"
        
        # Black level
        if is_black:
            message += "\n\n🖤 <b>ЛЕГЕНДА!</b>"
            message += "\n⚡ 7 дней подряд ≥90%. Это уже характер."
        
        # ТОП-3 ПРОБЛЕМНЫХ ЗАДАЧ
        top_failed = self.get_top_failed_tasks(stats, days=7)
        if top_failed:
            message += "\n\n⚠️ <b>Зоны роста:</b>\n"
            for i, task in enumerate(top_failed, 1):
                # Прогресс-бар для задачи
                task_bar = self.get_progress_bar(task['rate'], 5)
                message += f"{i}. {task['task']}\n"
                message += f"   {task_bar} {task['rate']}% ({task['completed']}/{task['total']})\n"
        
        # ПОДТЯГИВАНИЯ (пятничный зачёт)
        last_pullups, pullups_date = self.get_last_pullups(days=7)
        if last_pullups is not None:
            goal = 15
            pullups_perc = min(100, int((last_pullups / goal) * 100))
            pullups_bar = self.get_progress_bar(pullups_perc, 7)
            message += f"\n\n💪 <b>Подтягивания:</b> {last_pullups}/{goal}\n"
            message += f"{pullups_bar}\n"
            
            if last_pullups >= goal:
                message += "🏆 <b>ЦЕЛЬ ДОСТИГНУТА!</b>\n"
                message += "Выбери приз: 🍕 Пицца / 🎮 Игра / 📱 Гаджет"
            elif last_pullups >= goal - 2:
                message += "🔥 Почти у цели! Ещё чуть-чуть!"
            else:
                diff = goal - last_pullups
                message += f"→ До цели: +{diff}"
        
        # СТАТИСТИКА ШТРАФОВ
        penalty_stats = self.get_week_penalty_stats(stats, days=7)
        if penalty_stats['total_fails'] > 0:
            message += f"\n\n⚠️ <b>Штрафы недели:</b>\n"
            message += f"Отжиманий: {penalty_stats['total_pushups']}×\n"
            message += f"Дней со срывами: {penalty_stats['days_with_penalty']}/7\n"
            message += f"Всего срывов: {penalty_stats['total_fails']}\n"
            
            if penalty_stats['top_violations']:
                message += "\n<i>Частые нарушения:</i>\n"
                for v in penalty_stats['top_violations']:
                    message += f"· {v['rule']} ({v['count']}×)\n"
        else:
            message += "\n\n✅ <b>Без штрафов!</b> Чистая неделя 🏆"
        
        # Мотивация
        message += "\n"
        if week_stats['avg'] >= 95:
            message += "🏆 ЛЕГЕНДАРНАЯ НЕДЕЛЯ! Ты на пути к величию."
        elif week_stats['avg'] >= 90:
            message += "⚡ Отличный результат! Level Up заслужен."
        elif week_stats['avg'] >= 80:
            message += "🗡️ Спартанская неделя. Враги повержены."
        elif week_stats['avg'] >= 70:
            message += "⚔️ Хорошая работа, самурай. Продолжай."
        else:
            message += "🛡️ Новая неделя — новый шанс. Level Up ждёт."
        
        await self.send_telegram_message(message)
        logger.info(f"📊 Итоги недели отправлены: средний {week_stats['avg']}%, уровень {avg_level['name']}")
    
    async def send_monthly_summary(self):
        """Отправляет итоги месяца с Level System"""
        stats = self.load_stats()
        month_stats = self.get_month_stats(stats)
        streak_90 = self.calculate_streak_90(stats)
        
        today = datetime.now()
        
        # Получаем данные за последние 30 дней
        month_data = []
        for i in range(29, -1, -1):
            day = today - timedelta(days=i)
            day_key = day.strftime("%Y-%m-%d")
            
            if day_key in stats:
                percentage = stats[day_key].get('percentage', 0)
            else:
                percentage = 0
            month_data.append(percentage)
        
        message = f"<b>ИТОГИ МЕСЯЦА</b>\n30 дней\n\n"
        
        # Мини-график (каждый символ = 1 день)
        message += "<code>"
        for i, perc in enumerate(month_data):
            if perc >= 90:
                message += "█"
            elif perc >= 80:
                message += "▓"
            elif perc >= 70:
                message += "▒"
            elif perc > 0:
                message += "░"
            else:
                message += "·"
            
            if (i + 1) % 7 == 0:
                message += "\n"
        message += "</code>\n"
        message += "█90+ ▓80+ ▒70+ ░<70 ·нет\n\n"
        
        # Статистика
        avg_level = month_stats['level']
        message += f"Средний: {month_stats['avg']}%\n"
        message += f"{avg_level['emoji']} {avg_level['name']}\n\n"
        
        message += f"≥90%: {month_stats['days_above_90']}d\n"
        message += f"≥80%: {month_stats['days_above_80']}d\n"
        message += f"≥70%: {month_stats['days_above_70']}d\n"
        
        # Black level
        if streak_90 >= 7:
            message += f"\n🖤 ЛЕГЕНДА · серия {streak_90} дней"
        elif streak_90 > 0:
            message += f"\nСерия: {streak_90}/7"
        
        # Короткая мотивация
        message += "\n\n"
        if month_stats['avg'] >= 90:
            message += "Легендарный месяц."
        elif month_stats['avg'] >= 80:
            message += "Отличный результат."
        elif month_stats['avg'] >= 70:
            message += "Хорошая работа."
        else:
            message += "Следующий месяц будет лучше."
        
        await self.send_telegram_message(message)
        logger.info(f"📊 Итоги месяца отправлены: средний {month_stats['avg']}%")
    
    async def check_schedule(self):
        """Проверяет расписание для отправки итогов"""
        now = datetime.now()
        
        # Итоги дня в 23:00
        if now.hour == 23 and now.minute == 0:
            logger.info("⏰ Время для итогов дня")
            await self.send_daily_summary()
            
            # Итоги недели в воскресенье
            if now.weekday() == 6:  # Воскресенье
                logger.info("⏰ Время для итогов недели")
                await asyncio.sleep(60)  # Подождём минуту после итогов дня
                await self.send_weekly_summary()
            
            # Итоги месяца 1-го числа
            if now.day == 1:
                logger.info("⏰ Время для итогов месяца")
                await asyncio.sleep(120)  # Подождём 2 минуты
                await self.send_monthly_summary()
    
    async def send_telegram_message(self, message, reply_markup=None):
        """Отправляет сообщение в Telegram (с опциональной клавиатурой)"""
        try:
            url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
            payload = {
                'chat_id': self.chat_id,
                'text': message,
                'parse_mode': 'HTML'
            }
            if reply_markup:
                payload['reply_markup'] = reply_markup
            
            async with self.session.post(url, json=payload, timeout=10) as response:
                if response.status == 200:
                    logger.info("✅ Сообщение отправлено")
                    return True
                else:
                    logger.error(f"❌ Ошибка отправки: {response.status}")
                    return False
        except Exception as e:
            logger.error(f"❌ Ошибка: {e}")
            return False
    
    # Алиас для обратной совместимости
    async def send_message(self, text, reply_markup=None):
        return await self.send_telegram_message(text, reply_markup)
    
    async def edit_message(self, message_id, text, reply_markup=None):
        """Редактирует сообщение"""
        try:
            url = f"https://api.telegram.org/bot{self.telegram_token}/editMessageText"
            payload = {
                'chat_id': self.chat_id,
                'message_id': message_id,
                'text': text,
                'parse_mode': 'HTML'
            }
            
            if reply_markup:
                payload['reply_markup'] = reply_markup
            
            async with self.session.post(url, json=payload, timeout=10) as response:
                if response.status == 200:
                    logger.info("✅ Сообщение обновлено")
                    return True
                else:
                    error_text = await response.text()
                    logger.error(f"❌ Ошибка обновления: {response.status} - {error_text}")
                    return False
        except Exception as e:
            logger.error(f"❌ Ошибка: {e}")
            return False
    
    async def answer_callback_query(self, callback_query_id, text=None):
        """Отвечает на callback query"""
        try:
            url = f"https://api.telegram.org/bot{self.telegram_token}/answerCallbackQuery"
            payload = {'callback_query_id': callback_query_id}
            
            if text:
                payload['text'] = text
            
            async with self.session.post(url, json=payload, timeout=10) as response:
                return response.status == 200
        except Exception as e:
            logger.error(f"❌ Ошибка: {e}")
            return False
    
    async def process_callback(self, callback_data, callback_query_id, message_id, message_text):
        """Обрабатывает callback от кнопок"""
        logger.info(f"📞 Получен callback: {callback_data}")
        
        if callback_data.startswith('weight_'):
            # Взвешивание — своя история в stats.json, на процент дня и
            # уровень не влияет.
            try:
                value = float(callback_data.split('_', 1)[1])
            except ValueError:
                await self.answer_callback_query(callback_query_id, "Не понял")
                return
            previous, _ = self.get_last_weight(days=7)
            await self.save_weight(value)
            await self.sync_stats_to_github(self.load_stats())
            await self.answer_callback_query(
                callback_query_id, weight_verdict(value, previous))
            await self.edit_message(
                message_id,
                f"⚖️ <b>КОНТРОЛЬНОЕ ВЗВЕШИВАНИЕ</b>\n\n"
                f"{weight_verdict(value, previous)}")
            return

        if callback_data == 'update_progress':
            # Показываем чек-лист
            await self.show_checklist(message_id, message_text)
            await self.answer_callback_query(callback_query_id, "Отметь выполненные задачи ✅")
        
        elif callback_data.startswith('toggle_'):
            # Переключаем задачу
            # Формат: toggle_day_0, toggle_evening_5, toggle_cant_do_1
            if '_cant_do_' in callback_data:
                # Обрабатываем cant_do отдельно (два подчёркивания)
                task_idx = int(callback_data.split('_')[-1])
                period = 'cant_do'
            else:
                # Обычный формат: toggle_day_0
                parts = callback_data.split('_')
                period = parts[1]  # day/evening
                task_idx = int(parts[2])
            
            await self.toggle_task(message_id, period, task_idx)
            await self.answer_callback_query(callback_query_id)
        
        elif callback_data in ('task_done', 'task_skip'):
            # Задание дня. Отметка идёт в program.json и не трогает
            # статистику дня — это разные учёты.
            day = self._message_date((message_text or "").split("\n", 1)[0])
            status = 'done' if callback_data == 'task_done' else 'skip'
            if self.record_task_result(day, status):
                await self.sync_program_to_github()
                await self.edit_message_keyboard(
                    message_id, self._redraw_keyboard(message_text))
            await self.answer_callback_query(
                callback_query_id,
                "Записал ✅" if status == 'done' else "Ок, отложили")

        elif callback_data == 'save_progress':
            # Сохраняем прогресс
            await self.save_progress(message_id)
            await self.answer_callback_query(callback_query_id, "✅ Прогресс сохранён!")
        
        elif callback_data == 'vacation':
            await self.set_vacation(message_id)
            await self.answer_callback_query(callback_query_id, "🏖 Отпуск включён на сегодня")

        elif callback_data == 'cancel_update':
            # Отменяем обновление
            await self.cancel_update(message_id)
            await self.answer_callback_query(callback_query_id, "❌ Отменено")
        
        elif callback_data == 'header':
            # Заголовки не кликабельны
            await self.answer_callback_query(callback_query_id)
        
        elif callback_data.startswith('pullups_'):
            # Зачёт подтягиваний
            count = int(callback_data.split('_')[1])
            await self.save_pullups(count)
            
            # Формируем ответ
            goal = 15
            if count >= goal:
                response = f"🏆 <b>ЦЕЛЬ ДОСТИГНУТА!</b>\n\n"
                response += f"💪 Подтягивания: {count}/{goal}\n"
                response += f"▓▓▓▓▓▓▓▓▓▓ 100%\n\n"
                response += "🎁 Выбери свой приз:\n"
                response += "🍕 Пицца | 🎮 Игра | 📱 Гаджет"
                await self.answer_callback_query(callback_query_id, f"🏆 {count} раз! Цель достигнута!")
            else:
                progress_pct = int((count / goal) * 100)
                filled = int(progress_pct / 10)
                bar = '▓' * filled + '░' * (10 - filled)
                remaining = goal - count
                response = f"✅ <b>Записано: {count} подтягиваний</b>\n\n"
                response += f"💪 Прогресс: {count}/{goal}\n"
                response += f"{bar} {progress_pct}%\n\n"
                response += f"→ Ещё {remaining} до цели!"
                await self.answer_callback_query(callback_query_id, f"✅ Записано: {count}")
            
            # Обновляем сообщение
            await self.edit_message(message_id, response, None)
    
    async def show_checklist(self, message_id, original_message):
        """Показывает чек-лист для отметки задач"""
        
        # Если состояние уже существует, используем сохранённый оригинал
        if message_id in self.message_state:
            # Используем уже сохранённые данные
            state = self.message_state[message_id]
            text = self.format_checklist_message(state['tasks'], state['completed'])
            keyboard = self.create_checklist_keyboard(state['tasks'], state['completed'])
            await self.edit_message(message_id, text, keyboard)
            return
        
        # Первый вызов - парсим задачи из оригинального сообщения
        tasks = self.parse_tasks(original_message)
        
        # ПРОВЕРКА: если задач нет - пробуем загрузить из stats.json
        total_tasks = len(tasks['morning']) + len(tasks['day']) + len(tasks['cant_do']) + len(tasks['evening'])
        if total_tasks == 0:
            # Пробуем загрузить из stats.json (сохраняется в notifier.py)
            tasks = await self.load_tasks_from_stats()
            total_tasks = len(tasks.get('day', [])) + len(tasks.get('cant_do', [])) + len(tasks.get('evening', []))
            
            if total_tasks > 0:
                logger.info(f"✅ Задачи загружены из stats.json: {total_tasks} задач")
            else:
                error_text = (
                    "⚠️ <b>Ошибка:</b> Не удалось загрузить задачи.\n\n"
                    "Подожди следующего утреннего/вечернего сообщения."
                )
                keyboard = {
                    'inline_keyboard': [
                        [{'text': '❌ Закрыть', 'callback_data': 'cancel_update'}]
                    ]
                }
                await self.edit_message(message_id, error_text, keyboard)
                return
        
        # Загружаем существующий прогресс за сегодня
        today_key = self.get_today_key()
        stats = self.load_stats()
        
        # Проверяем есть ли уже данные за сегодня
        if today_key in stats:
            # Загружаем существующие выполненные задачи
            existing = stats[today_key]
            completed = {
                'morning': existing.get('morning', {}).get('completed', []),
                'day': existing.get('day', {}).get('completed', []),
                'cant_do': existing.get('cant_do', {}).get('completed', []),
                'evening': existing.get('evening', {}).get('completed', [])
            }
            logger.info(f"📊 Загружен существующий прогресс за {today_key}")
        else:
            # Новый день, начинаем с нуля
            completed = {'morning': [], 'day': [], 'cant_do': [], 'evening': []}
        
        # Сохраняем состояние
        self.message_state[message_id] = {
            'tasks': tasks,
            'completed': completed,
            'original_text': original_message,  # Сохраняем ЧИСТЫЙ оригинал
            'clean_original': original_message  # Дублируем для безопасности
        }
        
        # Сохраняем в файл
        self.save_message_states()
        
        # Формируем сообщение и клавиатуру
        text = self.format_checklist_message(tasks, completed)
        keyboard = self.create_checklist_keyboard(tasks, completed)
        
        await self.edit_message(message_id, text, keyboard)
    
    async def toggle_task(self, message_id, period, task_idx):
        """Переключает статус задачи"""
        if message_id not in self.message_state:
            logger.error(f"❌ Состояние для сообщения {message_id} не найдено")
            return
        
        state = self.message_state[message_id]
        completed = state['completed'][period]
        
        # Переключаем
        if task_idx in completed:
            completed.remove(task_idx)
            logger.info(f"☐ Задача {period}[{task_idx}] снята")
        else:
            completed.append(task_idx)
            logger.info(f"☑ Задача {period}[{task_idx}] отмечена")
        
        # Сохраняем в файл
        self.save_message_states()
        
        # Обновляем сообщение
        text = self.format_checklist_message(state['tasks'], state['completed'])
        keyboard = self.create_checklist_keyboard(state['tasks'], state['completed'])
        await self.edit_message(message_id, text, keyboard)
    
    def load_program(self):
        """Отметки заданий дня. Отсутствие файла — нормальный первый запуск."""
        try:
            with open(self.program_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def save_program(self):
        try:
            with open(self.program_file, 'w', encoding='utf-8') as f:
                json.dump(self.program, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"❌ Не сохранил program.json: {e}")

    def record_task_result(self, day, status):
        """Отметить задание дня как «сделал» или «не сегодня».

        «Не сегодня» — равноправный ответ, а не провал: он даёт ровно те
        же данные и нужен, чтобы чинить пул, а не оценивать человека.
        Категория сохраняется — без неё нельзя увидеть, какие темы
        стабильно не делаются.
        """
        task = task_of_the_day(day)
        if not task:
            return False
        self.program[day.strftime("%Y-%m-%d")] = {
            'status': status,
            'category': task['category'],
            'task': task['task'],
        }
        self.save_program()
        return True

    def program_week_line(self, day):
        """Строка про задания недели для воскресного итога.

        Без стрика: на длинной дистанции один пропуск на 340-й день
        обнуляет год, и человек бросает программу целиком.
        """
        answered, done, skipped_cats = 0, 0, []
        for i in range(7):
            key = (day - timedelta(days=i)).strftime("%Y-%m-%d")
            rec = self.program.get(key)
            if not rec:
                continue
            answered += 1
            if rec['status'] == 'done':
                done += 1
            else:
                skipped_cats.append(rec['category'])
        if not answered:
            return ''
        line = f"🎯 Задания недели: {done} из {answered}"
        if skipped_cats:
            line += f" · отложено: {', '.join(dict.fromkeys(skipped_cats))}"
        return line

    def _redraw_keyboard(self, message_text=""):
        """Клавиатура при перерисовке сообщения. Ссылка на страницу дня —
        ТОЛЬКО в утреннем сообщении (09.07); день и вечер получают лишь
        кнопку прогресса. Раньше трекер хардкодил ссылки во всех трёх
        сообщениях при каждом edit — они «возвращались» в вечер/день.

        Список страниц берётся из core (05.08.2026). До этого он был
        прописан здесь копией и разъехался с нотификатором: утром
        приходила одна страница дня, а после первого нажатия трекер
        перерисовывал клавиатуру и возвращал все четыре старые ссылки.

        Дата берётся из заголовка самого сообщения, а не из системных
        часов: правка вчерашнего сообщения не должна подменять ссылку на
        сегодняшнюю страницу."""
        rows = [[{'text': '🔄 Обновить прогресс', 'callback_data': 'update_progress'}]]
        header = (message_text or "").split("\n", 1)[0]
        # Утреннее сообщение узнаём по эмодзи заголовка: 🌅 — утро,
        # ☀️ — дневной блок, 🌙 — вечер. По фразе «Доброе утро» было
        # нельзя: воскресный заголовок — «🌅 Воскресенье», и в воскресенье
        # терялись и кнопки задания, и ссылка на страницу дня.
        # Проверяем ТОЛЬКО первую строку, чтобы подзаголовок
        # «Дневные задачи · утро» не сбивал.
        if '🌅' not in header:
            return {'inline_keyboard': rows}

        day = self._message_date(header)
        if task_of_the_day(day):
            status = self.program.get(day.strftime("%Y-%m-%d"), {}).get('status')
            rows.append([
                {'text': ('✅ Сделал' if status == 'done' else 'Сделал'),
                 'callback_data': 'task_done'},
                {'text': ('👉 Не сегодня' if status == 'skip' else 'Не сегодня'),
                 'callback_data': 'task_skip'},
            ])

        page = page_of_the_day(day)
        if page:
            rows.append([{'text': f'{page["emoji"]} {page["title"]}',
                          'url': page_url(page)}])
        return {'inline_keyboard': rows}

    @staticmethod
    def _message_date(header):
        """Дата из заголовка сообщения, иначе сегодня."""
        return parse_ddmmyyyy(header, date.today())

    @staticmethod
    def blocks_fullness(completed_day, day_total, morning_count,
                        completed_evening, evening_total):
        """Полнота блоков (10.07): утро и день делят секцию 'day' —
        граница = morning_count (пишется нотификатором при утренней отправке).
        morning: индексы [0..mc), day: [mc..day_total), evening: своя секция.
        morning_count отсутствует/0 -> утро не выделяется (fallback: вся
        секция 'day' считается блоком 'day'). Пустой блок полным не считается."""
        cd = set(completed_day or [])
        mc = morning_count or 0
        out = {}
        if mc > 0:
            out['morning'] = all(i in cd for i in range(mc))
            out['day'] = day_total > mc and all(i in cd for i in range(mc, day_total))
        else:
            out['morning'] = False
            out['day'] = day_total > 0 and all(i in cd for i in range(day_total))
        out['evening'] = evening_total > 0 and \
            len(set(completed_evening or [])) >= evening_total
        return out

    async def save_progress(self, message_id):
        """Сохраняет прогресс в stats.json"""
        if message_id not in self.message_state:
            logger.error(f"❌ Состояние для сообщения {message_id} не найдено")
            return
        
        state = self.message_state[message_id]
        today_key = self.get_today_key()
        
        # Загружаем статистику. База — СВЕЖАЯ с GitHub (08.07: локальная копия
        # сервера не содержит _tasks, которые пишет notifier из Actions;
        # сохранение с локальной базы затирало их в репо при каждом нажатии).
        stats = self.load_stats()
        try:
            content = await self._github_get_file("stats.json")
            if content:
                stats = json.loads(content)
        except Exception as e:
            logger.warning(f"⚠️ GitHub stats как база недоступен ({e}) — локальная")
        
        # ЗАПОМИНАЕМ старое количество срывов ДО объединения (для проверки дублирования штрафов)
        previous_cant_do_count = 0
        if today_key in stats and 'cant_do' in stats[today_key]:
            previous_cant_do_count = len(stats[today_key]['cant_do'].get('completed', []))

        # Бинго-триггер (09.07): какие блоки БЫЛИ полными до этого нажатия —
        # чтобы поздравить только за блок, закрытый именно сейчас, без повторов.
        _rec_day = (stats.get(today_key) or {}).get('day', {})
        _rec_eve = (stats.get(today_key) or {}).get('evening', {})
        _mc = (stats.get(today_key) or {}).get('_morning_day_count', 0)
        _prev_full = self.blocks_fullness(
            _rec_day.get('completed', []), _rec_day.get('total', 0), _mc,
            _rec_eve.get('completed', []), _rec_eve.get('total', 0))
        
        # ВАЖНО: Объединяем с существующими данными за сегодня!
        merged_totals = {}  # Сохраняем merged totals отдельно
        
        if today_key in stats:
            # Уже есть данные за сегодня - объединяем
            existing = stats[today_key]
            
            # Объединяем выполненные задачи (убираем дубликаты)
            for period in ['morning', 'day', 'cant_do', 'evening']:
                existing_completed = set(existing.get(period, {}).get('completed', []))
                new_completed = set(state['completed'][period])
                # Объединяем множества
                combined_completed = list(existing_completed | new_completed)
                
                # Обновляем completed
                state['completed'][period] = combined_completed
                
                # Объединяем total - берём максимум из существующего и нового
                existing_total = existing.get(period, {}).get('total', 0)
                new_total = len(state['tasks'].get(period, []))
                merged_totals[period] = max(existing_total, new_total)
                
            logger.info(f"📊 Объединены данные за {today_key}")
        else:
            # Нет данных - используем текущие totals
            for period in ['morning', 'day', 'cant_do', 'evening']:
                merged_totals[period] = len(state['tasks'].get(period, []))
        
        # Считаем общие показатели (ТОЛЬКО день + вечер, БЕЗ morning и cant_do!)
        total_completed = (
            len(state['completed']['day']) +
            len(state['completed']['evening'])
        )
        total_tasks = merged_totals['day'] + merged_totals['evening']
        
        percentage = int((total_completed / total_tasks * 100)) if total_tasks > 0 else 0
        
        logger.info(f"📊 ПОДСЧЁТ: day={len(state['completed']['day'])}/{merged_totals['day']}, evening={len(state['completed']['evening'])}/{merged_totals['evening']}, total={total_completed}/{total_tasks} ({percentage}%)")
        
        # НЕ перезаписываем запись дня целиком: notifier хранит в ней _tasks
        # (единая вселенная задач для чек-листов утро/день) — затирание ломало
        # индексацию галочек между блоками. Merge поверх существующего.
        _day_record = dict(stats.get(today_key) or {})
        _day_record.update({
            'morning': {
                'completed': state['completed']['morning'],
                'total': merged_totals['morning']
            },
            'day': {
                'completed': state['completed']['day'],
                'total': merged_totals['day']
            },
            'cant_do': {
                'completed': state['completed']['cant_do'],
                'total': merged_totals['cant_do']
            },
            'evening': {
                'completed': state['completed']['evening'],
                'total': merged_totals['evening']
            },
            'percentage': percentage,
            'points': total_completed,
            'max_points': total_tasks,
            'penalty': len(state['completed']['cant_do']) > 0,
            'penalty_pushups': len(state['completed']['cant_do']) * 30
        })
        stats[today_key] = _day_record
        
        # Сохраняем в файл
        save_success = await self.save_stats(stats)
        logger.info(f"💾 Save stats result: {save_success}")
        
        if save_success:
            # НОВОЕ: Отправляем штрафное сообщение ТОЛЬКО если количество срывов УВЕЛИЧИЛОСЬ
            current_cant_do_count = len(state['completed']['cant_do'])
            
            logger.info(f"⚠️ Штрафы: было={previous_cant_do_count}, стало={current_cant_do_count}")
            
            # Отправляем штраф ТОЛЬКО если количество УВЕЛИЧИЛОСЬ
            if current_cant_do_count > previous_cant_do_count:
                # Получаем названия задач НЕЛЬЗЯ
                cant_do_tasks = state['tasks']['cant_do']
                failed_tasks = [cant_do_tasks[i] for i in state['completed']['cant_do']]
                
                # Отправляем штрафное сообщение
                await self.send_penalty_message(current_cant_do_count, failed_tasks)
                logger.info(f"📤 Отправлен штраф: {current_cant_do_count} срывов (увеличилось с {previous_cant_do_count})")
            elif current_cant_do_count > 0:
                logger.info(f"⏭️ Штраф уже отправлен ранее ({current_cant_do_count} срывов = {previous_cant_do_count}), пропускаем")

            # Бинго-триггер (09.07): блок закрыт, если ВСЕ его задачи отмечены.
            # Поздравляем только за блоки, ставшие полными ИМЕННО СЕЙЧАС
            # (не были полными до нажатия) — без повторов на каждое сохранение.
            try:
                import bingo_messages as bingo
                now_full = self.blocks_fullness(
                    state['completed']['day'], merged_totals.get('day', 0), _mc,
                    state['completed']['evening'], merged_totals.get('evening', 0))
                newly = [s for s in ('morning', 'day', 'evening')
                         if now_full[s] and not _prev_full.get(s)]
                perfect_now = all(now_full[s] for s in ('morning', 'day', 'evening'))
                perfect_before = all(_prev_full.get(s) for s in ('morning', 'day', 'evening'))
                if perfect_now and not perfect_before:
                    # весь день закрыт впервые — жирное БИНГО (вместо блочного)
                    await self.send_message(bingo.pick('bingo'))
                    logger.info("🔥 БИНГО: идеальный день")
                else:
                    for _sec in newly:
                        await self.send_message(bingo.pick(_sec))
                        logger.info(f"🎉 Блок закрыт: {_sec}")
            except Exception as e:
                logger.warning(f"⚠️ Бинго-триггер: {e}")
            
            # ЭТАП 3: Обновляем исходное сообщение с прогресс-барами
            # ВАЖНО: используем clean_original, а НЕ original_text!
            clean_text = state.get('clean_original', state['original_text'])
            
            # КРИТИЧНО: парсим задачи ИЗ ТЕКУЩЕГО СООБЩЕНИЯ (не из state!)
            # Потому что вечернее сообщение содержит только вечерние задачи
            current_tasks = self.parse_tasks(clean_text)
            
            updated_text = self.update_original_message_with_progress(
                clean_text,
                current_tasks,  # Используем текущие, а не state['tasks']
                state['completed']
            )
            
            keyboard = self._redraw_keyboard(clean_text)
            await self.edit_message(message_id, updated_text, keyboard)
            
            # НЕ перезаписываем clean_original - он остаётся чистым!
            # Обновляем только original_text для отображения
            self.message_state[message_id]['original_text'] = updated_text
            
            # Сохраняем в файл + GitHub (переживёт рестарт)
            self.save_message_states()
            await self.sync_message_states_to_github()
            
            # Логируем (без отправки нового сообщения)
            logger.info(f"💾 Прогресс сохранён: {percentage}%")
    
    async def set_vacation(self, message_id):
        """Кнопка «Отпуск» (08.07): помечает сегодня как отпускной —
        дневной/вечерний блоки в этот день не выйдут (нотификатор читает
        флаг из stats.json), — и заменяет текст утреннего сообщения на
        карточку отпуска. Только на сегодня; назавтра всё вернётся само."""
        today_key = self.get_today_key()
        # база — свежий stats с GitHub (как в save_progress), чтобы не затереть
        stats = self.load_stats()
        try:
            content = await self._github_get_file("stats.json")
            if content:
                stats = json.loads(content)
        except Exception as e:
            logger.warning(f"⚠️ stats с GitHub недоступен ({e}) — локальная база")

        rec = dict(stats.get(today_key) or {})
        rec["vacation"] = True
        stats[today_key] = rec
        await self.save_stats(stats)
        try:
            await self.sync_stats_to_github(stats)
        except Exception as e:
            logger.warning(f"⚠️ sync отпуска не удался ({e})")

        # заменяем текст утреннего сообщения (id на руках — надёжно)
        await self.edit_message(
            message_id,
            "🏖 <b>Отпуск</b>\n\nСегодня без плана. Дневной и вечерний блоки "
            "пропущены. Хорошего отдыха!",
            reply_markup=None)
        # чистим состояние сообщения — кнопки больше не нужны
        self.message_state.pop(message_id, None)
        try:
            self.save_message_states()
        except Exception:
            pass

    async def cancel_update(self, message_id):
        """Отменяет обновление, возвращает исходное сообщение"""
        if message_id in self.message_state:
            original_text = self.message_state[message_id]['original_text']
            
            keyboard = self._redraw_keyboard(original_text)
            await self.edit_message(message_id, original_text, keyboard)
            
            # При отмене - очищаем состояние
            if message_id in self.message_state:
                del self.message_state[message_id]
                # Сохраняем в файл
                self.save_message_states()
    
    async def get_updates(self):
        """Получает обновления от Telegram (long polling)"""
        try:
            url = f"https://api.telegram.org/bot{self.telegram_token}/getUpdates"
            params = {
                'offset': self.last_update_id + 1,
                'timeout': 30
            }
            
            async with self.session.get(url, params=params, timeout=40) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get('result', [])
                return []
        except Exception as e:
            logger.error(f"❌ Ошибка получения обновлений: {e}")
            return []
    
    async def health_check(self, request):
        """HTTP endpoint health check (порт 8080, слушает и внешний скан)"""
        return web.Response(text="OK", status=200)
    
    async def webhook_handler(self, request):
        """Обработчик webhook от Telegram"""
        try:
            update = await request.json()
            
            # ЛОГИРУЕМ ВСЕ WEBHOOK ДЛЯ ОТЛАДКИ
            logger.info(f"🔔 Webhook получен: {list(update.keys())}")
            
            # Обрабатываем обычное сообщение или channel_post
            message = update.get('message') or update.get('channel_post')
            
            if message:
                chat_id = str(message.get('chat', {}).get('id', ''))
                chat_title = message.get('chat', {}).get('title', 'Private')
                chat_type = message.get('chat', {}).get('type', 'unknown')
                
                logger.info(f"📩 Сообщение из чата: ID={chat_id}, Title={chat_title}, Type={chat_type}")
                logger.info(f"🔑 Ожидаемый chat_id: {self.chat_id}")
                
                # Проверяем что это наш чат
                if chat_id == self.chat_id and 'text' in message:
                    message_text = message['text']
                    
                    logger.info(f"✅ Chat ID совпал! Проверяю текст...")
                    
                    # Проверяем что в сообщении есть задачи
                    if any(keyword in message_text for keyword in ['☀️', '📋', '⛔', '🌙', 'Дневн', 'Нельзя', 'Вечерн']):
                        logger.info("📨 Получено сообщение с задачами")
                        
                        # Парсим задачи
                        tasks = self.parse_tasks(message_text)
                        
                        # Создаём клавиатуру
                        keyboard = self.create_checklist_keyboard(tasks, {})
                        
                        # Формируем текст
                        response_text = self.format_checklist_message(tasks, {})
                        
                        # Отправляем ответ с кнопками
                        await self.send_message(response_text, keyboard)
                    else:
                        logger.warning(f"⚠️ Нет ключевых слов в сообщении: {message_text[:50]}...")
                else:
                    logger.warning(f"⚠️ Чат не совпадает или нет текста. chat_id={chat_id}, expected={self.chat_id}, has_text={'text' in message}")
            
            # Обрабатываем callback_query
            elif 'callback_query' in update:
                callback_query = update['callback_query']
                callback_data = callback_query.get('data', '')
                callback_query_id = callback_query.get('id', '')
                message = callback_query.get('message', {})
                message_id = message.get('message_id', 0)
                message_text = message.get('text', '')
                
                logger.info(f"📞 Получен callback: {callback_data}")
                await self.process_callback(callback_data, callback_query_id, message_id, message_text)
            
            return web.Response(text='OK')
        except Exception as e:
            logger.error(f"❌ Ошибка webhook: {e}", exc_info=True)
            return web.Response(status=500)
    
    async def run(self):
        """Основной цикл бота"""
        logger.info("🤖 Tracker Bot v2.0 запущен!")
        
        # Создаём persistent aiohttp session (одна на весь бот)
        self.session = aiohttp.ClientSession()
        
        # Загружаем message_states с GitHub (переживает рестарт сервиса)
        github_states = await self.load_message_states_from_github()
        if github_states:
            self.merge_github_states(github_states)
            logger.info(f"📊 Всего состояний: {len(self.message_state)}")
        
        # Загружаем stats с GitHub (для еженедельных отчётов)
        await self.load_stats_from_github()
        
        logger.info("📊 Слушаю обновления...")
        
        # HTTP сервер: health check и keepalive
        app = web.Application()
        app.router.add_get('/', self.health_check)
        app.router.add_get('/health', self.health_check)
        app.router.add_post('/webhook', self.webhook_handler)  # ← WEBHOOK!
        
        port = int(os.environ.get('PORT', 8080))
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', port)
        await site.start()
        logger.info(f"🌐 HTTP сервер запущен на порту {port}")
        
        # Устанавливаем webhook или используем polling
        railway_domain = os.environ.get('RAILWAY_PUBLIC_DOMAIN')
        use_polling = os.environ.get('USE_POLLING', 'false').lower() == 'true'
        
        if railway_domain and not use_polling:
            webhook_url = f"https://{railway_domain}/webhook"
            url = f"https://api.telegram.org/bot{self.telegram_token}/setWebhook"
            payload = {'url': webhook_url}
            async with self.session.post(url, json=payload) as response:
                result = await response.json()
                if result.get('ok'):
                    logger.info(f"✅ Webhook установлен: {webhook_url}")
                else:
                    logger.error(f"❌ Ошибка webhook: {result}")
        else:
            # VPS mode - используем long polling
            logger.info("📡 Режим Long Polling (VPS)")
            # Удаляем webhook если был
            delete_url = f"https://api.telegram.org/bot{self.telegram_token}/deleteWebhook"
            async with self.session.post(delete_url) as response:
                result = await response.json()
                if result.get('ok'):
                    logger.info("✅ Webhook удалён, переключаемся на polling")
        
        last_schedule_check = datetime.now()
        
        # Основной цикл
        try:
            while True:
                try:
                    # Проверяем расписание каждую минуту
                    now = datetime.now()
                    if (now - last_schedule_check).total_seconds() >= 60:
                        await self.check_schedule()
                        last_schedule_check = now
                    
                    # Если VPS mode - используем polling
                    if not railway_domain or use_polling:
                        updates = await self.get_updates()
                        for update in updates:
                            self.last_update_id = update.get('update_id', self.last_update_id)
                            
                            # Обрабатываем callback_query (нажатие кнопки)
                            callback_query = update.get('callback_query')
                            if callback_query:
                                callback_data = callback_query.get('data', '')
                                callback_query_id = callback_query.get('id', '')
                                message = callback_query.get('message', {})
                                message_id = message.get('message_id', 0)
                                message_text = message.get('text', '')
                                logger.info(f"📞 Получен callback: {callback_data}")
                                await self.process_callback(callback_data, callback_query_id, message_id, message_text)
                        
                        await asyncio.sleep(1)  # Короткая пауза между polling запросами
                    else:
                        await asyncio.sleep(60)  # Webhook mode - просто ждём
                    
                except Exception as e:
                    logger.error(f"❌ Ошибка в главном цикле: {e}")
                    await asyncio.sleep(5)
        finally:
            # Корректно закрываем session при выходе
            await self.session.close()

if __name__ == "__main__":
    bot = TaskTrackerBot()
    asyncio.run(bot.run())
