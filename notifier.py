#!/usr/bin/env python3
import asyncio
import aiohttp
from datetime import datetime
from calendar import monthcalendar
import logging
import random
import sys
import os
import json
import re
import base64
import requests

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class PersonalScheduleNotifier:
    # Константы класса
    DAY_NAMES_MAP = {
        'monday': 'понедельник',
        'tuesday': 'вторник', 
        'wednesday': 'среда',
        'thursday': 'четверг',
        'friday': 'пятница',
        'saturday': 'суббота',
        'sunday': 'воскресенье'
    }
    
    def __init__(self):
        self.telegram_token = os.getenv('TELEGRAM_TOKEN', '')
        if not self.telegram_token:
            raise ValueError("❌ TELEGRAM_TOKEN не найден в переменных окружения!")
        
        self.chat_id = os.getenv('TELEGRAM_CHAT_ID', '')
        if not self.chat_id:
            raise ValueError("❌ TELEGRAM_CHAT_ID не найден в переменных окружения!")
        
        self.prayer_url = "https://brkme.github.io/My_Day_Shedule/prayer.html"
        self.ss_url = "https://brkme.github.io/My_Day_Shedule/ss.html"
        self.career_url = "https://brkme.github.io/My_Day_Shedule/career.html"
        self.taleb_url = "https://brkme.github.io/My_Day_Shedule/taleb.html"
        
        self.wisdoms = [
    "Фокусируешься на решениях — находишь их даже в безвыходных, казалось бы, ситуациях. Концентрируешься на проблемах — получаешь их в полном объёме и даже больше."
]
        
        self.recurring_events = {
            'tarelka': {'name': 'Семейная традиция - Путешествие на тарелке', 'file': 'tarelka.txt', 'rule': 'last_saturday'},
            # АРХИВ: 'chronos' - Вечер воспоминаний (убрана из активных традиций)
            # 'chronos': {
            #     'name': 'Семейная традиция - Вечер воспоминаний',
            #     'url': 'https://brkme.github.io/My_Day_Shedule/chronos.html',
            #     'short_text': 'Хранители времени — смотрим фото и рассказываем историю семьи',
            #     'rule': 'third_saturday'
            # },
            'new': {
                'name': 'Семейная традиция - День нового',
                'url': 'https://brkme.github.io/My_Day_Shedule/new.html',
                'short_text': 'Выходим из зоны комфорта всей семьей!',
                'rule': 'second_saturday'
            }
        }
        
        # Расписание занятий детей
        self.kids_schedule = {
            'понедельник': [
                {'child': '👧 Марта', 'activity': '🇬🇧 Английский', 'time': '16:00-17:00'},
                {'child': '👦 Аркаша', 'activity': '📐 Математика', 'time': '19:00-20:00'}
            ],
            'вторник': [
                {'child': '👧 Марта', 'activity': '💃 Танцы', 'time': '17:30-19:00'},
                {'child': '👦 Аркаша', 'activity': '⚽ Футбол', 'time': '17:00-18:00'}
            ],
            'среда': [
                {'child': '👧 Марта', 'activity': '🤺 Фехтование', 'time': '15:00-16:30'},
                {'child': '👦 Аркаша', 'activity': '🤺 Фехтование', 'time': '16:00-18:00'},
                {'child': '👧 Марта', 'activity': '🇬🇧 Английский', 'time': '17:00-18:00'}
            ],
            'четверг': [
                {'child': '👧 Марта', 'activity': '💃 Танцы', 'time': '17:30-19:00'},
                {'child': '👦 Аркаша', 'activity': '⚽ Футбол', 'time': '17:00-18:00'}
            ],
            'пятница': [
                {'child': '👧 Марта', 'activity': '🤺 Фехтование', 'time': '15:00-16:30'},
                {'child': '👦 Аркаша', 'activity': '🤺 Фехтование', 'time': '16:00-18:00'},
                {'child': '👦 Аркаша', 'activity': '📐 Математика', 'time': '19:00-20:00'}
            ],
            'суббота': [
                {'child': '👧 Марта', 'activity': '🤺 Фехтование', 'time': '15:00-17:00'}
            ],
            'воскресенье': [
                {'child': '👧 Марта', 'activity': '🤺 Фехтование', 'time': '12:00-14:00'},
                {'child': '👦 Аркаша', 'activity': '🤺 Фехтование', 'time': '14:00-16:00'}
            ]
        }
        
        self.schedule = {
            'monday': {
        'день': [
            'Прими 💊 Витамины <i>(Топливо для мозга)</i>',
            'Взвесится ⚖️ <i>(Цель 85 кг)</i>',
            'Зарядка 🤸 <i>(Старт для твоей энергии)</i>',
            'Дать 💝 3 поглаживания семье: (комплимент, внимание, объятия, искренний интерес)',
            'Занятия 🇬🇧 English на YouTube <i>(20 min)</i>',
            'Читать 📖 в дороге <i>(25 min это Спорт для мозга)</i>',
            'Ответить на вопрос Какую ценность ты добавишь миру сегодня ?',
            'Включи 🧠 Мозг Выбери 1 самое важное дело на сегодня. Приоритет $',
            'Прочитай 📚 задания от психолога',
            '🏦 Напоминание инвестировать в детей 200 USD в неделю',
            'Проверь 🎯 Цели <i>(10 min Цели — твой навигатор)</i>',
            'Подтянуться 💪 min 15 раз  <i>(5 min Силы для побед)</i>',
            'Подтянуться 💪 min 15 раз  <i>(5 min Силы для побед)</i>',
            'Упражнение 🦾 на пресс min 17 раз <i>(5 min Крепкий корпус)</i>',
            'Упражнение 🦾 на пресс min 17 раз <i>(5 min Крепкий корпус)</i>'
        ],
        'нельзя_день': [
            'Не 🤫 Перебивай <i>(Молчание строит доверие)</i>',
            'Не 🙅 Извиняйся <i>(автоматическое принятие вины + эрозия авторитета)</i>',
            'Не 🤬 Ругайся <i>(Мат это мусор и 👅 гнева и бессилия)</i>',
            'Не ⚡ Делай Д <i>(Слил энергию = слил фокус)</i>',
            'Не ⚡ Есть после 22-00 <i>( Цель 85 кг. )</i>',
            'Не 🍷 Пей Алкоголь <i>(Даже вино. Он крадет твою энергию, деньги и внешность. Сушка до 1 мая)</i>'
        ],
        'вечер': [
            'Читать 📖 в дороге <i>(30 min это Спорт для мозга)</i>',
            'Семейный 🍽️ ужин <i>(30 min)</i>',
            'Проверить 📝 оценки детей <i>(Контроль учёбы)</i>',
            'Отдых 😌 <i>(60 min Ментальная перезагрузка)</i>',
            'CRPT 📊 LP <i>(30 min)</i>',
            'Pet 💻 Project <i>(120 min)</i>',
            'Читать 📚 с Мартой без телефона <i>(20 min)</i>',
            'GROK 🤖 сессия с психологом <i>(15 min)</i>',
            'Эмоциональный 📔 дневник <i>(10 min управляешь эмоциями и счастьем)</i>',
            'Включи 💨 увлажнитель <i>(Здоровье лёгких)</i>',
            '🌙 Мой SPA-ритуал',
            'Прими 💊 Магний перед сном <i>(Выключи стресс)</i>',
            'Вечерняя 🙏 благодарность <i>(Семейная традиция)</i>'
        ]
    },
    'tuesday': {
        'день': [
            'Прими 💊 Витамины <i>(Топливо для мозга)</i>',
            'Взвесится ⚖️ <i>(Цель 85 кг)</i>',
            'Зарядка 🤸 <i>(Старт для твоей энергии)</i>',
            'Дать 💝 3 поглаживания семье: (комплимент, внимание, объятия, искренний интерес)',
            'Занятия 🇬🇧 English на YouTube <i>(20 min)</i>',
            'Читать 📖 в дороге <i>(25 min это Спорт для мозга)</i>',
            'Ответить на вопрос Какую ценность ты добавишь миру сегодня ?',
            'Включи 🧠 Мозг Выбери 1 самое важное дело на сегодня. Приоритет $',
            'Прочитай 📚 задания от психолога',
            'Проверь 🎯 Цели <i>(10 min Цели — твой навигатор)</i>',
            'Подтянуться 💪 min 15 раз  <i>(5 min Силы для побед)</i>',
            'Подтянуться 💪 min 15 раз  <i>(5 min Силы для побед)</i>',
            'Упражнение 🦾 на пресс min 17 раз <i>(5 min Крепкий корпус)</i>',
            'Упражнение 🦾 на пресс min 17 раз <i>(5 min Крепкий корпус)</i>'
        ],
        'нельзя_день': [
            'Не 🤫 Перебивай <i>(Молчание строит доверие)</i>',
            'Не 🙅 Извиняйся <i>(автоматическое принятие вины + эрозия авторитета)</i>',
            'Не 🤬 Ругайся <i>(Мат это мусор и 👅 гнева и бессилия)</i>',
            'Не ⚡ Делай Д <i>(Слил энергию = слил фокус)</i>',
            'Не ⚡ Есть после 22-00 <i>( Цель 85 кг. )</i>',
            'Не 🍷 Пей Алкоголь <i>(Даже вино. Он крадет твою энергию, деньги и внешность. Сушка до 1 мая)</i>'
        ],
        'вечер': [
            'Читать 📖 в дороге <i>(30 min это Спорт для мозга)</i>',
            'Семейный 🍽️ ужин <i>(30 min)</i>',
            'Проверить 📝 оценки детей <i>(5 min Контроль учёбы)</i>',
            'Отдых 😌 <i>(60 min Ментальная перезагрузка)</i>',
            'CRPT 📊 LP <i>(30 min)</i>',
            'Pet 💻 Project <i>(120 min)</i>',
            'Читать 📚 с Мартой <i>(20 min)</i>',
            'GROK 🤖 сессия с психологом <i>(15 min)</i>',
            'Эмоциональный 📔 дневник <i>(10 min управляешь эмоциями и счастьем)</i>',
            'Включи 💨 увлажнитель <i>(1 min Здоровье лёгких)</i>',
            '🌙 Мой SPA-ритуал',
            'Прими 💊 Магний перед сном <i>(1 min Выключи стресс)</i>',
            'Вечерняя 🙏 благодарность <i>(5 min Семейная традиция)</i>'
        ]
    },
    'wednesday': {
        'день': [
            'Прими 💊 Витамины <i>(Топливо для мозга)</i>',
            'Взвесится ⚖️ <i>(Цель 85 кг)</i>',
            'Зарядка 🤸 <i>(Старт для твоей энергии)</i>',
            'Дать 💝 3 поглаживания семье: (комплимент, внимание, объятия, искренний интерес)',
            'Занятия 🇬🇧 English на YouTube <i>(20 min)</i>',
            'Читать 📖 в дороге <i>(25 min это Спорт для мозга)</i>',
            'Ответить на вопрос Какую ценность ты добавишь миру сегодня ?',
            'Включи 🧠 Мозг Выбери 1 самое важное дело на сегодня. Приоритет $',
            '🏦 Напоминание инвестировать в детей 200 USD в неделю',
            'Прочитай 📚 задания от психолога',
            'Проверь 🎯 Цели <i>(10 min Цели — твой навигатор)</i>',
            'Подтянуться 💪 min 15 раз  <i>(5 min Силы для побед)</i>',
            'Подтянуться 💪 min 15 раз  <i>(5 min Силы для побед)</i>',
            'Упражнение 🦾 на пресс min 17 раз <i>(5 min Крепкий корпус)</i>',
            'Упражнение 🦾 на пресс min 17 раз <i>(5 min Крепкий корпус)</i>'
        ],
        'нельзя_день': [
            'Не 🤫 Перебивай <i>(Молчание строит доверие)</i>',
            'Не 🙅 Извиняйся <i>(автоматическое принятие вины + эрозия авторитета)</i>',
            'Не 🤬 Ругайся <i>(Мат это мусор и 👅 гнева и бессилия)</i>',
            'Не ⚡ Делай Д <i>(Слил энергию = слил фокус)</i>',
            'Не ⚡ Есть после 22-00 <i>( Цель 85 кг. )</i>',
            'Не 🍷 Пей Алкоголь <i>(Даже вино. Он крадет твою энергию, деньги и внешность. Сушка до 1 мая)</i>'
        ],
        'вечер': [
            'Читать 📖 в дороге <i>(30 min это Спорт для мозга)</i>',
            'Семейный 🍽️ ужин <i>(30 min)</i>',
            'Проверить 📝 оценки детей <i>(5 min Контроль учёбы)</i>',
            'Отдых 😌 <i>(60 min Ментальная перезагрузка)</i>',
            'CRPT 📊 LP <i>(30 min)</i>',
            'Pet 💻 Project <i>(120 min)</i>',
            'Читать 📚 с Мартой <i>(20 min)</i>',
            'GROK 🤖 сессия с психологом <i>(15 min)</i>',
            'Эмоциональный 📔 дневник <i>(10 min управляешь эмоциями и счастьем)</i>',
            'Включи 💨 увлажнитель <i>(1 min Здоровье лёгких)</i>',
            '🌙 Мой SPA-ритуал',
            'Прими 💊 Магний перед сном <i>(1 min Выключи стресс)</i>',
            'Вечерняя 🙏 благодарность <i>(5 min Семейная традиция)</i>'
        ]
    },
    'thursday': {
        'день': [
            'Прими 💊 Витамины <i>(Топливо для мозга)</i>',
            'Взвесится ⚖️ <i>(Цель 85 кг)</i>',
            'Зарядка 🤸 <i>(Старт для твоей энергии)</i>',
            'Дать 💝 3 поглаживания семье: (комплимент, внимание, объятия, искренний интерес)',
            'Занятия 🇬🇧 English на YouTube <i>(20 min)</i>',
            'Читать 📖 в дороге <i>(25 min это Спорт для мозга)</i>',
            'Ответить на вопрос Какую ценность ты добавишь миру сегодня ?',
            'Включи 🧠 Мозг Выбери 1 самое важное дело на сегодня. Приоритет $',
            'Прочитай 📚 задания от психолога',
            'Проверь 🎯 Цели <i>(10 min Цели — твой навигатор)</i>',
            'Подтянуться 💪 min 15 раз  <i>(5 min Силы для побед)</i>',
            'Подтянуться 💪 min 15 раз  <i>(5 min Силы для побед)</i>',
            'Упражнение 🦾 на пресс min 17 раз <i>(5 min Крепкий корпус)</i>',
            'Упражнение 🦾 на пресс min 17 раз <i>(5 min Крепкий корпус)</i>'
        ],
        'нельзя_день': [
            'Не 🤫 Перебивай <i>(Молчание строит доверие)</i>',
            'Не 🙅 Извиняйся <i>(автоматическое принятие вины + эрозия авторитета)</i>',
            'Не 🤬 Ругайся <i>(Мат это мусор и 👅 гнева и бессилия)</i>',
            'Не ⚡ Делай Д <i>(Слил энергию = слил фокус)</i>',
            'Не ⚡ Есть после 22-00 <i>( Цель 85 кг. )</i>',
            'Не 🍷 Пей Алкоголь <i>(Даже вино. Он крадет твою энергию, деньги и внешность. Сушка до 1 мая)</i>'
        ],
        'вечер': [
            'Читать 📖 в дороге <i>(30 min это Спорт для мозга)</i>',
            'Семейный 🍽️ ужин <i>(30 min)</i>',
            'Проверить 📝 оценки детей <i>(5 min Контроль учёбы)</i>',
            'Отдых 😌 <i>(60 min Ментальная перезагрузка)</i>',
            'CRPT 📊 LP <i>(30 min)</i>',
            'Pet 💻 Project <i>(120 min)</i>',
            'Читать 📚 с Мартой <i>(20 min)</i>',
            'GROK 🤖 сессия с психологом <i>(15 min)</i>',
            'Эмоциональный 📔 дневник <i>(10 min управляешь эмоциями и счастьем)</i>',
            'Включи 💨 увлажнитель <i>(1 min Здоровье лёгких)</i>',
            '🌙 Мой SPA-ритуал',
            'Прими 💊 Магний перед сном <i>(1 min Выключи стресс)</i>',
            'Вечерняя 🙏 благодарность <i>(5 min Семейная традиция)</i>'
        ]
    },
    'friday': {
        'день': [
            'Прими 💊 Витамины <i>(Топливо для мозга)</i>',
            'Взвесится ⚖️ <i>(Цель 85 кг)</i>',
            'Зарядка 🤸 <i>(Старт для твоей энергии)</i>',
            'Дать 💝 3 поглаживания семье: (комплимент, внимание, объятия, искренний интерес)',
            'Занятия 🇬🇧 English на YouTube <i>(20 min)</i>',
            'Читать 📖 в дороге <i>(25 min это Спорт для мозга)</i>',
            'Включи 🧠 Мозг Выбери 1 самое важное дело на сегодня. Приоритет $',
            'Ответить на вопрос Какую ценность ты добавишь миру сегодня ?',
            'Прочитай 📚 задания от психолога',
            'Проверь 🎯 Цели <i>(10 min Цели — твой навигатор)</i>',
            'Подтянуться 💪 min 15 раз  <i>(5 min Силы для побед)</i>',
            'Подтянуться 💪 min 15 раз  <i>(5 min Силы для побед)</i>',
            'Упражнение 🦾 на пресс min 17 раз <i>(5 min Крепкий корпус)</i>',
            'Упражнение 🦾 на пресс min 17 раз <i>(5 min Крепкий корпус)</i>'
        ],
        'нельзя_день': [
            'Не 🤫 Перебивай <i>(Молчание строит доверие)</i>',
            'Не 🙅 Извиняйся <i>(автоматическое принятие вины + эрозия авторитета)</i>',
            'Не 🤬 Ругайся <i>(Мат это мусор и 👅 гнева и бессилия)</i>',
            'Не ⚡ Делай Д <i>(Слил энергию = слил фокус)</i>',
            'Не ⚡ Есть после 22-00 <i>( Цель 85 кг. )</i>',
            'Не 🍷 Пей Алкоголь <i>(Даже вино. Он крадет твою энергию, деньги и внешность. Сушка до 1 мая)</i>'
        ],
        'вечер': [
            'Читать 📖 в дороге <i>(30 min это Спорт для мозга)</i>',
            'Семейный 🍽️ ужин <i>(30 min)</i>',
            'Проверить 📝 оценки детей <i>(5 min Контроль учёбы)</i>',
            'Отдых 😌 <i>(60 min Ментальная перезагрузка)</i>',
            'CRPT 📊 LP <i>(30 min)</i>',
            'Pet 💻 Project <i>(120 min)</i>',
            'Читать 📚 с Мартой <i>(20 min)</i>',
            'GROK 🤖 сессия с психологом <i>(15 min)</i>',
            'Эмоциональный 📔 дневник <i>(10 min управляешь эмоциями и счастьем)</i>',
            'Включи 💨 увлажнитель <i>(1 min Здоровье лёгких)</i>',
            '🌙 Мой SPA-ритуал',
            'Прими 💊 Магний перед сном <i>(1 min Выключи стресс)</i>',
            'Вечерняя 🙏 благодарность <i>(5 min Семейная традиция)</i>',
            'Зачёт 🧹 по чистоте комнаты в пятницу. Семейная традиция <i>(20 min Порядок в доме)</i>'
        ]
    },
    'saturday': {
        'день': [
            'Прими 💊 витамины <i>(«Топливо» для мозга)</i>',
            'Взвесится ⚖️ <i>(Цель 85 кг)</i>',
            'Зарядка 🤸 <i>(«Старт» для твоей энергии)</i>',
            'Дать 💝 3 поглаживания семье: (комплимент, внимание, объятия, искренний интерес)',
            'Ответить на вопрос Какую ценность ты добавишь миру сегодня ?',
            'Включи 🧠 Мозг Выбери 1 самое важное дело на сегодня. Приоритет $',
            'Полить 🌸 Цветы <i>(10 min Забота о доме)</i>',
            'Проверь 🎯 Цели <i>(10 min Цели — твой навигатор)</i>',
            '🏦 Напоминание инвестировать в детей 200 USD в неделю',
            'LP 📈 % <i>(30 min Анализ портфеля детей)</i>'
        ],
        'нельзя_день': [
            'Не 🙅 Извиняйся <i>(автоматическое принятие вины + эрозия авторитета)</i>',
            'Не 🤬 Ругайся <i>(Мат это мусор и 👅 гнева и бессилия)</i>',
            'Не ⚡ Есть после 22-00 <i>( Цель 85 кг. )</i>',
            'Не ⚡ Делай Д <i>(Слил энергию = слил фокус)</i>',
        ],
        'вечер': [
            'Pet 💻 Project <i>(120 +120 +120 min)</i>',
            'Читать 📚 с Мартой <i>(20 min)</i>',
            'GROK 🤖 сессия с психологом <i>(15 min)</i>',
            'Эмоциональный 📔 дневник <i>(10 min управляешь эмоциями и счастьем)</i>',
            'Включи 💨 увлажнитель <i>(1 min Здоровье лёгких)</i>',
            '🌙 Мой SPA-ритуал',
            'Прими 💊 Магний перед сном <i>(1 min Выключи стресс)</i>',
            'Вечерняя 🙏 благодарность <i>(5 min Семейная традиция)</i>',
            'Семейный 🎬 просмотр фильма <i>(120 min Время вместе)</i>'
        ]
    },
    'sunday': {
        'день': [
            '👨‍👩‍👧‍👦 FamilyDay — день без задач'
        ],
        'нельзя_день': [],
        'вечер': []
            }
        }

    def get_random_wisdom(self):
        return random.choice(self.wisdoms)

    def get_today_schedule(self):
        now = datetime.now()
        date_str = now.strftime("%d.%m.%Y")
        day_of_week = now.strftime("%A").lower()
        schedule = self.schedule.get(day_of_week, {})
        return date_str, day_of_week, schedule

    async def get_weather_forecast(self):
        """Получение погоды через Open-Meteo API (копия из Family_Bot)"""
        try:
            # Санкт-Петербург: 59.9311, 30.3609
            url = "https://api.open-meteo.com/v1/forecast?latitude=59.9311&longitude=30.3609&current_weather=true&temperature_unit=celsius&timezone=Europe/Moscow"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        current = data.get('current_weather', {})
                        
                        temp = current.get('temperature', 'N/A')
                        windspeed = current.get('windspeed', 'N/A')
                        
                        weather_codes = {
                            0: 'Ясно', 1: 'Малооблачно', 2: 'Переменная облачность', 3: 'Облачно',
                            45: 'Туман', 48: 'Изморозь',
                            51: 'Морось', 53: 'Морось', 55: 'Сильная морось',
                            61: 'Слабый дождь', 63: 'Дождь', 65: 'Сильный дождь',
                            71: 'Слабый снег', 73: 'Снег', 75: 'Сильный снег',
                            95: 'Гроза'
                        }
                        
                        weather_code = current.get('weathercode', 0)
                        condition = weather_codes.get(weather_code, 'Неизвестно')
                        
                        logger.info(f"✅ Погода получена: {temp}°C, {condition}")
                        
                        return (
                            f"🌤️ <b>Погода в Санкт-Петербурге:</b>\n"
                            f"🌡️ {temp}°C • {condition}\n"
                            f"💨 Ветер: {windspeed} км/ч\n"
                        )
                    else:
                        logger.warning(f"⚠️ Open-Meteo вернул статус {response.status}")
                        return ""
            
        except Exception as e:
            logger.error(f"❌ Ошибка погоды: {e}")
            return ""

    async def get_weekend_forecast(self):
        """Не используется, возвращает пустую строку"""
        return ""

    async def get_rates(self):
        """Получение курсов USD/RUB и BTC/USD"""
        try:
            rates = {}
            
            async with aiohttp.ClientSession() as session:
                # USD/RUB от ЦБ РФ
                try:
                    cbr_url = "https://www.cbr-xml-daily.ru/daily_json.js"
                    async with session.get(cbr_url, timeout=10) as response:
                        if response.status == 200:
                            data = await response.json()
                            usd = data.get('Valute', {}).get('USD', {})
                            rates['usd'] = usd.get('Value', 0)
                            rates['usd_prev'] = usd.get('Previous', 0)
                except Exception as e:
                    logger.error(f"❌ Ошибка USD: {e}")
                    rates['usd'] = None
                
                # BTC/USD от CoinGecko
                try:
                    btc_url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd&include_24hr_change=true"
                    async with session.get(btc_url, timeout=10) as response:
                        if response.status == 200:
                            data = await response.json()
                            btc = data.get('bitcoin', {})
                            rates['btc'] = btc.get('usd', 0)
                            rates['btc_change'] = btc.get('usd_24h_change', 0)
                except Exception as e:
                    logger.error(f"❌ Ошибка BTC: {e}")
                    rates['btc'] = None
            
            # Форматируем вывод
            result = ""
            
            if rates.get('usd'):
                usd_val = rates['usd']
                usd_prev = rates.get('usd_prev', usd_val)
                usd_diff = usd_val - usd_prev
                usd_arrow = "↑" if usd_diff > 0 else "↓" if usd_diff < 0 else "→"
                result += f"💵 USD: {usd_val:.2f}₽ {usd_arrow}\n"
            
            if rates.get('btc'):
                btc_val = rates['btc']
                btc_change = rates.get('btc_change', 0)
                btc_arrow = "↑" if btc_change > 0 else "↓" if btc_change < 0 else "→"
                # Форматируем BTC с запятыми
                btc_formatted = f"{btc_val:,.0f}".replace(",", " ")
                result += f"₿ BTC: ${btc_formatted} {btc_arrow}{abs(btc_change):.1f}%\n"
            
            if result:
                logger.info(f"✅ Курсы получены: USD={rates.get('usd')}, BTC={rates.get('btc')}")
                return result
            else:
                return ""
                
        except Exception as e:
            logger.error(f"❌ Ошибка курсов: {e}")
            return ""

    def get_last_day_of_month(self, year, month, target_weekday):
        calendar = monthcalendar(year, month)
        for week in reversed(calendar):
            day = week[target_weekday]
            if day != 0:
                return day
        return None

    def get_event_date_by_rule(self, rule, year, month):
        if rule == 'last_saturday':
            day = self.get_last_day_of_month(year, month, 5)
            return (year, month, day) if day else None
        elif rule == 'third_saturday':
            calendar = monthcalendar(year, month)
            saturdays = [week[5] for week in calendar if week[5] != 0]
            if len(saturdays) >= 3:
                return (year, month, saturdays[2])
        elif rule == 'second_saturday':
            calendar = monthcalendar(year, month)
            saturdays = [week[5] for week in calendar if week[5] != 0]
            if len(saturdays) >= 2:
                return (year, month, saturdays[1])
        return None

    async def check_yesterday_penalty(self):
        """Проверяет штраф за вчера из stats.json (загружает с GitHub)"""
        try:
            from datetime import timedelta
            
            # Получаем вчерашнюю дату
            yesterday = datetime.now() - timedelta(days=1)
            yesterday_key = yesterday.strftime("%Y-%m-%d")
            
            # Загружаем stats.json с GitHub (там актуальные данные от tracker_bot)
            stats = self._load_stats_from_github()
            
            if not stats:
                logger.info("📊 Не удалось загрузить stats.json с GitHub")
                return None
            
            # Проверяем насколько свежие данные
            dates = [k for k in stats.keys() if k.startswith('202')]
            if dates:
                last_date = max(dates)
                days_old = (datetime.now() - datetime.strptime(last_date, "%Y-%m-%d")).days
                if days_old > 3:
                    logger.warning(f"⚠️ Данные устарели! Последняя запись: {last_date} ({days_old} дней назад)")
                    logger.warning("⚠️ Проверь GITHUB_TOKEN на Railway - синхронизация не работает!")
            
            # Проверяем есть ли данные за вчера
            if yesterday_key not in stats:
                logger.info(f"📊 Нет данных за {yesterday_key}, штрафа нет")
                return None
            
            yesterday_data = stats[yesterday_key]
            
            # Проверяем penalty_pushups
            penalty_pushups = yesterday_data.get('penalty_pushups', 0)
            
            if penalty_pushups > 0:
                cant_do_completed = yesterday_data.get('cant_do', {}).get('completed', [])
                cant_do_fails = len(cant_do_completed)
                logger.info(f"⚠️ Найден штраф за {yesterday_key}: {penalty_pushups} отжиманий ({cant_do_fails} срывов)")
                
                # Получаем названия задач из _tasks
                tasks_dict = yesterday_data.get('_tasks', {})
                cant_do_tasks = tasks_dict.get('cant_do', [])
                
                # Формируем детальное сообщение
                penalty_text = f"⚠️ <b>Отжимания {penalty_pushups}×</b>\n"
                penalty_text += f"Вчера срывов: {cant_do_fails}\n"
                
                # Показываем какие именно срывы были (по индексам)
                if cant_do_completed and cant_do_tasks:
                    for idx in cant_do_completed[:3]:  # Максимум 3
                        if isinstance(idx, int) and idx < len(cant_do_tasks):
                            task = cant_do_tasks[idx]
                            clean_task = task.replace('НЕ ', '').replace('Не ', '').strip()
                            penalty_text += f"· {clean_task}\n"
                
                return penalty_text.strip()
            else:
                logger.info(f"✅ Штрафа за {yesterday_key} нет")
                return None
                
        except Exception as e:
            logger.error(f"❌ Ошибка проверки штрафа: {e}")
            return None
    
    def _load_stats_from_github(self):
        """Загружает stats.json с GitHub"""
        try:
            github_token = os.getenv('GITHUB_TOKEN')
            if not github_token:
                logger.warning("⚠️ GITHUB_TOKEN не найден в переменных окружения")
                return None
            
            repo = "BRKME/My_Day_Shedule"
            path = "stats.json"
            url = f"https://api.github.com/repos/{repo}/contents/{path}"
            headers = {
                "Authorization": f"token {github_token}",
                "Accept": "application/vnd.github.v3+json"
            }
            
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                content_b64 = response.json().get('content', '')
                content = base64.b64decode(content_b64).decode('utf-8')
                stats = json.loads(content)
                # Показываем последнюю дату в stats
                dates = [k for k in stats.keys() if k.startswith('202')]
                if dates:
                    last_date = max(dates)
                    logger.info(f"✅ Загружен stats.json с GitHub (последняя запись: {last_date})")
                else:
                    logger.info(f"✅ Загружен stats.json с GitHub ({len(stats)} записей)")
                return stats
            elif response.status_code == 401:
                logger.error("❌ GitHub: токен невалиден (401)")
                return None
            elif response.status_code == 404:
                logger.warning("⚠️ stats.json не найден на GitHub")
                return None
            else:
                logger.warning(f"⚠️ GitHub GET stats.json: {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки stats.json с GitHub: {e}")
            return None

    def get_kids_schedule(self, day_of_week):
        """Возвращает расписание детей на сегодня с полным логированием и защитой от ошибок"""
        logger.info(f"📅 Запрос расписания детей для дня: {day_of_week}")
        
        # Проверка входных данных
        if not day_of_week:
            logger.warning("⚠️ day_of_week is None or empty")
            return None
        
        # Преобразование дня недели в русский
        day_ru = self.DAY_NAMES_MAP.get(day_of_week)
        if not day_ru:
            logger.warning(f"⚠️ День '{day_of_week}' не найден в маппинге")
            return None
        
        # Проверка наличия расписания для этого дня
        if day_ru not in self.kids_schedule:
            logger.warning(f"⚠️ Расписание для дня '{day_ru}' отсутствует")
            return None
        
        activities = self.kids_schedule[day_ru]
        
        # Проверка на пустое расписание
        if not activities:
            logger.info(f"ℹ️ Нет занятий на {day_ru}")
            return None
        
        logger.info(f"✅ Найдено {len(activities)} занятий для {day_ru}")
        
        # Формирование текста расписания
        schedule_text = "<b>👨‍👩‍👧‍👦 Занятия детей сегодня:</b>\n"
        successful_items = 0
        
        for idx, item in enumerate(activities):
            try:
                child = item['child']
                activity = item['activity']
                time = item['time']
                
                schedule_text += f"• {child} — {activity} <i>({time})</i>\n"
                successful_items += 1
                logger.debug(f"  ✓ Занятие {idx+1}: {child} - {activity} ({time})")
                
            except KeyError as e:
                logger.error(f"❌ Ошибка в данных расписания (элемент {idx+1}): отсутствует ключ {e}")
                logger.error(f"   Данные элемента: {item}")
                continue
            except Exception as e:
                logger.error(f"❌ Неожиданная ошибка при обработке элемента {idx+1}: {e}")
                continue
        
        # Проверка что хотя бы одно занятие добавлено успешно
        if successful_items == 0:
            logger.warning(f"⚠️ Не удалось обработать ни одного занятия для {day_ru}")
            return None
        
        logger.info(f"✅ Расписание сформировано: {successful_items}/{len(activities)} занятий")
        return schedule_text

    async def format_morning_day_message(self, date_str, day_of_week, schedule):
        day_names = {'monday': 'Понедельник', 'tuesday': 'Вторник', 'wednesday': 'Среда', 'thursday': 'Четверг', 'friday': 'Пятница', 'saturday': 'Суббота', 'sunday': 'Воскресенье'}
        day_ru = day_names.get(day_of_week, day_of_week)
        wisdom = self.get_random_wisdom()
        
        # Sunday = FamilyDay, minimal message
        if day_of_week == 'sunday':
            content = f"🌅 <b>{day_ru} {date_str}</b>\n\n"
            
            weather = await self.get_weather_forecast()
            content += weather
            
            content += "\n👨‍👩‍👧‍👦 <b>FamilyDay</b>\nДень без задач. Наслаждайся семьёй.\n"
            
            # Kids schedule
            kids_day = day_ru.lower()
            if kids_day in self.kids_schedule and self.kids_schedule[kids_day]:
                content += "\n<b>👶 Расписание детей:</b>\n"
                for k in self.kids_schedule[kids_day]:
                    content += f"• {k['child']} {k['activity']} {k['time']}\n"
            
            content += f"\n<b>Мудрость дня:</b>\n{wisdom}"
            return content
        
        content = f"🌅 <b>План на {day_ru} {date_str}</b>\n\n"
        
        weather = await self.get_weather_forecast()
        content += weather
        
        # Курсы валют
        rates = await self.get_rates()
        if rates:
            content += rates
        
        if day_of_week in ['monday', 'wednesday', 'friday']:
            weekend_forecast = await self.get_weekend_forecast()
            if weekend_forecast:
                content += weekend_forecast
        
        content += "\n"
        
        # Штраф за вчера (если есть) - с деталями
        penalty_info = await self.check_yesterday_penalty()
        if penalty_info:
            content += f"{penalty_info}\n\n"
        
        if schedule.get('день'):
            content += "<b>📋 Дневные задачи:</b>\n"
            
            if day_of_week == 'saturday':
                today = datetime.now()
                last_saturday_day = self.get_last_day_of_month(today.year, today.month, 5)
                if today.day == last_saturday_day:
                    content += "• Сделать фото-презентацию по итогам месяца\n"
            
            for task in schedule['день']:
                content += f"• {task}\n"
        if schedule.get('нельзя_день'):
            content += "\n<b>⛔ Нельзя делать:</b>\n"
            for task in schedule['нельзя_день']:
                content += f"• {task}\n"
        
        # Добавляем расписание детей
        #kids_schedule_text = self.get_kids_schedule(day_of_week)
        #if kids_schedule_text:
        #    content += f"\n{kids_schedule_text}"
        
        content += f"\n<b>Мудрость дня:</b>\n{wisdom}"
        
        content += f'\n\n🙏 <a href="{self.prayer_url}">Утренняя молитва</a>'
        content += f'\n🏢 <a href="{self.career_url}">Принципы карьеры</a>'
        content += f'\n📚 <a href="{self.taleb_url}">Талеб: Антихрупкость</a>'
        
        return content
    
    def create_message_keyboard(self):
        return {
            'inline_keyboard': [
                [{'text': '🔄 Обновить прогресс', 'callback_data': 'update_progress'}],
                [{'text': '🙏 Утренняя молитва', 'url': self.prayer_url}],
                [{'text': '🏢 Принципы карьеры', 'url': self.career_url}],
                [{'text': '📚 Талеб: Антихрупкость', 'url': self.taleb_url}]
            ]
        }
    
    def save_today_tasks(self, message):
        """
        Сохраняет задачи из сообщения в stats.json для tracker_bot.py
        Это решает проблему timeout кнопок при перезапуске Render
        """
        try:
            stats_file = "stats.json"
            today = datetime.now().strftime("%Y-%m-%d")
            
            # Парсим задачи из сообщения
            tasks = self.parse_tasks_from_message(message)
            
            # Загружаем существующую статистику
            stats = {}
            if os.path.exists(stats_file):
                with open(stats_file, 'r', encoding='utf-8') as f:
                    stats = json.load(f)
                    # Фильтруем служебные ключи
                    stats = {k: v for k, v in stats.items() if not k.startswith('_')}
            
            # Создаём или обновляем запись за сегодня
            if today not in stats:
                stats[today] = {}
            
            # Сохраняем задачи (не перезаписываем completed если уже есть)
            stats[today]['_tasks'] = tasks
            stats[today]['_message'] = message[:1000]  # Сохраняем первые 1000 символов
            stats[today]['_updated'] = datetime.now().isoformat()
            
            # Сохраняем локально
            with open(stats_file, 'w', encoding='utf-8') as f:
                json.dump(stats, f, ensure_ascii=False, indent=2)
            
            logger.info(f"✅ Задачи сохранены в stats.json: day={len(tasks.get('day', []))}, evening={len(tasks.get('evening', []))}")
            
            # Синхронизируем с GitHub для tracker_bot на Railway
            self.sync_stats_to_github(stats)
            
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения задач: {e}")
    
    def sync_stats_to_github(self, stats):
        """Синхронизирует stats.json с GitHub для tracker_bot.py"""
        try:
            github_token = os.getenv('GITHUB_TOKEN')
            if not github_token:
                logger.warning("⚠️ GITHUB_TOKEN не найден, пропускаем синхронизацию")
                return
            
            repo = "BRKME/My_Day_Shedule"
            path = "stats.json"
            url = f"https://api.github.com/repos/{repo}/contents/{path}"
            headers = {
                "Authorization": f"token {github_token}",
                "Accept": "application/vnd.github.v3+json"
            }
            
            # Получаем текущий SHA
            response = requests.get(url, headers=headers, timeout=10)
            sha = None
            if response.status_code == 200:
                sha = response.json().get('sha')
            
            # Кодируем контент
            content = json.dumps(stats, ensure_ascii=False, indent=2)
            encoded = base64.b64encode(content.encode()).decode()
            
            # Обновляем файл
            data = {
                "message": f"stats: tasks {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                "content": encoded,
                "branch": "main"
            }
            if sha:
                data["sha"] = sha
            
            response = requests.put(url, headers=headers, json=data, timeout=10)
            if response.status_code in [200, 201]:
                logger.info("✅ stats.json синхронизирован с GitHub")
            else:
                logger.warning(f"⚠️ GitHub sync: {response.status_code}")
                
        except Exception as e:
            logger.warning(f"⚠️ Ошибка синхронизации с GitHub: {e}")
            
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения задач: {e}")
    
    def parse_tasks_from_message(self, message):
        """Парсит задачи из сообщения (аналог parse_tasks в tracker_bot.py)"""
        tasks = {
            'day': [],
            'cant_do': [],
            'evening': []
        }
        
        lines = message.split('\n')
        current_section = None
        
        for line in lines:
            line = line.strip()
            clean_line = line.replace('<b>', '').replace('</b>', '').replace('<i>', '').replace('</i>', '')
            
            # Определяем секцию
            if ('📋' in clean_line or '☀️' in clean_line) and 'Дневн' in clean_line:
                current_section = 'day'
                continue
            elif any(marker in clean_line for marker in ['⛔', '⛔️', 'Нельзя делать']):
                current_section = 'cant_do'
                continue
            elif ('🌙' in clean_line and 'Вечерн' in clean_line) or 'Вечерние задачи' in clean_line:
                current_section = 'evening'
                continue
            elif any(marker in clean_line for marker in ['Мудрость дня', '🙏 Утренняя', '🎉 СЕГОДНЯ', 'Занятия детей']):
                current_section = None
                continue
            
            # Собираем задачи
            if current_section and line.startswith('•'):
                task_text = line[1:].strip()
                if task_text:
                    tasks[current_section].append(task_text)
        
        return tasks

    async def format_evening_message(self, date_str, day_of_week, schedule):
        day_names = {'monday': 'Понедельник', 'tuesday': 'Вторник', 'wednesday': 'Среда', 'thursday': 'Четверг', 'friday': 'Пятница', 'saturday': 'Суббота', 'sunday': 'Воскресенье'}
        day_ru = day_names.get(day_of_week, day_of_week)
        wisdom = self.get_random_wisdom()
        
        content = f"🌙 <b>Вечерний план на {day_ru} {date_str}</b>\n\n"
        
        if schedule.get('вечер'):
            content += "<b>📋 Вечерние задачи:</b>\n"
            for task in schedule['вечер']:
                content += f"• {task}\n"
        content += f"\n<b>Мудрость дня:</b>\n{wisdom}"
        
        return content

    async def send_pullups_message(self):
        """Отправляет сообщение для зачёта по подтягиваниям с кнопками"""
        message = "💪 <b>ЗАЧЁТ ПО ПОДТЯГИВАНИЯМ</b>\n\n"
        message += "Сколько раз подтянулся?\n"
        message += "Цель: 15 раз 🎯"
        
        # Кнопки с числами 8-20
        keyboard = {
            'inline_keyboard': [
                [
                    {'text': '8', 'callback_data': 'pullups_8'},
                    {'text': '10', 'callback_data': 'pullups_10'},
                    {'text': '12', 'callback_data': 'pullups_12'},
                    {'text': '13', 'callback_data': 'pullups_13'}
                ],
                [
                    {'text': '14', 'callback_data': 'pullups_14'},
                    {'text': '15 🎯', 'callback_data': 'pullups_15'},
                    {'text': '17', 'callback_data': 'pullups_17'},
                    {'text': '20', 'callback_data': 'pullups_20'}
                ],
                [
                    {'text': '22', 'callback_data': 'pullups_22'},
                    {'text': '25', 'callback_data': 'pullups_25'}
                ]
            ]
        }
        
        url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
        payload = {
            'chat_id': self.chat_id,
            'text': message,
            'parse_mode': 'HTML',
            'reply_markup': json.dumps(keyboard)
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=30) as response:
                    if response.status == 200:
                        logger.info("✅ Сообщение подтягиваний отправлено")
                        return True
                    else:
                        error = await response.text()
                        logger.error(f"❌ Ошибка Telegram: {error}")
                        return False
        except Exception as e:
            logger.error(f"❌ Ошибка: {e}")
            return False

    async def fetch_event_file(self, filename):
        try:
            url = f"https://raw.githubusercontent.com/BRKME/Day/main/{filename}"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=10) as response:
                    if response.status == 200:
                        content = await response.text()
                        logger.info(f"✅ Файл {filename} загружен")
                        return content
                    else:
                        logger.error(f"❌ Ошибка загрузки {filename}")
                        return None
        except Exception as e:
            logger.error(f"❌ Ошибка: {e}")
            return None

    def check_recurring_events(self):
        from datetime import date as dt
        today = datetime.now()
        year, month, day = today.year, today.month, today.day
        reminders = []
        for event_key, event in self.recurring_events.items():
            event_date = self.get_event_date_by_rule(event['rule'], year, month)
            if not event_date:
                continue
            event_year, event_month, event_day = event_date
            event_dt = dt(event_year, event_month, event_day)
            today_dt = dt(year, month, day)
            days_until = (event_dt - today_dt).days
            if days_until == 7:
                reminders.append({'key': event_key, 'event': event, 'type': 'week_before'})
            elif days_until == 3:
                reminders.append({'key': event_key, 'event': event, 'type': 'three_days_before'})
            elif days_until == 0:
                reminders.append({'key': event_key, 'event': event, 'type': 'event_day'})
        return reminders

    async def send_morning_photo(self):
        """Отправляет мотивационное фото перед утренним сообщением"""
        try:
            photo_url = "https://raw.githubusercontent.com/BRKME/My_Day_Shedule/main/morning_motivation.jpg"
            url = f"https://api.telegram.org/bot{self.telegram_token}/sendPhoto"
            
            payload = {
                'chat_id': self.chat_id,
                'photo': photo_url
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=15) as response:
                    if response.status == 200:
                        logger.info("✅ Утреннее фото отправлено")
                        return True
                    else:
                        logger.warning(f"⚠️ Не удалось отправить фото: {response.status}")
                        return False
        except Exception as e:
            logger.warning(f"⚠️ Ошибка отправки фото: {e}")
            return False

    async def send_telegram_message(self, message, ss_content=None, add_progress_button=False):
        try:
            # НОВОЕ: Сохраняем задачи для tracker_bot.py
            self.save_today_tasks(message)
            
            url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
            payload = {
                'chat_id': self.chat_id, 
                'text': message, 
                'parse_mode': 'HTML',
                'disable_web_page_preview': False
            }
            
            if add_progress_button:
                payload['reply_markup'] = self.create_message_keyboard()
            
            logger.info("📤 Отправка сообщения в Telegram...")
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=10) as response:
                    if response.status != 200:
                        logger.error(f"❌ Ошибка API")
                        return False
            if ss_content:
                family_msg = f'<b>📋 Семейный совет:</b>\n\n🔗 <a href="{self.ss_url}">Открыть структуру Семейного Совета</a>'
                payload_council = {'chat_id': self.chat_id, 'text': family_msg, 'parse_mode': 'HTML', 'disable_web_page_preview': False}
                async with aiohttp.ClientSession() as session:
                    async with session.post(url, json=payload_council, timeout=10) as response:
                        if response.status == 200:
                            logger.info("✅ Сообщения отправлены!")
                            return True
                        else:
                            logger.error(f"❌ Ошибка отправки")
                            return False
            else:
                logger.info("✅ Сообщение отправлено!")
                return True
        except Exception as e:
            logger.error(f"❌ Ошибка: {e}")
            return False

    async def send_message_for_period(self, period):
        date_str, day_of_week, schedule = self.get_today_schedule()
        ss_content = None
        add_button = False
        
        if period == 'morning':
            # Сначала отправляем мотивационное фото
            await self.send_morning_photo()
            
            message = await self.format_morning_day_message(date_str, day_of_week, schedule)
            add_button = True
            
            if day_of_week == 'sunday':
                ss_content = True
            reminders = self.check_recurring_events()
            if reminders:
                for reminder in reminders:
                    event = reminder['event']
                    
                    # Если есть URL - используем короткий текст со ссылкой
                    if 'url' in event:
                        if reminder['type'] == 'week_before':
                            message += f"\n\n🔔 <b>НАПОМИНАНИЕ (За 7 дней):</b>\n<b>{event['name']}</b>\n"
                            message += f"{event.get('short_text', '')}\n"
                            message += f"🔗 <a href='{event['url']}'>Подробнее</a>\n"
                        elif reminder['type'] == 'three_days_before':
                            message += f"\n\n🔔 <b>НАПОМИНАНИЕ (За 3 дня):</b>\n<b>{event['name']}</b>\n"
                            message += f"{event.get('short_text', '')}\n"
                            message += f"🔗 <a href='{event['url']}'>Подробнее</a>\n"
                        elif reminder['type'] == 'event_day':
                            message += f"\n\n🎉 <b>СЕГОДНЯ:</b>\n<b>{event['name']}</b>\n"
                            message += f"{event.get('short_text', '')}\n"
                            message += f"🔗 <a href='{event['url']}'>Подробнее</a>\n"
                    else:
                        # Старая логика для событий с файлом
                        event_content = await self.fetch_event_file(event['file'])
                        if reminder['type'] == 'week_before':
                            message += f"\n\n🔔 <b>НАПОМИНАНИЕ (За 7 дней):</b>\n<b>{event['name']}</b>\n"
                            if event_content:
                                message += f"{event_content}"
                        elif reminder['type'] == 'three_days_before':
                            message += f"\n\n🔔 <b>НАПОМИНАНИЕ (За 3 дня):</b>\n<b>{event['name']}</b>\n"
                            if event_content:
                                message += f"{event_content}"
                        elif reminder['type'] == 'event_day':
                            message += f"\n\n🎉 <b>СЕГОДНЯ:</b>\n<b>{event['name']}</b>\n"
                            if event_content:
                                message += f"{event_content}"
        elif period == 'day':
            message = await self.format_morning_day_message(date_str, day_of_week, schedule)
            add_button = True
        elif period == 'evening':
            if day_of_week == 'sunday':
                logger.info("🌙 Воскресенье — FamilyDay, вечернее сообщение не отправляется")
                return True
            message = await self.format_evening_message(date_str, day_of_week, schedule)
            add_button = True
        elif period == 'pullups':
            # Отдельная логика для подтягиваний
            return await self.send_pullups_message()
        else:
            logger.error(f"❌ Неизвестный период: {period}")
            return False
        return await self.send_telegram_message(message, ss_content, add_progress_button=add_button)

async def main(period):
    logger.info(f"🚀 Запуск для периода: {period}")
    notifier = PersonalScheduleNotifier()
    success = await notifier.send_message_for_period(period)
    if success:
        logger.info("🎉 Успешно завершено!")
    else:
        logger.error("💥 Ошибка при отправке")
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ('morning', 'day', 'evening', 'pullups'):
        print("❌ Использование: python notifier.py <morning|day|evening|pullups>")
        sys.exit(1)
    asyncio.run(main(sys.argv[1]))
