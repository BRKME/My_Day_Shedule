# -*- coding: utf-8 -*-
"""Арифметика итогов дня.

Заменяет test_simulation.py, который переписывал рендер сообщения заново
(со своей мёртвой лестницей уровней TITANIUM/STEEL/IRON) и ничего не
проверял. Здесь считает production-код.

Главное правило: «Нельзя делать» в процент выполнения НЕ входит. Это
запреты, а не задачи — засчитывать их в прогресс значит поощрять срыв.
"""
import sys

sys.path.insert(0, '.')

from core import summarize_day


def _day(day_done, day_total, ev_done, ev_total, fails=0, fails_total=3):
    return {
        'day': {'completed': list(range(day_done)), 'total': day_total},
        'evening': {'completed': list(range(ev_done)), 'total': ev_total},
        'cant_do': {'completed': list(range(fails)), 'total': fails_total},
    }


def test_splits_day_and_evening():
    s = summarize_day(_day(5, 8, 3, 5))
    assert (s['day_done'], s['day_total']) == (5, 8)
    assert (s['evening_done'], s['evening_total']) == (3, 5)


def test_total_is_day_plus_evening():
    s = summarize_day(_day(5, 8, 3, 5))
    assert s['overall_done'] == 8
    assert s['overall_total'] == 13
    assert s['percentage'] == 61


def test_forbidden_tasks_excluded_from_percentage():
    """Срывы считаются отдельно и процент не двигают."""
    clean = summarize_day(_day(4, 8, 2, 5, fails=0))
    broken = summarize_day(_day(4, 8, 2, 5, fails=3))
    assert clean['percentage'] == broken['percentage']
    assert broken['fails'] == 3
    assert clean['fails'] == 0


def test_empty_day_does_not_divide_by_zero():
    s = summarize_day({'day': {'completed': [], 'total': 0},
                       'evening': {'completed': [], 'total': 0},
                       'cant_do': {'completed': [], 'total': 0}})
    assert s['percentage'] == 0
    assert s['overall_total'] == 0


def test_missing_sections_are_tolerated():
    """Ранние дни в stats.json без секции evening не должны ронять итоги."""
    s = summarize_day({'day': {'completed': [0, 1], 'total': 4}})
    assert s['percentage'] == 50
    assert s['evening_total'] == 0


def test_perfect_day_is_hundred():
    s = summarize_day(_day(8, 8, 5, 5))
    assert s['percentage'] == 100


def test_percentage_never_exceeds_hundred():
    """Список выполненных может пережить сокращение расписания —
    процент выше 100 в итогах выглядит как поломка."""
    s = summarize_day(_day(10, 8, 5, 5))
    assert s['percentage'] == 100
