# -*- coding: utf-8 -*-
"""Отметка задания дня.

Две кнопки под утренним сообщением: «Сделал» и «Не сегодня». Обе —
равноправные ответы, а не успех и провал: пропуск даёт ровно те же данные
и нужен, чтобы починить пул, а не чтобы оценивать человека.

Учёт намеренно отдельный от процента дня. Если задание попадёт в общий
чек-лист, в тяжёлый день сольётся именно оно — развитие стоит дороже, чем
«прими витамины», и первым идёт под нож.
"""
import json
import os
import sys
from datetime import date, timedelta

import pytest

sys.path.insert(0, '.')

os.environ.setdefault('TELEGRAM_TOKEN', 'test-token')
os.environ.setdefault('TELEGRAM_CHAT_ID', 'test-chat')

from core import task_of_the_day
from tracker_bot import TaskTrackerBot


@pytest.fixture
def bot(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    b = TaskTrackerBot()
    b.program_file = str(tmp_path / 'program.json')
    b.program = {}
    return b


# ── Хранение ─────────────────────────────────────────────────────────────

def test_done_is_recorded(bot):
    bot.record_task_result(date(2026, 8, 12), 'done')
    saved = json.load(open(bot.program_file, encoding='utf-8'))
    assert saved['2026-08-12']['status'] == 'done'


def test_skip_is_recorded_the_same_way(bot):
    bot.record_task_result(date(2026, 8, 12), 'skip')
    saved = json.load(open(bot.program_file, encoding='utf-8'))
    assert saved['2026-08-12']['status'] == 'skip'


def test_record_keeps_category_for_later_analysis(bot):
    """Смысл учёта — увидеть, какие категории ты не делаешь, и починить
    пул. Без категории данные бесполезны."""
    d = date(2026, 8, 12)
    bot.record_task_result(d, 'skip')
    saved = json.load(open(bot.program_file, encoding='utf-8'))
    assert saved['2026-08-12']['category'] == task_of_the_day(d)['category']


def test_answer_can_be_changed(bot):
    d = date(2026, 8, 12)
    bot.record_task_result(d, 'skip')
    bot.record_task_result(d, 'done')
    assert bot.program['2026-08-12']['status'] == 'done'


def test_record_does_not_touch_day_statistics(bot):
    """Главный инвариант: задание дня не влияет на процент выполнения."""
    bot.stats = {'2026-08-12': {'percentage': 40, 'points': 2}}
    bot.record_task_result(date(2026, 8, 12), 'done')
    assert bot.stats['2026-08-12'] == {'percentage': 40, 'points': 2}


def test_no_record_on_a_day_without_task(bot):
    """В выходной с браслетом задания нет — отмечать нечего."""
    d = date(2026, 8, 21)                      # белый браслет
    assert task_of_the_day(d) is None
    assert bot.record_task_result(d, 'done') is False
    assert bot.program == {}


# ── Кнопки ───────────────────────────────────────────────────────────────

def test_morning_keyboard_has_both_answers(bot):
    header = '🌅 <b>Доброе утро! План на Среда 12.08.2026</b>'
    buttons = [b for row in bot._redraw_keyboard(header)['inline_keyboard']
               for b in row]
    data = [b.get('callback_data') for b in buttons]
    assert 'task_done' in data
    assert 'task_skip' in data


def test_skip_button_is_not_framed_as_failure(bot):
    header = '🌅 <b>Доброе утро! План на Среда 12.08.2026</b>'
    buttons = [b for row in bot._redraw_keyboard(header)['inline_keyboard']
               for b in row]
    skip = next(b for b in buttons if b.get('callback_data') == 'task_skip')
    for word in ('провал', 'пропуск', 'не смог', '❌'):
        assert word not in skip['text'].lower()


def test_no_task_buttons_on_bracelet_day(bot):
    header = '🌅 <b>Доброе утро! План на Пятница 21.08.2026</b>'
    data = [b.get('callback_data')
            for row in bot._redraw_keyboard(header)['inline_keyboard']
            for b in row]
    assert 'task_done' not in data and 'task_skip' not in data


def test_no_task_buttons_in_day_and_evening(bot):
    for header in ('☀️ <b>Дневной блок · Среда 12.08.2026</b>',
                   '🌙 <b>Вечерний план на Среда 12.08.2026</b>'):
        data = [b.get('callback_data')
                for row in bot._redraw_keyboard(header)['inline_keyboard']
                for b in row]
        assert 'task_done' not in data, header


def test_chosen_answer_is_visible_on_the_button(bot):
    d = date(2026, 8, 12)
    bot.record_task_result(d, 'done')
    header = '🌅 <b>Доброе утро! План на Среда 12.08.2026</b>'
    buttons = [b for row in bot._redraw_keyboard(header)['inline_keyboard']
               for b in row]
    done = next(b for b in buttons if b.get('callback_data') == 'task_done')
    assert '✅' in done['text']


# ── Недельный итог ───────────────────────────────────────────────────────

def test_weekly_line_counts_done_out_of_answered(bot):
    start = date(2026, 8, 10)
    for i, status in enumerate(['done', 'done', 'skip', 'done']):
        bot.record_task_result(start + timedelta(days=i), status)
    line = bot.program_week_line(start + timedelta(days=6))
    assert '3' in line and '4' in line


def test_weekly_line_has_no_streak_language(bot):
    """Стрик на длинной дистанции убивает: один пропуск на 340-й день
    обнуляет год, и человек бросает."""
    bot.record_task_result(date(2026, 8, 10), 'done')
    line = bot.program_week_line(date(2026, 8, 16)).lower()
    for word in ('подряд', 'серия', 'стрик', 'обнул'):
        assert word not in line


def test_weekly_line_is_empty_without_answers(bot):
    assert bot.program_week_line(date(2026, 8, 16)) == ''


# ── Обработка нажатия ────────────────────────────────────────────────────

def test_callback_records_and_refreshes_keyboard(bot, monkeypatch):
    """Целиком путь нажатия: запись, синк и обновление клавиатуры —
    и ни одного обращения к editMessageText, который переписал бы текст
    и сломал отметки задач по индексам строк."""
    import asyncio
    calls = {}

    async def fake_sync(self):
        calls['sync'] = True

    async def fake_edit_kb(self, message_id, keyboard):
        calls['keyboard'] = keyboard

    async def fake_answer(self, qid, text=None):
        calls['answer'] = text

    async def boom(self, *a, **kw):
        raise AssertionError('текст сообщения трогать нельзя')

    monkeypatch.setattr(type(bot), 'sync_program_to_github', fake_sync)
    monkeypatch.setattr(type(bot), 'edit_message_keyboard', fake_edit_kb)
    monkeypatch.setattr(type(bot), 'answer_callback_query', fake_answer)
    monkeypatch.setattr(type(bot), 'edit_message', boom)

    header = '🌅 <b>Доброе утро! План на Среда 12.08.2026</b>\n\n• задача'
    asyncio.run(bot.process_callback('task_done', 'q1', 777, header))

    assert bot.program['2026-08-12']['status'] == 'done'
    assert calls['sync'] and calls['answer']
    data = [b.get('callback_data') for row in calls['keyboard']['inline_keyboard']
            for b in row]
    assert 'task_done' in data


def test_callback_on_bracelet_day_records_nothing(bot, monkeypatch):
    import asyncio
    called = {}

    async def fake_answer(self, qid, text=None):
        called['answer'] = True

    async def boom_sync(self):
        raise AssertionError('нечего синкать — задания нет')

    monkeypatch.setattr(type(bot), 'answer_callback_query', fake_answer)
    monkeypatch.setattr(type(bot), 'sync_program_to_github', boom_sync)

    header = '🌅 <b>Доброе утро! План на Пятница 21.08.2026</b>'
    asyncio.run(bot.process_callback('task_done', 'q1', 777, header))
    assert bot.program == {}
    assert called['answer']


def test_weekly_summary_shows_programme_line(bot, monkeypatch):
    import asyncio
    from datetime import datetime
    sent = {}

    async def fake_send(self, text, keyboard=None, **kw):
        sent['text'] = text
        return True

    monkeypatch.setattr(type(bot), 'send_message', fake_send, raising=False)
    monkeypatch.setattr(type(bot), 'send_telegram_message', fake_send,
                        raising=False)

    today = datetime.now().date()
    bot.record_task_result(today - timedelta(days=1), 'done')
    line = bot.program_week_line(today)
    assert line.startswith('🎯 Задания недели:')


# ── Кнопки в момент отправки, а не только при перерисовке ────────────────

def _notifier_at(d):
    from datetime import datetime
    from unittest.mock import patch
    from notifier import PersonalScheduleNotifier
    n = PersonalScheduleNotifier()

    class FixedDT(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(d.year, d.month, d.day, 7, 30, tzinfo=tz)

    with patch('notifier.datetime', FixedDT):
        return n.create_message_keyboard()


def test_sent_message_already_has_task_buttons():
    """Кнопки должны быть в сообщении сразу. Инцидент: они были только в
    перерисовке трекера, то есть утром отметить задание было нечем."""
    kb = _notifier_at(date(2026, 8, 12))
    data = [b.get('callback_data') for row in kb['inline_keyboard'] for b in row]
    assert 'task_done' in data and 'task_skip' in data


def test_sent_keyboard_has_no_task_buttons_on_bracelet_day():
    kb = _notifier_at(date(2026, 8, 21))
    data = [b.get('callback_data') for row in kb['inline_keyboard'] for b in row]
    assert 'task_done' not in data


def test_sunday_morning_keeps_task_buttons(bot):
    """Воскресный заголовок — «🌅 Воскресенье», без «Доброе утро».
    Трекер узнавал утро по этой фразе и в воскресенье терял и кнопки
    задания, и ссылку на страницу дня."""
    header = '🌅 <b>Воскресенье 23.08.2026</b>'
    data = [b.get('callback_data')
            for row in bot._redraw_keyboard(header)['inline_keyboard']
            for b in row]
    assert 'task_done' in data


def test_full_block_header_also_counts_as_morning(bot):
    header = '🌅 <b>План на Среда 12.08.2026</b>'
    data = [b.get('callback_data')
            for row in bot._redraw_keyboard(header)['inline_keyboard']
            for b in row]
    assert 'task_done' in data
