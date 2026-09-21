# -*- coding: utf-8 -*-
"""Программа «365 дней» выключена 22.09.2026.

Из утреннего сообщения уходят блок «Задание дня» и кнопки
«Сделал / Не сегодня». План дня (рутина) не трогается. Пул заданий
остаётся в репозитории: вернуть программу — одна строка в core.py.
"""
import asyncio
import os
import sys
from datetime import date

sys.path.insert(0, '.')

os.environ.setdefault('TELEGRAM_TOKEN', 'test-token')
os.environ.setdefault('TELEGRAM_CHAT_ID', 'test-chat')

import core
from core import DAILY_TASKS, task_of_the_day


def test_programme_is_switched_off():
    assert core.PROGRAM_ACTIVE is False


def test_no_task_on_a_regular_weekday():
    assert task_of_the_day(date(2026, 9, 23)) is None


def test_pool_is_kept_for_a_return():
    assert len(DAILY_TASKS) > 300


def test_morning_has_routine_but_no_task_block():
    from notifier import PersonalScheduleNotifier
    n = PersonalScheduleNotifier()
    msg = asyncio.run(n.format_morning_day_message(
        '23.09.2026', 'wednesday', n.schedule['wednesday'], block='morning'))
    assert '🎯' not in msg
    assert '• ' in msg                      # рутина на месте


def test_no_task_buttons_in_morning_keyboard():
    from tracker_bot import TaskTrackerBot
    header = '🌅 <b>Доброе утро! План на Среда 23.09.2026</b>'
    data = [b.get('callback_data')
            for row in TaskTrackerBot()._redraw_keyboard(header)['inline_keyboard']
            for b in row]
    assert 'task_done' not in data and 'task_skip' not in data
