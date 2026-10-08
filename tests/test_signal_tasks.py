# -*- coding: utf-8 -*-
"""Блок заданий SIGNAL в 10:00.

Данные пишет программа SIGNAL в data/signal_tasks.json по датам. Нет
даты — сообщение не уходит. Пункты нумеруются эмодзи, без «• »: иначе
tracker_bot принял бы их за задачи расписания и испортил статистику.
"""
import asyncio
import json
import os
import sys
from datetime import date

sys.path.insert(0, '.')

os.environ.setdefault('TELEGRAM_TOKEN', 'test-token')
os.environ.setdefault('TELEGRAM_CHAT_ID', 'test-chat')

import core


def _write(tmp_path, monkeypatch, data):
    (tmp_path / 'signal_tasks.json').write_text(
        json.dumps(data, ensure_ascii=False), encoding='utf-8')
    monkeypatch.setattr(core, 'DATA_DIR', str(tmp_path))


def test_missing_file_gives_no_tasks(tmp_path, monkeypatch):
    monkeypatch.setattr(core, 'DATA_DIR', str(tmp_path))
    assert core.signal_tasks_of_the_day(date(2026, 10, 9)) == []


def test_tasks_by_date(tmp_path, monkeypatch):
    _write(tmp_path, monkeypatch, {'2026-10-09': {'tasks': ['Йога', ' ', 'Lilloo']}})
    assert core.signal_tasks_of_the_day(date(2026, 10, 9)) == ['Йога', 'Lilloo']
    assert core.signal_tasks_of_the_day(date(2026, 10, 10)) == []


def test_plain_list_also_accepted(tmp_path, monkeypatch):
    _write(tmp_path, monkeypatch, {'2026-10-09': ['Йога']})
    assert core.signal_tasks_of_the_day(date(2026, 10, 9)) == ['Йога']


def test_message_has_no_tracker_bullets_and_escapes_html():
    from notifier import PersonalScheduleNotifier
    n = PersonalScheduleNotifier()
    msg = n.format_signal_message(date(2026, 10, 9), ['A < B & C', 'Йога'])
    assert '<b>SIGNAL · пятница 09.10</b>' in msg
    assert '1️⃣ A &lt; B &amp; C' in msg
    assert not any(line.startswith('• ') for line in msg.splitlines())


def test_no_tasks_sends_nothing(monkeypatch):
    from notifier import PersonalScheduleNotifier
    n = PersonalScheduleNotifier()
    monkeypatch.setattr('notifier.signal_tasks_of_the_day', lambda day: [])

    def boom(*a, **kw):
        raise AssertionError('не должно быть сетевого вызова')
    monkeypatch.setattr('notifier.aiohttp.ClientSession', boom)
    assert asyncio.run(n.send_message_for_period('signal')) is True


def test_signal_period_registered_in_cli_and_workflow():
    src = open('notifier.py', encoding='utf-8').read()
    assert "'pullups', 'weight', 'signal')" in src
    wf = open('.github/workflows/personal-schedule.yml', encoding='utf-8').read()
    assert '- signal' in wf


def test_data_file_is_valid_json():
    with open(os.path.join('data', 'signal_tasks.json'), encoding='utf-8') as f:
        assert isinstance(json.load(f), dict)
