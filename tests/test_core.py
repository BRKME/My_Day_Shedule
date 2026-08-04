# -*- coding: utf-8 -*-
"""Тесты общего ядра (core.py).

Логика, которая раньше жила в двух копиях — в notifier.py и tracker_bot.py.
Расхождение копий уже кусало (load_stats_from_github, 16.07), поэтому здесь
фиксируем контракт один раз для обоих потребителей.
"""
import sys

sys.path.insert(0, '.')

from core import (LEVELS, get_level, merge_stats, normalize_task,
                  prune_message_states, task_minutes, load_schedule,
                  load_kids_schedule, split_day_tasks, MORNING_BOUNDARIES)


# ── Минуты и нормализация ────────────────────────────────────────────────

def test_task_minutes_reads_both_formats():
    assert task_minutes('Читать 📖 <i>(30 min спорт)</i>') == 30
    assert task_minutes('Читать 📖 — 25м') == 25
    assert task_minutes('Задача без времени') == 0


def test_normalize_task_moves_emoji_to_front():
    out = normalize_task('Читать 📖 в дороге <i>(30 min это Спорт для мозга)</i>')
    assert out.startswith('📖 ')
    assert '— 30м' in out
    assert out.count('<i>') == 1


def test_normalize_task_is_idempotent():
    src = 'Читать 📖 в дороге <i>(30 min это Спорт для мозга)</i>'
    once = normalize_task(src)
    assert normalize_task(once) == once


def test_normalize_task_keeps_latin_names_capitalized():
    assert 'Project' in normalize_task('Pet 💻 Project <i>(90 min)</i>')


# ── Уровни ───────────────────────────────────────────────────────────────

def test_levels_are_ordered_and_cover_full_range():
    ranks = [lv['rank'] for lv in LEVELS]
    assert ranks == sorted(ranks)
    for pct in range(0, 101):
        assert get_level(pct) is not None


def test_get_level_boundaries():
    assert get_level(0)['name'] == 'Хаос'
    assert get_level(100)['rank'] == max(lv['rank'] for lv in LEVELS)


def test_get_level_is_monotonic():
    """Больше процент — не ниже ранг. Иначе мотивация работает против цели."""
    prev = 0
    for pct in range(0, 101):
        rank = get_level(pct)['rank']
        assert rank >= prev
        prev = rank


# ── Слияние статистики ───────────────────────────────────────────────────

def test_merge_stats_local_wins_on_conflict():
    github = {'2026-08-01': {'percentage': 10}, '2026-08-02': {'percentage': 20}}
    local = {'2026-08-02': {'percentage': 99}, '2026-08-03': {'percentage': 50}}
    merged = merge_stats(github, local)
    assert merged['2026-08-02']['percentage'] == 99   # локальный источник истины
    assert merged['2026-08-01']['percentage'] == 10   # история с GitHub цела
    assert merged['2026-08-03']['percentage'] == 50


def test_merge_stats_never_loses_days():
    github = {f'2026-07-{d:02d}': {} for d in range(1, 20)}
    local = {f'2026-08-{d:02d}': {} for d in range(1, 5)}
    assert len(merge_stats(github, local)) == 23


# ── Прополка состояний сообщений ─────────────────────────────────────────

def test_prune_keeps_only_newest_states():
    states = {i: {'tasks': {}, 'completed': {}} for i in range(1, 101)}
    pruned = prune_message_states(states, keep_last=30)
    assert len(pruned) == 30
    assert max(pruned) == 100
    assert min(pruned) == 71


def test_prune_is_noop_when_under_limit():
    states = {1: {}, 2: {}, 3: {}}
    assert prune_message_states(states, keep_last=30) == states


def test_prune_handles_string_keys():
    """С GitHub состояния приходят со строковыми ключами — сортировка
    должна быть числовой, иначе '9' > '100' и свежие состояния улетают."""
    states = {'9': {}, '100': {}, '101': {}}
    pruned = prune_message_states(states, keep_last=2)
    assert set(int(k) for k in pruned) == {100, 101}


def test_prune_preserves_entry_payload():
    states = {1: {'tasks': {'day': ['a']}, 'completed': {'day': [0]},
                  'original_text': 'x', 'clean_original': 'x'}}
    assert prune_message_states(states, keep_last=30)[1]['clean_original'] == 'x'


# ── Данные расписания ────────────────────────────────────────────────────

def test_load_schedule_has_all_seven_days():
    sched = load_schedule()
    assert set(sched) == {'monday', 'tuesday', 'wednesday', 'thursday',
                          'friday', 'saturday', 'sunday'}


def test_load_kids_schedule_uses_russian_day_names():
    assert 'понедельник' in load_kids_schedule()


def test_split_day_tasks_morning_includes_boundary():
    tasks = ['a', 'Читать 📖 в дороге', 'b', 'c']
    morning, day = split_day_tasks(tasks)
    assert morning == ['a', 'Читать 📖 в дороге']
    assert day == ['b', 'c']


def test_split_day_tasks_falls_back_to_brain_marker():
    """Суббота: дороги нет, граница — «Включи 🧠 Мозг»."""
    tasks = ['a', 'Включи 🧠 Мозг', 'b']
    morning, day = split_day_tasks(tasks)
    assert morning == ['a', 'Включи 🧠 Мозг']
    assert day == ['b']


def test_split_day_tasks_no_marker_is_failsafe():
    """Без маркеров всё уходит в утро — лучше одно полное сообщение,
    чем потерянные задачи."""
    tasks = ['a', 'b']
    assert split_day_tasks(tasks) == (['a', 'b'], [])


def test_morning_boundaries_priority_order():
    assert MORNING_BOUNDARIES[0].startswith('Читать')
