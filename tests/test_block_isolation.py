# -*- coding: utf-8 -*-
"""Утро и день не делят отметки.

Инцидент 22.09.2026: отметил в утреннем блоке две задачи и одно «нельзя»
— пришёл дневной блок, и в нём сразу стояли отмеченными две задачи и
одно «нельзя». Оба блока писали в одни ячейки статистики по номерам
строк: утренние №1 и №2 становились дневными №1 и №2.

Следствия, которые тоже ловит этот файл:
* «всего» бралось как максимум блоков, а не сумма — 4 вместо 7, и день
  выходил ложными 100%;
* перенесённое «нельзя» вешало штраф на задачу, которую не нарушали;
* снятая галочка возвращалась при следующем сохранении.

Теперь у блоков общий список: утро — позиции 0..3, день — 4..6, каждый
видит и пишет только свою часть. Размеры блоков трекер берёт из
расписания дня, а не из статистики — нотификаторскую границу трекер
затирал своей записью.
"""
import asyncio
import json
import os
import sys
from datetime import date

import pytest

sys.path.insert(0, '.')

os.environ.setdefault('TELEGRAM_TOKEN', 'test-token')
os.environ.setdefault('TELEGRAM_CHAT_ID', 'test-chat')

from core import block_layout, message_block

WED = date(2026, 9, 23)          # среда: утро 4 + 1 нельзя, день 3 + 3 нельзя


# ── Раскладка блоков ─────────────────────────────────────────────────────

def test_layout_for_a_weekday():
    lay = block_layout(WED)
    assert lay['morning']['day'] == (0, 4)
    assert lay['day']['day'] == (4, 3)
    assert lay['totals']['day'] == 7
    assert lay['morning']['cant_do'] == (0, 1)
    assert lay['day']['cant_do'] == (1, 3)
    assert lay['evening']['cant_do'] == (4, 2)
    assert lay['totals']['cant_do'] == 6


def test_block_is_read_from_the_header():
    assert message_block('🌅 <b>Доброе утро! План на Среда 23.09.2026</b>') == 'morning'
    assert message_block('☀️ <b>Дневной блок · Среда 23.09.2026</b>') == 'day'
    assert message_block('🌙 <b>Вечерний план на Среда 23.09.2026</b>') == 'evening'
    assert message_block('🌅 <b>План на Среда 23.09.2026</b>') == 'full'


# ── Сценарий инцидента ───────────────────────────────────────────────────

@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from notifier import PersonalScheduleNotifier
    from tracker_bot import TaskTrackerBot

    n = PersonalScheduleNotifier()
    b = TaskTrackerBot()
    b.stats_file = str(tmp_path / 'stats.json')
    b.message_state = {}

    async def noop(*a, **kw):
        return True

    async def no_github(*a, **kw):
        return None

    async def local_save(self, stats):
        with open(self.stats_file, 'w', encoding='utf-8') as f:
            json.dump(stats, f, ensure_ascii=False)
        return True

    for name in ('edit_message', 'send_message', 'send_penalty_message',
                 'answer_callback_query', 'sync_stats_to_github'):
        monkeypatch.setattr(type(b), name, noop, raising=False)
    monkeypatch.setattr(type(b), '_github_get_file', no_github)
    monkeypatch.setattr(type(b), 'save_stats', local_save)

    def msg(block):
        if block == 'evening':
            return asyncio.run(n.format_evening_message(
                '23.09.2026', 'wednesday', n.schedule['wednesday']))
        return asyncio.run(n.format_morning_day_message(
            '23.09.2026', 'wednesday', n.schedule['wednesday'], block=block))

    return n, b, msg


def _mark(b, mid, day=(), cant=(), evening=()):
    st = b.message_state[mid]
    st['completed']['day'] = list(day)
    st['completed']['cant_do'] = list(cant)
    st['completed']['evening'] = list(evening)
    asyncio.run(b.save_progress(mid))


def _today(b):
    return b.load_stats()[b.get_today_key()]


def test_day_block_does_not_inherit_morning_marks(world):
    """Ровно то, что случилось 22.09."""
    n, b, msg = world
    asyncio.run(b.show_checklist(1, msg('morning')))
    _mark(b, 1, day=[0, 1], cant=[0])

    asyncio.run(b.show_checklist(2, msg('day')))
    day_state = b.message_state[2]['completed']
    assert day_state['day'] == []
    assert day_state['cant_do'] == []


def test_total_is_the_sum_of_blocks(world):
    """«Всего» бралось как максимум блоков: 4 вместо 7 — ложные 100%."""
    n, b, msg = world
    asyncio.run(b.show_checklist(1, msg('morning')))
    _mark(b, 1, day=[0, 1, 2, 3])
    asyncio.run(b.show_checklist(2, msg('day')))
    _mark(b, 2, day=[])

    rec = _today(b)
    assert rec['day']['total'] == 7
    assert rec['day']['completed'] == [0, 1, 2, 3]
    assert rec['percentage'] < 100


def test_day_marks_land_after_the_morning_ones(world):
    n, b, msg = world
    asyncio.run(b.show_checklist(1, msg('morning')))
    _mark(b, 1, day=[0, 1])
    asyncio.run(b.show_checklist(2, msg('day')))
    _mark(b, 2, day=[0])

    assert _today(b)['day']['completed'] == [0, 1, 4]


def test_evening_prohibitions_do_not_collide_with_the_day(world):
    n, b, msg = world
    asyncio.run(b.show_checklist(2, msg('day')))
    _mark(b, 2, cant=[0])
    asyncio.run(b.show_checklist(3, msg('evening')))
    assert b.message_state[3]['completed']['cant_do'] == []
    _mark(b, 3, cant=[1])
    assert _today(b)['cant_do']['completed'] == [1, 5]


def test_unchecking_sticks(world):
    """Отметки объединялись с сохранёнными, и снятая возвращалась."""
    n, b, msg = world
    asyncio.run(b.show_checklist(1, msg('morning')))
    _mark(b, 1, day=[0, 1])
    _mark(b, 1, day=[0])
    assert _today(b)['day']['completed'] == [0]


def test_morning_state_survives_a_restart(world):
    """После рестарта трекер восстанавливает утренние отметки из
    статистики — и только утренние."""
    n, b, msg = world
    asyncio.run(b.show_checklist(1, msg('morning')))
    asyncio.run(b.show_checklist(2, msg('day')))
    _mark(b, 1, day=[1, 2])
    _mark(b, 2, day=[2])

    b.message_state = {}
    asyncio.run(b.show_checklist(11, msg('morning')))
    asyncio.run(b.show_checklist(12, msg('day')))
    assert b.message_state[11]['completed']['day'] == [1, 2]
    assert b.message_state[12]['completed']['day'] == [2]
