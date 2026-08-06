# -*- coding: utf-8 -*-
"""Задание дня — программа «365 дней улучшений».

Одно задание в день из пула в data/daily_tasks.json. Порядок случайный,
но колодой: пока не пройдёт вся, повторов нет.

Три правила отбора, каждое написано по итогам разбора пула:
  • семья, отцовство и друзья — на выходные, остальное на будни;
  • в день белого браслета задания нет (там ты ничего не должен);
  • два эмоционально дорогих задания не идут подряд, а требующие
    заметного усилия не выпадают в понедельник и пятницу.
"""
import sys
from datetime import date, timedelta

sys.path.insert(0, '.')

from core import (DAILY_TASKS, WEEKEND_CATEGORIES, is_bracelet_day,
                  load_daily_tasks, task_of_the_day)


def _run(start, days):
    return [(d, task_of_the_day(d))
            for d in (start + timedelta(days=i) for i in range(days))]


# ── Данные ───────────────────────────────────────────────────────────────

def test_pool_is_loaded():
    assert len(DAILY_TASKS) > 300
    assert load_daily_tasks() == list(DAILY_TASKS)


def test_every_task_has_category_text_and_reason():
    for t in DAILY_TASKS:
        assert t['category'] and t['task'] and t['why']
        assert t.get('load', 'light') in ('light', 'high', 'effort')


def test_no_duplicate_tasks_in_pool():
    texts = [t['task'] for t in DAILY_TASKS]
    assert len(texts) == len(set(texts))


# ── Отбор ────────────────────────────────────────────────────────────────

def test_weekend_gets_only_relationship_categories():
    for d, t in _run(date(2026, 8, 1), 120):
        if d.weekday() >= 5 and t:
            assert t['category'] in WEEKEND_CATEGORIES, (d, t['category'])


def test_weekday_never_gets_weekend_categories():
    for d, t in _run(date(2026, 8, 1), 120):
        if d.weekday() < 5 and t:
            assert t['category'] not in WEEKEND_CATEGORIES, (d, t['category'])


def test_no_task_on_bracelet_day():
    for d, t in _run(date(2026, 8, 1), 200):
        if is_bracelet_day(d):
            assert t is None, d


def test_task_is_stable_for_a_date():
    """Сообщение и клавиатура собираются разными вызовами — расхождение
    показало бы одно задание в тексте и другое на кнопке."""
    d = date(2026, 8, 12)
    assert task_of_the_day(d) == task_of_the_day(d) == task_of_the_day(d)


# ── Колода ───────────────────────────────────────────────────────────────

def test_no_repeats_within_a_deck():
    """Ключевое отличие от честного random: он выдал бы одно задание
    дважды за неделю и не выдал бы другое полгода. Гарантия — внутри
    колоды; на стыке колод повтор законен, как и при тасовке карт."""
    seen = [t['task'] for _, t in _run(date(2026, 8, 3), 120)
            if t and t['category'] not in WEEKEND_CATEGORIES]
    assert len(seen) == len(set(seen)), 'повтор внутри колоды'


def test_weekend_deck_also_has_no_early_repeats():
    """Выходных пул меньше буднего, поэтому и окно проверки короче:
    70 заданий — это 35 недель выходных."""
    seen = [t['task'] for _, t in _run(date(2026, 8, 1), 60)
            if t and t['category'] in WEEKEND_CATEGORIES]
    assert len(seen) == len(set(seen))


def test_deck_contains_the_whole_pool_exactly_once():
    """Гарантия колоды на уровне самой колоды, а не окна наблюдения."""
    from core import _WEEKDAY_POOL, _deck
    for cycle in range(5):
        deck = _deck(_WEEKDAY_POOL, cycle, True)
        assert len(deck) == len(_WEEKDAY_POOL)
        assert len({t['task'] for t in deck}) == len(_WEEKDAY_POOL)


def test_order_is_not_a_fixed_rotation():
    a = [t['task'] for _, t in _run(date(2026, 8, 3), 40) if t]
    b = [t['task'] for _, t in _run(date(2027, 3, 1), 40) if t]
    assert a != b


# ── Нагрузка ─────────────────────────────────────────────────────────────

def test_two_expensive_tasks_never_land_back_to_back():
    """«Признай промах перед женой» два дня подряд — путь к тому,
    чтобы бросить программу."""
    seq = [t for _, t in _run(date(2026, 8, 1), 400) if t]
    for a, b in zip(seq, seq[1:]):
        assert not (a.get('load') == 'high' and b.get('load') == 'high')


def test_effort_tasks_avoid_monday_and_friday():
    """В начале и в конце недели сил меньше всего — тяжёлое туда не ставим."""
    for d, t in _run(date(2026, 8, 1), 400):
        if t and t.get('load') == 'effort':
            assert d.weekday() not in (0, 4), (d, t['task'])


def test_every_task_appears_over_a_long_run():
    seen = {t['task'] for _, t in _run(date(2026, 1, 1), 1200) if t}
    assert len(seen) >= len(DAILY_TASKS) - 5


# ── Вывод в утреннем сообщении ───────────────────────────────────────────

def _notifier():
    import os
    os.environ.setdefault('TELEGRAM_TOKEN', 'test-token')
    os.environ.setdefault('TELEGRAM_CHAT_ID', 'test-chat')
    from notifier import PersonalScheduleNotifier
    return PersonalScheduleNotifier()


def _morning(date_str, day_key, block='morning'):
    import asyncio
    n = _notifier()
    return asyncio.run(n.format_morning_day_message(
        date_str, day_key, n.schedule[day_key], block=block))


def test_morning_message_carries_the_task():
    msg = _morning('12.08.2026', 'wednesday')
    t = task_of_the_day(date(2026, 8, 12))
    assert t['task'] in msg
    assert t['why'] in msg
    assert t['category'] in msg


def test_task_line_is_not_a_checklist_item():
    """Строки задач начинаются с «• » и попадают в прогресс по индексам.
    Задание дня туда попасть не должно — трекинга у программы нет."""
    import os
    os.environ.setdefault('TELEGRAM_TOKEN', 'test-token')
    from tracker_bot import TaskTrackerBot

    msg = _morning('12.08.2026', 'wednesday')
    b = TaskTrackerBot()
    parsed = b.parse_tasks(msg)
    task = task_of_the_day(date(2026, 8, 12))['task']
    everything = parsed['day'] + parsed['evening'] + parsed['cant_do']
    assert all(task not in line for line in everything)
    assert not any(line.startswith('🎯') for line in everything)


def test_no_task_line_in_day_and_evening_messages():
    t = task_of_the_day(date(2026, 8, 12))
    assert t['task'] not in _morning('12.08.2026', 'wednesday', block='day')


def test_message_stays_within_telegram_limit():
    for day, ds in (('monday', '10.08.2026'), ('wednesday', '12.08.2026'),
                    ('saturday', '15.08.2026'), ('sunday', '16.08.2026')):
        msg = _morning(ds, day)
        assert len(msg) < 4096
        assert msg.count('<i>') == msg.count('</i>')
        assert msg.count('<b>') == msg.count('</b>')
