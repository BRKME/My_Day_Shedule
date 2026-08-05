# -*- coding: utf-8 -*-
"""Белый браслет — супер-удачный день.

Раз в десять дней выпадает день, когда все задачи отменяются: надевается
белый браслет, утро приносит одно мотивирующее сообщение и предсказание
из стоиков. Дневной и вечерний блоки не отправляются.

Ключевое требование: удачный день не должен портить статистику. День без
задач, посчитанный как 0%, обвалил бы недельный уровень — «повезло во
всём» превратилось бы в наказание.
"""
import sys
from datetime import date, timedelta

sys.path.insert(0, '.')

from core import (STOIC_QUOTES, bracelet_quote, is_bracelet_day,
                  load_stoic_quotes)


# ── Выпадение дня ────────────────────────────────────────────────────────

def test_exactly_one_bracelet_day_per_ten_days():
    start = date(2026, 8, 1)
    start += timedelta(days=(-start.toordinal()) % 10)      # граница блока
    for block in range(40):
        base = start + timedelta(days=block * 10)
        hits = [i for i in range(10) if is_bracelet_day(base + timedelta(days=i))]
        assert len(hits) == 1, f'блок {block}: выпало {len(hits)} дней'


def test_bracelet_never_falls_on_weekend():
    """В выходные задач почти нет — отменять там нечего, удача пропадёт зря."""
    d = date(2026, 8, 1)
    for i in range(400):
        day = d + timedelta(days=i)
        if is_bracelet_day(day):
            assert day.weekday() < 5, f'{day} — выходной'


def test_bracelet_day_is_stable():
    """Дата должна давать один и тот же ответ при любом числе вызовов:
    иначе утреннее сообщение и проверка дневного блока разойдутся."""
    d = date(2026, 8, 12)
    assert is_bracelet_day(d) == is_bracelet_day(d) == is_bracelet_day(d)


def test_bracelet_days_are_not_always_same_weekday():
    """Иначе это не удача, а расписание: «каждый второй вторник»."""
    d = date(2026, 1, 1)
    weekdays = {(d + timedelta(days=i)).weekday()
                for i in range(365) if is_bracelet_day(d + timedelta(days=i))}
    assert len(weekdays) > 2, weekdays


def test_roughly_three_bracelet_days_a_month():
    d = date(2026, 8, 1)
    count = sum(1 for i in range(365) if is_bracelet_day(d + timedelta(days=i)))
    assert 33 <= count <= 40, f'за год выпало {count}'


# ── Предсказание ─────────────────────────────────────────────────────────

def test_twenty_quotes_loaded():
    assert len(STOIC_QUOTES) == 20
    assert load_stoic_quotes() == list(STOIC_QUOTES)   # кортеж — защита от правки


def test_every_quote_has_text_author_and_practice():
    for q in STOIC_QUOTES:
        assert q['text'].strip() and q['author'].strip()
        assert q['practice'].strip()
        assert q['text'].count('<') == 0, 'разметка в данных ломает parse_mode'


def test_quote_is_stable_within_a_day():
    d = date(2026, 8, 12)
    assert bracelet_quote(d) == bracelet_quote(d)


def test_consecutive_bracelet_days_get_different_quotes():
    """Одно и то же предсказание два браслета подряд обесценивает механику."""
    days = [date(2026, 8, 1) + timedelta(days=i) for i in range(400)]
    quotes = [bracelet_quote(d)['text'] for d in days if is_bracelet_day(d)]
    for a, b in zip(quotes, quotes[1:]):
        assert a != b


def test_all_quotes_get_used_over_time():
    days = [date(2026, 1, 1) + timedelta(days=i) for i in range(1500)]
    seen = {bracelet_quote(d)['text'] for d in days if is_bracelet_day(d)}
    assert len(seen) == 20, f'использовано только {len(seen)} предсказаний'


# ── Сообщение и подавление блоков ────────────────────────────────────────

def _notifier():
    import os
    os.environ.setdefault('TELEGRAM_TOKEN', 'test-token')
    os.environ.setdefault('TELEGRAM_CHAT_ID', 'test-chat')
    from notifier import PersonalScheduleNotifier
    return PersonalScheduleNotifier()


def _bracelet_date(after=date(2026, 8, 5)):
    d = after
    while not is_bracelet_day(d):
        d += timedelta(days=1)
    return d


def test_bracelet_message_carries_quote_and_no_tasks():
    n = _notifier()
    d = _bracelet_date()
    msg = n.format_bracelet_message(d.strftime('%d.%m.%Y'), d)
    quote = bracelet_quote(d)

    assert 'браслет' in msg.lower()
    assert quote['text'] in msg
    assert quote['author'] in msg
    assert '• ' not in msg, 'в удачный день задач быть не должно'
    assert msg.count('<b>') == msg.count('</b>')
    assert msg.count('<i>') == msg.count('</i>')
    assert len(msg) < 4096


def test_bracelet_message_is_not_parsed_as_a_checklist():
    """Трекер не должен увидеть в нём задач — иначе появятся чекбоксы
    и день попадёт в статистику как невыполненный."""
    import os
    os.environ.setdefault('TELEGRAM_TOKEN', 'test-token')
    from tracker_bot import TaskTrackerBot

    n, b = _notifier(), TaskTrackerBot()
    d = _bracelet_date()
    tasks = b.parse_tasks(n.format_bracelet_message(d.strftime('%d.%m.%Y'), d))
    assert not tasks['day'] and not tasks['evening'] and not tasks['cant_do']


def test_day_and_evening_are_suppressed_on_bracelet_day():
    import asyncio
    from datetime import datetime
    from unittest.mock import patch

    n = _notifier()
    d = _bracelet_date()
    sent = []

    async def fake_send(*a, **kw):
        sent.append(a)
        return True

    class BraceletDT(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(d.year, d.month, d.day, 11, 0)

    with patch('notifier.datetime', BraceletDT), \
         patch.object(type(n), 'send_telegram_message', fake_send):
        assert asyncio.run(n.send_message_for_period('day')) is True
        assert asyncio.run(n.send_message_for_period('evening')) is True

    assert sent == [], 'в день браслета задачи отменяются'


def test_weekly_strip_marks_bracelet_day_not_as_failure():
    """В полоске недели пустой день рисуется как «0% 😴» — то есть как
    слитый. Для браслета это ложь: задач не было по правилам игры."""
    import os
    os.environ.setdefault('TELEGRAM_TOKEN', 'test-token')
    from tracker_bot import TaskTrackerBot

    b = TaskTrackerBot()
    d = _bracelet_date()
    row = b.week_day_row(d, {})
    assert '🤍' in row
    assert '0%' not in row
    assert '😴' not in row


def test_weekly_strip_keeps_normal_days_intact():
    import os
    os.environ.setdefault('TELEGRAM_TOKEN', 'test-token')
    from tracker_bot import TaskTrackerBot

    b = TaskTrackerBot()
    d = date(2026, 8, 5)                      # обычная среда
    assert not is_bracelet_day(d)
    row = b.week_day_row(d, {'2026-08-05': {'percentage': 75}})
    assert '75%' in row and '🤍' not in row


def test_bracelet_day_does_not_lower_weekly_average():
    """Удачный день не пишет статистику вовсе, поэтому среднее считается
    по остальным дням — «повезло во всём» не должно снижать уровень."""
    import os
    os.environ.setdefault('TELEGRAM_TOKEN', 'test-token')
    from tracker_bot import TaskTrackerBot

    b = TaskTrackerBot()
    from datetime import datetime
    today = datetime.now()
    stats = {(today - timedelta(days=i)).strftime('%Y-%m-%d'):
             {'percentage': 80} for i in range(1, 4)}
    assert b.get_week_stats(stats)['avg'] == 80
