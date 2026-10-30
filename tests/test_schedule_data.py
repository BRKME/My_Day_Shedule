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


def test_no_day_block_anywhere():
    """Дневной блок снят 30.10.2026: его не отмечали, а важные из него были
    только подтягивания (теперь — строка SIGNAL по будням). Всё до границы
    утра включительно, после неё — пусто: дневное сообщение не уходит."""
    sched = load_schedule()
    for day in DAYS:
        tasks = sched[day]['день']
        if len(tasks) <= 1:
            continue                       # воскресенье — FamilyDay без задач
        morning, rest = split_day_tasks(tasks)
        assert morning == tasks, f'{day}: граница утра потеряна'
        assert not rest, f'{day}: дневной блок вернулся'
        assert not sched[day]['нельзя_день'], f'{day}: дневные запреты переедут в утро'


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


def test_no_reading_on_the_road_in_the_morning():
    """«Читать в дороге» убрано из утреннего блока 22.09.2026. Вечернее
    чтение в дороге остаётся — это другая задача."""
    sched = load_schedule()
    for day in ('monday', 'tuesday', 'wednesday', 'thursday', 'friday'):
        assert not any('Читать в дороге' in t for t in sched[day]['день']), day


def test_morning_split_survives_the_removal():
    """Граница утра в будни — English."""
    sched = load_schedule()
    for day in ('monday', 'tuesday', 'wednesday', 'thursday', 'friday'):
        morning, rest = split_day_tasks(sched[day]['день'])
        assert 'English в дороге' in morning[-1], day
        assert not rest, day


def test_saturday_split_is_unchanged():
    morning, rest = split_day_tasks(load_schedule()['saturday']['день'])
    assert morning[-1].startswith('Послушать молитву')


def test_no_words_lost_to_emoji_stripping():
    """При чистке эмодзи 👅 заменял слово «язык» — фраза стала «мат это
    мусор и гнева». Остальные эмодзи были украшением, этот — словом."""
    for day, sections in load_schedule().items():
        for name, tasks in sections.items():
            for t in tasks:
                assert 'мусор и гнева' not in t, f'{day}/{name}'


# Утро йоги по четвергам (08.10.2026): в четверг вместо зарядки — йога,
# остальные правила те же — первая задача утра и минимум в 5 минут.
EXERCISE = {'thursday': 'Йога'}


def test_exercise_opens_the_morning():
    """Зарядка — первая задача утра с 22.09.2026; в четверг — йога."""
    sched = load_schedule()
    for day in ('monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday'):
        assert sched[day]['день'][0].startswith(EXERCISE.get(day, 'Зарядка')), day


def test_no_invisible_characters():
    """Семейный эмодзи 👨‍👩‍👧‍👦 склеен невидимыми связками U+200D. При
    чистке фигуры ушли, а связки остались — строка «FamilyDay» начиналась
    с трёх невидимых символов."""
    for day, sections in load_schedule().items():
        for name, tasks in sections.items():
            for t in tasks:
                for c in ('\u200d', '\ufe0f', '\u200b'):
                    assert c not in t, f'{day}/{name}: {t!r}'
                assert t == t.strip(), f'{day}/{name}: пробел по краям'


def test_exercise_states_its_minimum():
    """Минимум прописан в самом пункте: иначе мозг сравнивает себя с
    «полной» зарядкой и не начинает вовсе. Пять минут засчитываются сразу."""
    for day in ('monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday'):
        first = load_schedule()[day]['день'][0]
        assert first.startswith(EXERCISE.get(day, 'Зарядка')) and '5 min' in first, day


def test_english_moved_to_the_commute():
    """English опирается на уже существующую привычку — дорогу — вместо
    отдельных двадцати минут дома, самого хрупкого пункта утра."""
    for day in ('monday', 'tuesday', 'wednesday', 'thursday', 'friday'):
        tasks = load_schedule()[day]['день']
        assert any('English в дороге' in t for t in tasks), day
        assert not any('YouTube' in t for t in tasks), day


# ── Дневной блок, пересборка 22.09.2026 ──────────────────────────────────

WEEKDAYS = ('monday', 'tuesday', 'wednesday', 'thursday', 'friday')


def _day_block(day):
    return split_day_tasks(load_schedule()[day]['день'])[1]



def test_goals_are_not_daily_anywhere():
    """Цели квартальные — ежедневные 10 минут на них избыточны."""
    for day, sections in load_schedule().items():
        assert not any('Проверь цели' in t for t in sections['день']), day


def test_signal_action_is_not_duplicated_in_schedule():
    """Пункт «Сделать действие дня из SIGNAL» дублировал само сообщение
    SIGNAL и снят вместе с дневным блоком (30.10.2026)."""
    for day, sections in load_schedule().items():
        assert not any('SIGNAL' in t and 'действие дня' in t
                       for t in sections['день']), day


def test_kids_investment_only_on_monday():
    """Перевод детям — раз в неделю. В остальные дни пункт либо висел
    неотмеченным, либо отмечался по инерции."""
    for day, sections in load_schedule().items():
        has = any('200 USD' in t for t in sections['день'])
        assert has == (day == 'monday'), day


def test_pullups_moved_from_schedule_to_signal():
    """Подтягивания — в SIGNAL по будням; пресс снят (30.10.2026)."""
    for day, sections in load_schedule().items():
        assert not any('одтягиван' in t or 'Пресс' in t for t in sections['день']), day




def test_english_item_links_to_the_channel():
    """Скрытая ссылка: кликабелен сам текст пункта, адрес не виден.
    Трекинговый параметр ?si= из ссылки-шеринга убран."""
    for day in WEEKDAYS:
        item = next(t for t in load_schedule()[day]['день'] if 'English в дороге' in t)
        assert '<a href="https://youtube.com/@englishbyjay.official">' in item, day
        assert '<a href="https://youtube.com/@soundbritish">' in item, day
        assert '?si=' not in item


def test_preview_stays_on_the_page_of_the_day(monkeypatch):
    """Telegram превьюшит первую ссылку в сообщении. English стоит выше
    страницы дня — без явного выбора вместо карточки страницы утром
    приходила бы карточка YouTube-канала."""
    import asyncio
    import json as _j
    import os
    from datetime import datetime
    from unittest.mock import patch
    os.environ.setdefault('TELEGRAM_TOKEN', 'test-token')
    os.environ.setdefault('TELEGRAM_CHAT_ID', 'test-chat')
    from notifier import PersonalScheduleNotifier
    from core import page_of_the_day, page_url

    n = PersonalScheduleNotifier()
    captured = {}

    class Resp:
        status = 200
        async def json(self): return {'result': {'message_id': 1}}
        async def text(self): return ''
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False

    class Sess:
        def post(self, url, json=None, **kw):
            captured.setdefault('payloads', []).append(json)
            return Resp()
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False

    class FixedDT(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 9, 23, 7, 30, tzinfo=tz)

    monkeypatch.setattr('notifier.aiohttp.ClientSession', lambda *a, **kw: Sess())
    with patch('notifier.datetime', FixedDT):
        msg = asyncio.run(n.format_morning_day_message(
            '23.09.2026', 'wednesday', n.schedule['wednesday'], block='morning'))
        asyncio.run(n.send_telegram_message(msg, add_progress_button=True,
                                            with_link_buttons=True))
    p = captured['payloads'][0]
    page = page_of_the_day(datetime(2026, 9, 23).date())
    assert p['link_preview_options']['url'] == page_url(page)
