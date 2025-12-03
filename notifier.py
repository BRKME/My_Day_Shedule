#!/usr/bin/env python3
import asyncio
import aiohttp
from datetime import datetime, timedelta
from calendar import monthcalendar
import logging
import random
import sys
import os

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class PersonalScheduleNotifier:
    def __init__(self):
        self.telegram_token = os.getenv('TELEGRAM_TOKEN')
        if not self.telegram_token:
            raise ValueError("TELEGRAM_TOKEN не найден в переменных окружения!")

        self.chat_id = os.getenv('TELEGRAM_CHAT_ID')
        if not self.chat_id:
            raise ValueError("TELEGRAM_CHAT_ID не найден!")

        logger.info(f"Notifier запущен | Отправка в: {self.chat_id}")

        self.prayer_url = "https://brkme.github.io/My_Day/prayer.html"
        self.ss_url = "https://brkme.github.io/My_Day/ss.html"

        self.wisdoms = [
            "Лучший способ начать — перестать говорить и начать делать. — Уолт Дисней",
            "Не ждите. Время никогда не будет подходящим. — Наполеон Хилл",
            "Начало — самая важная часть работы. — Платон",
            "Путь в тысячу миль начинается с одного шага. — Лао-цзы",
            "Делай сегодня то, что другие не хотят, завтра будешь жить так, как другие не могут. — Джаред Лето",
            "Успех — это сумма маленьких усилий, повторяемых день за днём. — Роберт Кольер",
            "Я твердо верю в удачу, и чем больше я работаю — тем я удачливее. — Томас Джефферсон",
            "Неудача — это просто возможность начать снова, но уже более мудро. — Генри Форд",
            "Единственный способ сделать великую работу — любить то, что ты делаешь. — Стив Джобс",
            "Успех обычно приходит к тем, кто слишком занят, чтобы его искать. — Генри Дэвид Торо",
            "Дисциплина — это мост между целями и достижениями. — Джим Рон",
            "Мы есть то, что мы постоянно делаем. Совершенство — не действие, а привычка. — Аристотель",
            "Неважно, как медленно ты продвигаешься, главное, что ты не останавливаешься. — Конфуций",
            "Мотивация — это то, что заставляет вас начать. Привычка — это то, что заставляет продолжать. — Джим Рюн",
            "Каждое утро у нас есть два выбора: продолжать спать со своими мечтами или встать и осуществлять их.",
            "Потерянное утро остается потерянным на весь день. — Ричард Уэйтли",
            "Каждый день даёт шанс стать лучше.",
            "Самый верный способ добиться успеха — просто попробовать ещё раз. — Томас Эдисон",
            "Если вы можете мечтать об этом, вы можете это сделать. — Уолт Дисней",
            "Ваше время ограничено, не тратьте его, живя чужой жизнью. — Стив Джобс",
            "В центре каждой трудности — возможность. — Альберт Эйнштейн",
            "Сила не приходит от физических способностей. Она приходит от непреклонной воли. — Махатма Ганди",
            "Жизнь достаточно длинна, если ею хорошо распорядиться. — Сенека",
            "Действие — основной ключ к успеху. — Пабло Пикассо",
            "Цель без плана — это просто желание. — Антуан де Сент-Экзюпери",
            "Воображение важнее, чем знания. — Альберт Эйнштейн",
            "Мы сами должны стать теми переменами, которые хотим видеть в мире. — Махатма Ганди",
            "Счастье — это не нечто готовое. Оно зависит от ваших собственных действий. — Далай-лама",
            "Успех — это способность идти от одной неудачи к другой, не теряя энтузиазма. — Уинстон Черчилль"
        ]

        self.recurring_events = {
            'tarelka': {'name': 'Семейная традиция - Путещевствие на тарелке', 'file': 'tarelka.txt', 'rule': 'last_saturday'},
            'chronos': {'name': 'Семейная традиция - Вечер воспоминаний. Хранители времени', 'file': 'chronos.txt', 'rule': 'third_saturday'},
            'new': {'name': 'Семейная традиция - День нового', 'file': 'new.txt', 'rule': 'second_saturday'}
        }

        self.schedule = { /* твой большой словарь schedule — оставляю как есть, он норм */ }

    # ←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←
    # ИСПРАВЛЕННАЯ ФУНКЦИЯ — 100% рабочая
    def create_progress_button(self):
        """Создаёт inline кнопку для обновления прогресса"""
        return {
            "inline_keyboard": [
                [{"text": "Обновить прогресс", "callback_data": "update_progress"}]
            ]
        }
    # ←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←

    def get_random_wisdom(self):
        return random.choice(self.wisdoms)

    # ... все остальные методы без изменений (get_weather_forecast, format_morning_day_message и т.д.) ...

    async def send_telegram_message(self, message, ss_content=None, add_progress_button=False):
        try:
            url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
            payload = {
                'chat_id': self.chat_id,
                'text': message,
                'parse_mode': 'HTML',
                'disable_web_page_preview': False
            }

            if add_progress_button:
                payload['reply_markup'] = self.create_progress_button()

            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=10) as resp:
                    if resp.status != 200:
                        logger.error(f"Ошибка отправки: {resp.status}")
                        return False

            logger.info("Сообщение отправлено!")
            return True
        except Exception as e:
            logger.error(f"Ошибка отправки сообщения: {e}")
            return False

    # ... остальные методы без изменений ...

async def main(period):
    logger.info(f"Запуск notifier.py с периодом: {period}")
    notifier = PersonalScheduleNotifier()
    success = await notifier.send_message_for_period(period)
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ('morning', 'day', 'evening'):
        print("Использование: python notifier.py <morning|day|evening>")
        sys.exit(1)
    asyncio.run(main(sys.argv[1]))
