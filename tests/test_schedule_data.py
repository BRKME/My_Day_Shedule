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


def test_weekdays_have_two_distinct_sets_of_each_exercise():
    """Два подхода задуманы специально, но строки обязаны различаться:
    одинаковые отмечаются по индексам, и по сообщению не понять, какую
    именно нажал."""
    sched = load_schedule()
    for day in ('monday', 'tuesday', 'wednesday', 'thursday'):
        tasks = sched[day]['день']
        pull = [t for t in tasks if 'одтян' in t]
        abs_ = [t for t in tasks if 'пресс' in t]
        assert len(pull) == 2 and len(set(pull)) == 2, f'{day}: подтягивания'
        assert len(abs_) == 2 and len(set(abs_)) == 2, f'{day}: пресс'
        assert 'подход 1' in ' '.join(pull) and 'подход 2' in ' '.join(pull)


def test_no_reading_on_the_road_in_the_morning():
    """«Читать в дороге» убрано из утреннего блока 22.09.2026. Вечернее
    чтение в дороге остаётся — это другая задача."""
    sched = load_schedule()
    for day in ('monday', 'tuesday', 'wednesday', 'thursday', 'friday'):
        assert not any('Читать в дороге' in t for t in sched[day]['день']), day


def test_morning_split_survives_the_removal():
    """«Читать в дороге» было маркером границы утро/день. После удаления
    граница — English: утро не должно поглотить дневной блок, а «Включи
    мозг» должно остаться в дне."""
    sched = load_schedule()
    for day in ('monday', 'tuesday', 'wednesday', 'thursday', 'friday'):
        morning, rest = split_day_tasks(sched[day]['день'])
        assert morning[-1].startswith('Занятия English'), day
        assert rest[0].startswith('Включи мозг'), day


def test_saturday_split_is_unchanged():
    morning, rest = split_day_tasks(load_schedule()['saturday']['день'])
    assert morning[-1].startswith('Включи мозг')


def test_no_words_lost_to_emoji_stripping():
    """При чистке эмодзи 👅 заменял слово «язык» — фраза стала «мат это
    мусор и гнева». Остальные эмодзи были украшением, этот — словом."""
    for day, sections in load_schedule().items():
        for name, tasks in sections.items():
            for t in tasks:
                assert 'мусор и гнева' not in t, f'{day}/{name}'


def test_exercise_opens_the_morning():
    """Зарядка — первая задача утра с 22.09.2026."""
    sched = load_schedule()
    for day in ('monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday'):
        assert sched[day]['день'][0].startswith('Зарядка'), day
