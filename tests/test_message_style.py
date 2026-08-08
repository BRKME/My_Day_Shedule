# -*- coding: utf-8 -*-
"""Стиль утреннего сообщения (вариант А).

Эмодзи стоят только у заголовков секций. Раньше они были на трёх уровнях
сразу — у секций, у метаданных и у каждой задачи, — и когда помечено всё,
не помечено ничего: значки переставали работать указателями и читались
как фактура.

Секционные маркеры при этом неприкосновенны: трекер ловит секции по
«📋 … Дневн…» и «⛔», и переименование сломало бы разбор задач.
"""
import asyncio
import os
import sys

sys.path.insert(0, '.')

os.environ.setdefault('TELEGRAM_TOKEN', 'test-token')
os.environ.setdefault('TELEGRAM_CHAT_ID', 'test-chat')

from core import load_schedule
from notifier import PersonalScheduleNotifier
from tracker_bot import TaskTrackerBot

EMOJI = ('\U0001F300', '\U0001FAFF')


def _has_emoji(text):
    return any(EMOJI[0] <= ch <= EMOJI[1] or '\u2600' <= ch <= '\u27BF'
               for ch in text)


def test_schedule_tasks_carry_no_emoji():
    for day, sections in load_schedule().items():
        for name, tasks in sections.items():
            for t in tasks:
                assert not _has_emoji(t), f'{day}/{name}: {t}'


def test_section_headers_keep_their_markers():
    """Без «📋 Дневн» и «⛔» трекер не найдёт секции."""
    n = PersonalScheduleNotifier()
    msg = asyncio.run(n.format_morning_day_message(
        '12.08.2026', 'wednesday', n.schedule['wednesday'], block='morning'))
    assert '📋' in msg and 'Дневн' in msg
    assert '⛔' in msg


def test_parser_still_finds_all_tasks():
    n, b = PersonalScheduleNotifier(), TaskTrackerBot()
    msg = asyncio.run(n.format_morning_day_message(
        '12.08.2026', 'wednesday', n.schedule['wednesday'], block='morning'))
    parsed = b.parse_tasks(msg)
    assert len(parsed['day']) == 7
    assert len(parsed['cant_do']) >= 1


def test_task_lines_start_with_a_letter_not_a_symbol():
    n = PersonalScheduleNotifier()
    msg = asyncio.run(n.format_morning_day_message(
        '12.08.2026', 'wednesday', n.schedule['wednesday'], block='morning'))
    for line in msg.splitlines():
        if line.startswith('• '):
            assert line[2].isalpha(), line
