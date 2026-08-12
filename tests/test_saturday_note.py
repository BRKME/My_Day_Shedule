# -*- coding: utf-8 -*-
"""Субботняя ремарка «выходные — для бедных».

Фраза держится в системе ради второго прочтения: речь не о том, чтобы
работать в субботу, а о том, чтобы не ждать пятницы всю неделю. Голая
цитата читается ровно наоборот и каждую субботу подтачивала бы то, что
в расписании защищено осознанно — разгруженную субботу и воскресенье
без задач.

Поэтому расшифровка — часть ремарки, а не украшение: тест на неё стоит
здесь, чтобы её нельзя было «сократить» мимоходом.
"""
import asyncio
import os
import sys

sys.path.insert(0, '.')

os.environ.setdefault('TELEGRAM_TOKEN', 'test-token')
os.environ.setdefault('TELEGRAM_CHAT_ID', 'test-chat')

from core import SATURDAY_NOTE
from notifier import PersonalScheduleNotifier
from tracker_bot import TaskTrackerBot


def _morning(day_key, date_str, block='morning'):
    n = PersonalScheduleNotifier()
    return asyncio.run(n.format_morning_day_message(
        date_str, day_key, n.schedule[day_key], block=block))


def test_note_is_shown_on_saturday_morning():
    msg = _morning('saturday', '08.08.2026')
    assert SATURDAY_NOTE['quote'] in msg
    assert SATURDAY_NOTE['meaning'] in msg


def test_note_carries_its_interpretation():
    """Без расшифровки фраза читается как «работай в выходные»."""
    assert 'не о том' in SATURDAY_NOTE['meaning'].lower()
    assert len(SATURDAY_NOTE['meaning']) > 40


def test_note_is_absent_on_other_days():
    for day, ds in (('monday', '03.08.2026'), ('wednesday', '05.08.2026'),
                    ('friday', '07.08.2026'), ('sunday', '09.08.2026')):
        assert SATURDAY_NOTE['quote'] not in _morning(day, ds), day


def test_note_is_absent_in_saturday_evening():
    n = PersonalScheduleNotifier()
    msg = asyncio.run(n.format_evening_message(
        '08.08.2026', 'saturday', n.schedule['saturday']))
    assert SATURDAY_NOTE['quote'] not in msg


def test_note_adds_no_tasks():
    """Ремарка не должна попасть в чек-лист: строки задач начинаются
    с «• », и лишний буллет сдвинул бы индексы прогресса."""
    b = TaskTrackerBot()
    with_note = b.parse_tasks(_morning('saturday', '08.08.2026'))
    assert len(with_note['day']) == 5      # столько же, сколько до ремарки
    assert SATURDAY_NOTE['quote'] not in ' '.join(with_note['day'])


def test_saturday_message_stays_valid_html_and_short():
    msg = _morning('saturday', '08.08.2026')
    assert msg.count('<i>') == msg.count('</i>')
    assert msg.count('<b>') == msg.count('</b>')
    assert len(msg) < 4096


def test_saturday_message_has_no_page_link_whatever_day_it_is_built():
    """Сообщение должно зависеть от своей даты, а не от системных часов:
    иначе субботний текст, собранный в среду, тащит будний блок."""
    msg = _morning('saturday', '08.08.2026')
    assert '.html' not in msg


def test_weekday_message_link_matches_its_own_date():
    from core import page_of_the_day, page_url
    from datetime import date
    msg = _morning('wednesday', '12.08.2026')
    assert page_url(page_of_the_day(date(2026, 8, 12))) in msg
