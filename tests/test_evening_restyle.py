# -*- coding: utf-8 -*-
"""Рестайл вечернего сообщения (вариант Б, 16.07).

Инварианты активного текста (tracker_bot парсит и редактирует сообщение):
  - строки задач начинаются с '• ' — по ним parse_tasks и ⭐-подсветка;
  - заголовки секций содержат маркеры 'Вечерние задачи' / 'Нельзя делать';
  - прогресс хранится ПО ИНДЕКСАМ строк — число и порядок задач неизменны;
  - строка бюджета не начинается с '📊' (такие чистятся как прогресс-бары).

Рестайл на лету (данные расписания не трогаем): эмодзи в начало строки,
минуты из скобок в единый формат '— Nм', мотивация тихим италиком,
в шапке — бюджет времени с перегрузом и кандидатом на перенос.
"""
import asyncio
import sys
from datetime import datetime

sys.path.insert(0, '.')

from notifier import (PersonalScheduleNotifier, budget_header,
                      normalize_task, task_minutes)
from tracker_bot import TaskTrackerBot as TaskTracker


# ── normalize_task: единый формат строки ────────────────────────────────────

def test_emoji_moves_to_front_minutes_unified():
    src = 'Читать 📖 в дороге <i>(30 min это Спорт для мозга)</i>'
    assert normalize_task(src) == '📖 Читать в дороге — 30м · <i>спорт для мозга</i>'


def test_minutes_only():
    assert normalize_task('Семейный 🍽️ ужин <i>(30 min)</i>') == \
        '🍽️ Семейный ужин — 30м'


def test_motivation_only():
    assert normalize_task('Проверить 📝 оценки детей <i>(Контроль учёбы)</i>') == \
        '📝 Проверить оценки детей · <i>контроль учёбы</i>'


def test_emoji_already_leading_kept_as_is():
    assert normalize_task('🌙 Мой SPA-ритуал') == '🌙 Мой SPA-ритуал'


def test_no_emoji_no_parens_passthrough():
    assert normalize_task('Просто задача') == 'Просто задача'


def test_cant_do_normalized():
    src = 'Не ⚡ Есть после 22-00 <i>( Цель 85 кг. )</i>'
    assert normalize_task(src) == '⚡ Не есть после 22-00 · <i>цель 85 кг.</i>'


def test_task_minutes_extraction():
    assert task_minutes('📖 x <i>(30 min это спорт)</i>') == 30
    assert task_minutes('💻 Pet Project — 120м') == 120
    assert task_minutes('🌙 Мой SPA-ритуал') == 0


# ── бюджет времени в шапке ──────────────────────────────────────────────────

def _tasks_5h20():
    return ['📖 a — 30м', '🍽 b — 30м', '📝 c — 5м', '😌 d — 60м',
            '📊 e — 30м', '💻 Pet Project — 120м', '📚 f — 20м',
            '🤖 g — 15м', '📔 h — 10м', '💨 i — 1м', '🌙 j',
            '💊 k — 1м', '🙏 l — 5м']


def test_budget_header_overload_names_longest_task():
    now = datetime(2026, 7, 15, 19, 0)     # окно до 23:30 = 4ч 30м
    hdr = budget_header(_tasks_5h20(), now, end_hhmm="23:30")
    assert hdr.startswith('⏱')             # не 📊 и не • — инварианты трекера
    assert '5ч 27м' in hdr
    assert '4ч 30м' in hdr
    assert 'перегруз' in hdr and '57м' in hdr
    assert 'Pet Project' in hdr            # кандидат на перенос


def test_budget_header_fits_no_warning():
    now = datetime(2026, 7, 15, 18, 0)     # окно 5ч 30м > плана
    hdr = budget_header(_tasks_5h20(), now, end_hhmm="23:30")
    assert 'перегруз' not in hdr and 'перенос' not in hdr
    assert 'запас' in hdr


# ── роунд-трип с трекером: активный текст не сломан ─────────────────────────

def _notifier():
    import os
    os.environ.setdefault('TELEGRAM_TOKEN', 'test')
    os.environ.setdefault('TELEGRAM_CHAT_ID', 'test')
    return PersonalScheduleNotifier()


def _evening_message():
    n = _notifier()
    return asyncio.run(
        n.format_evening_message('16.07.2026', 'wednesday',
                                 n.schedule['wednesday']))


def test_roundtrip_tracker_parses_same_counts():
    msg = _evening_message()
    tr = TaskTracker.__new__(TaskTracker)
    tasks = tr.parse_tasks(msg)
    assert len(tasks['evening']) == 13     # число строк-задач неизменно
    assert len(tasks['cant_do']) == 2
    assert tasks['day'] == []


def test_roundtrip_star_highlight_still_works():
    msg = _evening_message()
    tr = TaskTracker.__new__(TaskTracker)
    tasks = tr.parse_tasks(msg)
    updated = tr.update_original_message_with_progress(
        msg, tasks, {'morning': [], 'day': [], 'cant_do': [], 'evening': [0, 5]})
    starred = [l for l in updated.split('\n') if '⭐' in l]
    assert len(starred) == 2
    assert any('Pet Project' in l for l in starred)


def test_budget_line_survives_progress_update():
    msg = _evening_message()
    tr = TaskTracker.__new__(TaskTracker)
    tasks = tr.parse_tasks(msg)
    updated = tr.update_original_message_with_progress(
        msg, tasks, {'morning': [], 'day': [], 'cant_do': [], 'evening': [0]})
    assert '⏱' in updated                  # шапка бюджета не съедена очисткой


# ── страж: расписание не должно возвращаться к перегрузу ────────────────────

def test_no_evening_overload_any_day():
    """16.07: все вечера пн–сб были перегружены (+45…+77м) — план, который
    не влезает, тренирует привычку его не выполнять. После ребаланса
    (Отдых 60→30, Pet Project 120→90, LP убран из пятницы) каждый вечер
    обязан влезать в окно 19:00–23:30. Добавил задачу — тест напомнит."""
    n = _notifier()
    window = 270
    for day, sched in n.schedule.items():
        tasks = [normalize_task(t) for t in sched.get('вечер', [])]
        total = sum(task_minutes(t) for t in tasks)
        assert total <= window, (
            f"{day}: план {total}м > окна {window}м — вечер снова перегружен")


# ── старт бота не должен откатывать локальную стату гитхабовской ────────────

def test_merge_stats_local_wins():
    """16.07: GitHub-синк умер с отзывом PAT (401), локальная стата на VPS
    ушла вперёд гитхабовской. Старый load_stats_from_github ПЕРЕЗАПИСЫВАЛ
    локальный stats.json репо-версией при каждом старте — рестарт бота
    (например, от autoupdate) откатил бы прогресс к 13.07. Слияние:
    объединение дней, при конфликте локальный день побеждает."""
    from tracker_bot import merge_stats
    github = {"2026-07-12": {"percentage": 80},
              "2026-07-13": {"percentage": None}}
    local = {"2026-07-13": {"percentage": 90},
             "2026-07-15": {"percentage": 100}}
    merged = merge_stats(github, local)
    assert merged["2026-07-12"]["percentage"] == 80    # только в GitHub — взят
    assert merged["2026-07-13"]["percentage"] == 90    # конфликт — локальный
    assert merged["2026-07-15"]["percentage"] == 100   # только локально — цел


def test_merge_stats_empty_local():
    from tracker_bot import merge_stats
    github = {"2026-07-12": {"percentage": 80}}
    assert merge_stats(github, {}) == github


def test_budget_window_uses_msk_not_utc():
    """16.07: VPS в UTC, naive now() завышал окно на 3ч («запас 3ч 3м»
    при реальных 3м). Рендер обязан считать окно по Europe/Moscow."""
    from unittest.mock import patch
    from zoneinfo import ZoneInfo
    import notifier as nf
    n = _notifier()
    real_dt = datetime
    with patch('notifier.datetime') as dt:
        # 16:00 UTC == 19:00 MSK; naive now() вернул бы 16:00
        dt.now = lambda tz=None: real_dt(2026, 7, 16, 19, 0,
                                         tzinfo=ZoneInfo("Europe/Moscow")) \
            if tz else real_dt(2026, 7, 16, 16, 0)
        msg = asyncio.run(n.format_evening_message(
            '16.07.2026', 'thursday', n.schedule['thursday']))
    assert '~4ч 30м' in msg          # окно от 19:00 МСК, не от 16:00 UTC
    assert '3ч' not in msg.split('\n')[1].replace('4ч 30м', '')
