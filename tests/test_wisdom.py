# -*- coding: utf-8 -*-
"""Мудрость дня.

Раньше список состоял из одной фразы, и random.choice выдавал её всегда.
Теперь фраз две, и они чередуются по дням — детерминированно от даты,
чтобы повторный рендер сообщения не подменил текст.
"""
import sys
from datetime import date, timedelta

sys.path.insert(0, '.')

from core import WISDOMS, wisdom_of_the_day


def test_two_wisdoms_registered():
    assert len(WISDOMS) == 2
    assert all(w.strip() for w in WISDOMS)


def test_alternates_day_by_day():
    d = date(2026, 8, 10)
    seq = [wisdom_of_the_day(d + timedelta(days=i)) for i in range(6)]
    for a, b in zip(seq, seq[1:]):
        assert a != b, 'две одинаковые мудрости подряд'


def test_stable_within_a_day():
    d = date(2026, 8, 10)
    assert wisdom_of_the_day(d) == wisdom_of_the_day(d)


def test_both_appear_evenly():
    d = date(2026, 8, 10)
    seen = [wisdom_of_the_day(d + timedelta(days=i)) for i in range(30)]
    assert len(set(seen)) == 2
    assert abs(seen.count(WISDOMS[0]) - seen.count(WISDOMS[1])) <= 1


def test_morning_message_uses_the_wisdom_of_that_date():
    import asyncio
    import os
    os.environ.setdefault('TELEGRAM_TOKEN', 'test-token')
    os.environ.setdefault('TELEGRAM_CHAT_ID', 'test-chat')
    from notifier import PersonalScheduleNotifier

    n = PersonalScheduleNotifier()
    msg = asyncio.run(n.format_morning_day_message(
        '12.08.2026', 'wednesday', n.schedule['wednesday'], block='morning'))
    assert wisdom_of_the_day(date(2026, 8, 12)) in msg
