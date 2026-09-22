# -*- coding: utf-8 -*-
"""Локальная статистика — источник истины, GitHub — реплика.

Аудит 22.09.2026: при каждой галочке трекер брал за основу копию из
GitHub. Стоило синку хоть раз не пройти, следующая галочка перезаписывала
локальный файл отставшей копией — пропадали вчерашний день и вес.
"""
import asyncio
import json
import os
import sys

import pytest

sys.path.insert(0, '.')

os.environ.setdefault('TELEGRAM_TOKEN', 'test-token')
os.environ.setdefault('TELEGRAM_CHAT_ID', 'test-chat')

from core import merge_stats


@pytest.fixture
def bot(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from tracker_bot import TaskTrackerBot
    b = TaskTrackerBot()
    b.stats_file = str(tmp_path / 'stats.json')
    b.message_state = {}

    async def noop(*a, **k):
        return True

    async def save(self, st):
        with open(self.stats_file, 'w', encoding='utf-8') as f:
            json.dump(st, f, ensure_ascii=False)
        return True

    for m in ('edit_message', 'send_message', 'send_penalty_message',
              'sync_stats_to_github'):
        monkeypatch.setattr(type(b), m, noop, raising=False)
    monkeypatch.setattr(type(b), 'save_stats', save)
    monkeypatch.setattr(type(b), 'get_today_key', lambda self: '2026-09-23')
    return b


def _tap(bot, github):
    from notifier import PersonalScheduleNotifier

    async def gh(self, path):
        return json.dumps(github) if github is not None else None

    type(bot)._github_get_file = gh
    n = PersonalScheduleNotifier()
    msg = asyncio.run(n.format_morning_day_message(
        '23.09.2026', 'wednesday', n.schedule['wednesday'], block='morning'))
    asyncio.run(bot.show_checklist(1, msg))
    bot.message_state[1]['completed']['day'] = [0]
    asyncio.run(bot.save_progress(1))
    return json.load(open(bot.stats_file, encoding='utf-8'))


def test_stale_github_does_not_erase_local_data(bot):
    local = {'2026-09-22': {'percentage': 80}, 'weight': {'2026-09-22': 91.0}}
    json.dump(local, open(bot.stats_file, 'w'))
    after = _tap(bot, {'2026-09-21': {'percentage': 50}})
    assert after['2026-09-22'] == {'percentage': 80}
    assert after['weight'] == {'2026-09-22': 91.0}


def test_github_only_days_are_kept(bot):
    json.dump({'2026-09-22': {'percentage': 80}}, open(bot.stats_file, 'w'))
    after = _tap(bot, {'2026-09-01': {'percentage': 70}})
    assert after['2026-09-01'] == {'percentage': 70}


def test_works_when_github_is_unavailable(bot):
    json.dump({'2026-09-22': {'percentage': 80}}, open(bot.stats_file, 'w'))
    after = _tap(bot, None)
    assert after['2026-09-22'] == {'percentage': 80}
    assert after['2026-09-23']['day']['completed'] == [0]


def test_notifier_fields_from_github_survive_on_the_same_day():
    """Нотификатор пишет служебные поля дня (_tasks) в GitHub. Если
    локальная запись дня есть, её поля побеждают, но служебные поля
    GitHub не теряются."""
    github = {'2026-09-23': {'_tasks': {'day': ['a']}, 'percentage': 10}}
    local = {'2026-09-23': {'percentage': 40}}
    merged = merge_stats(github, local)
    assert merged['2026-09-23']['percentage'] == 40
    assert merged['2026-09-23']['_tasks'] == {'day': ['a']}
