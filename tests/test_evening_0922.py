# -*- coding: utf-8 -*-
"""Вечер, пересборка 22.09.2026: двенадцать пунктов в шесть."""
import sys

sys.path.insert(0, '.')

from core import load_schedule, normalize_task

CORE = ['Семейный ужин — 30м',
        'Проверить оценки детей',
        'Проект дня — 60м',
        'Читать с Мартой без телефона — 20м',
        'Вечерняя сессия SIGNAL — 15м',
        'Увлажнитель · SPA · благодарность']


def _evening(day):
    return [normalize_task(t) for t in load_schedule()[day]['вечер']]


def test_weekday_evening_is_exactly_the_six():
    for day in ('monday', 'tuesday', 'wednesday', 'thursday'):
        assert _evening(day) == CORE, day


def test_friday_keeps_its_room_check():
    """Зачёт по чистоте — пятничная семейная традиция, как зачёт по
    подтягиваниям. Убирать её не просили."""
    ev = _evening('friday')
    assert ev[:6] == CORE
    assert any('чистоте комнаты' in t for t in ev)


def test_saturday_gets_no_new_items():
    """В субботу ужина и оценок не было — не добавляем."""
    ev = _evening('saturday')
    assert 'Семейный ужин — 30м' not in ev
    assert 'Проверить оценки детей' not in ev
    assert 'Проект дня — 60м' in ev
    assert any('фильма' in t for t in ev)


def test_merged_and_renamed_items_are_gone():
    gone = ('Читать в дороге', 'Отдых', 'CRPT LP', 'Pet Project', 'GROK',
            'Эмоциональный дневник', 'Включи увлажнитель', 'Мой SPA-ритуал',
            'Вечерняя благодарность')
    for day, secs in load_schedule().items():
        for t in secs['вечер']:
            assert not t.startswith(gone), f'{day}: {t}'


def test_evening_prohibitions_untouched():
    s = load_schedule()
    assert any('22-00' in t for t in s['monday']['нельзя_вечер'])
    assert any('алкоголь' in t for t in s['monday']['нельзя_вечер'])
