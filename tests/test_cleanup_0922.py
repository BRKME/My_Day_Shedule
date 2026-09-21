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


def test_signal_item_wording():
    for day in DAYS[:5]:
        hit = [t for t in load_schedule()[day]['день'] if 'SIGNAL' in t]
        assert hit and 'вчера пообещал себе' in hit[0], day


def test_saturday_split_survives_marker_removal():
    """«Записать одно главное дело» было маркером границы в субботе.
    Без него всё утро и день слиплись бы в одно сообщение."""
    morning, rest = split_day_tasks(load_schedule()['saturday']['день'])
    assert morning[-1].startswith('Послушать молитву')
    assert rest and rest[0].startswith('Полить цветы')


def test_weekday_split_unchanged():
    for day in DAYS[:5]:
        morning, rest = split_day_tasks(load_schedule()[day]['день'])
        assert morning[-1].startswith('English в дороге'), day
        assert rest[0].startswith('Сделать действие дня из SIGNAL'), day
