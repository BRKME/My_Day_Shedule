# -*- coding: utf-8 -*-
"""Страховка на данные расписания (data/schedule.json).

С 04.08.2026 расписание правится руками в JSON. Ошибка в этом файле тише,
чем ошибка в коде: бот не падает, а просто присылает неполный день. Здесь
фиксируем структурные инварианты, на которые опирается рендер.
"""
import sys

sys.path.insert(0, '.')

from core import load_kids_schedule, load_schedule, split_day_tasks

DAYS = ('monday', 'tuesday', 'wednesday', 'thursday',
        'friday', 'saturday', 'sunday')
SECTIONS = ('день', 'нельзя_утро', 'нельзя_день', 'нельзя_вечер', 'вечер')


def test_every_day_has_every_section():
    sched = load_schedule()
    for day in DAYS:
        assert set(sched[day]) == set(SECTIONS), f'{day}: секции разъехались'


def test_all_tasks_are_nonempty_strings():
    for day, sections in load_schedule().items():
        for name, tasks in sections.items():
            assert isinstance(tasks, list), f'{day}/{name} — не список'
            for t in tasks:
                assert isinstance(t, str) and t.strip(), f'{day}/{name}: пустая задача'


def test_italic_tags_are_balanced():
    """Незакрытый <i> ломает parse_mode=HTML — Telegram отвергает сообщение
    целиком, и день уходит без плана."""
    for day, sections in load_schedule().items():
        for name, tasks in sections.items():
            for t in tasks:
                assert t.count('<i>') == t.count('</i>'), f'{day}/{name}: {t}'


def test_working_days_have_morning_boundary():
    """Без маркера границы весь день схлопывается в утреннее сообщение."""
    sched = load_schedule()
    for day in DAYS:
        tasks = sched[day]['день']
        if len(tasks) <= 1:
            continue                       # воскресенье — FamilyDay без задач
        morning, rest = split_day_tasks(tasks)
        assert morning, f'{day}: пустой утренний блок'
        assert rest, f'{day}: маркер границы утро/день потерян'


def test_kids_schedule_entries_have_required_fields():
    for day, lessons in load_kids_schedule().items():
        for lesson in lessons:
            assert set(lesson) >= {'child', 'activity', 'time'}, f'{day}: {lesson}'
            assert '-' in lesson['time'], f'{day}: время без диапазона'


def test_friday_has_no_pullups_or_abs_in_day_block():
    """В пятницу отдельным сообщением приходит зачёт по подтягиваниям —
    те же упражнения в дневном блоке дублируют его и портят процент."""
    for task in load_schedule()['friday']['день']:
        assert 'одтян' not in task and 'пресс' not in task, task


def test_exercises_are_not_duplicated_within_a_day():
    """Одна и та же строка дважды в секции ломает прогресс: обе задачи
    отмечаются по индексам, и человек не понимает, какую именно нажал."""
    for day, sections in load_schedule().items():
        for name, tasks in sections.items():
            assert len(tasks) == len(set(tasks)), f'{day}/{name}: дубль'
