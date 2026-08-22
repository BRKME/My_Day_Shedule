# -*- coding: utf-8 -*-
"""Контрольное взвешивание.

По аналогии с зачётом по подтягиваниям: отдельное сообщение с кнопками,
результат копится в stats.json по датам.

Отличия от подтягиваний, из-за которых нельзя просто скопировать код:
вес дробный (85.4), а цель убывающая — 15 подтягиваний это «не меньше»,
а 85 кг это «не больше».
"""
import os
import sys
from datetime import date, timedelta

import pytest

sys.path.insert(0, '.')

os.environ.setdefault('TELEGRAM_TOKEN', 'test-token')
os.environ.setdefault('TELEGRAM_CHAT_ID', 'test-chat')

from core import WEIGHT_GOAL, weight_buttons, weight_verdict


# ── Кнопки ───────────────────────────────────────────────────────────────

def test_goal_is_85():
    assert WEIGHT_GOAL == 85.0


def test_buttons_cover_a_realistic_range():
    values = [b for row in weight_buttons(88.0) for b in row]
    assert min(values) < 85.0 < max(values)


def test_buttons_are_centred_on_the_last_weight():
    """Вчера было 88 — сегодня почти наверняка 87–89, и эти значения
    должны быть под пальцем, а не в конце длинного списка."""
    values = [b for row in weight_buttons(88.0) for b in row]
    assert 88.0 in values
    assert 87.5 in values and 88.5 in values


def test_buttons_have_a_step_of_half_a_kilo():
    values = sorted(b for row in weight_buttons(86.0) for b in row)
    steps = {round(b - a, 1) for a, b in zip(values, values[1:])}
    assert steps == {0.5}


def test_first_time_buttons_are_around_the_goal():
    """Истории ещё нет — центрируем на цели, чтобы не гадать."""
    values = [b for row in weight_buttons(None) for b in row]
    assert WEIGHT_GOAL in values


def test_buttons_fit_the_screen():
    rows = weight_buttons(88.0)
    assert len(rows) <= 4
    assert all(len(r) <= 4 for r in rows)


# ── Вердикт ──────────────────────────────────────────────────────────────

def test_goal_reached_is_celebrated():
    assert '🎯' in weight_verdict(84.5, previous=86.0)


def test_loss_is_noted_even_above_the_goal():
    """Цель убывающая: минус полкило по дороге к 85 — это движение,
    а не провал."""
    text = weight_verdict(87.0, previous=87.5)
    assert '−0.5' in text or '-0.5' in text


def test_gain_is_stated_without_scolding():
    text = weight_verdict(88.0, previous=87.5).lower()
    assert 'провал' not in text and 'плохо' not in text


def test_first_entry_has_no_comparison():
    text = weight_verdict(88.0, previous=None)
    assert '88' in text


def test_verdict_says_how_far_the_goal_is():
    assert '3' in weight_verdict(88.0, previous=88.0)


# ── Сообщение и история ──────────────────────────────────────────────────

@pytest.fixture
def bot(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from tracker_bot import TaskTrackerBot
    b = TaskTrackerBot()
    b.stats_file = str(tmp_path / 'stats.json')
    return b


def _write_stats(bot, data):
    """Статистика живёт в файле, а не в атрибуте: у бота нет self.stats."""
    import json
    with open(bot.stats_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)


def test_weight_is_saved_by_date(bot):
    import asyncio
    asyncio.run(bot.save_weight(87.5))
    stats = bot.load_stats()
    today = date.today().strftime('%Y-%m-%d')
    assert stats['weight'][today] == 87.5


def test_history_accumulates(bot):
    import asyncio
    _write_stats(bot, {'weight': {'2026-08-20': 88.0, '2026-08-21': 87.5}})
    asyncio.run(bot.save_weight(87.0))
    assert len(bot.load_stats()['weight']) == 3


def test_last_weight_is_found_for_the_verdict(bot):
    _write_stats(bot, {'weight': {
        (date.today() - timedelta(days=1)).strftime('%Y-%m-%d'): 88.0}})
    value, day = bot.get_last_weight(days=7)
    assert value == 88.0


def test_no_last_weight_on_a_clean_start(bot):
    assert bot.get_last_weight(days=7) == (None, None)


def test_old_entries_are_ignored(bot):
    """Вес месячной давности не годится для «со вчера»."""
    _write_stats(bot, {'weight': {'2020-01-01': 95.0}})
    assert bot.get_last_weight(days=7) == (None, None)


def test_message_has_buttons_around_the_last_weight(bot):
    import asyncio
    import os
    os.environ.setdefault('TELEGRAM_TOKEN', 'test-token')
    from notifier import PersonalScheduleNotifier

    n = PersonalScheduleNotifier()
    kb = n.weight_keyboard(previous=88.0)
    data = [b['callback_data'] for row in kb['inline_keyboard'] for b in row]
    assert 'weight_88.0' in data
    assert any(d.startswith('weight_') for d in data)


def test_callback_saves_and_answers(bot, monkeypatch):
    import asyncio
    calls = {}

    async def fake_answer(self, qid, text=None):
        calls['text'] = text

    async def fake_sync(self, stats):
        calls['synced'] = True
        return True

    async def fake_edit(self, message_id, text, reply_markup=None):
        calls['edited'] = text
        return True

    monkeypatch.setattr(type(bot), 'answer_callback_query', fake_answer)
    monkeypatch.setattr(type(bot), 'sync_stats_to_github', fake_sync)
    monkeypatch.setattr(type(bot), 'edit_message', fake_edit)

    asyncio.run(bot.process_callback('weight_87.5', 'q1', 5, 'текст'))
    today = date.today().strftime('%Y-%m-%d')
    assert bot.load_stats()['weight'][today] == 87.5
    assert calls['text']


def test_load_stats_keeps_section_keys(bot, tmp_path):
    """load_stats фильтровал ключи по наличию дефиса, оставляя только
    даты, — и выбрасывал секции pullups и weight. История подтягиваний
    уцелела лишь потому, что читается в обход."""
    import json
    (tmp_path / 'stats.json').write_text(json.dumps({
        '_info': 'служебное',
        '2026-08-20': {'percentage': 50},
        'pullups': {'2026-08-20': 15},
        'weight': {'2026-08-20': 88.0},
    }), encoding='utf-8')
    stats = bot.load_stats()
    assert 'weight' in stats and 'pullups' in stats
    assert '_info' not in stats
    assert '2026-08-20' in stats
