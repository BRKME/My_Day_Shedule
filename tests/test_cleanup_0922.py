# -*- coding: utf-8 -*-
"""Правки 22.09.2026: без строки времени, без «главного дела», новый
текст пункта SIGNAL."""
import asyncio
import os
import sys

sys.path.insert(0, '.')

os.environ.setdefault('TELEGRAM_TOKEN', 'test-token')
os.environ.setdefault('TELEGRAM_CHAT_ID', 'test-chat')

from core import load_schedule, split_day_tasks
from notifier import PersonalScheduleNotifier

DAYS = ('monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday')


def _all_messages():
    n = PersonalScheduleNotifier()
    out = []
    for i, day in enumerate(DAYS):
        ds = f'{21 + i:02d}.09.2026'
        for block in ('morning', 'day'):
            out.append(asyncio.run(n.format_morning_day_message(
                ds, day, n.schedule[day], block=block)))
        out.append(asyncio.run(n.format_evening_message(
            ds, day, n.schedule[day])))
    return out


def test_no_time_budget_line_anywhere():
    for msg in _all_messages():
        assert '⏱' not in msg and 'В плане' not in msg


def test_no_main_task_item_anywhere():
    for day, secs in load_schedule().items():
        for name, tasks in secs.items():
            assert not any('главное дело' in t for t in tasks), f'{day}/{name}'


def test_saturday_morning_keeps_flowers_and_lp():
    """С 30.10.2026 дневного блока нет: цветы и LP — в субботнем утре,
    граница утра по-прежнему «Послушать молитву»."""
    morning, rest = split_day_tasks(load_schedule()['saturday']['день'])
    assert morning[-1].startswith('Послушать молитву')
    assert not rest
    assert any(t.startswith('Полить цветы') for t in morning)
    assert any(t.startswith('LP %') for t in morning)


def test_weekday_split_unchanged():
    for day in DAYS[:5]:
        morning, rest = split_day_tasks(load_schedule()[day]['день'])
        assert 'English в дороге' in morning[-1], day
        assert not rest, day
