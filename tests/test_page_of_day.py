# -*- coding: utf-8 -*-
"""Страница дня.

Раньше утреннее сообщение несло все пять ссылок сразу — простыня, которую
перестаёшь замечать. Теперь одна страница в день.

Порядок случайный, но без повторов внутри цикла: за каждые пять дней
показываются все пять страниц, и только потом колода тасуется заново.
Чистый random.choice дал бы Талеба три утра подряд и молчал бы про
молитву неделю.
"""
import sys
from datetime import date, timedelta

sys.path.insert(0, '.')

from core import PAGES, page_of_the_day, page_url


def test_five_pages_registered():
    assert len(PAGES) == 5
    keys = {p['key'] for p in PAGES}
    assert keys == {'prayer', 'career', 'taleb', 'kohelet', 'stoic'}


def test_every_page_has_emoji_title_and_file():
    for p in PAGES:
        assert p['emoji'] and p['title'] and p['file'].endswith('.html')


def test_url_points_to_pages_site():
    url = page_url(PAGES[0])
    assert url.startswith('https://brkme.github.io/My_Day_Shedule/')
    assert url.endswith('.html')


def _weekday_keys(start, count):
    """Ключи страниц по будням подряд (выходные пропускаем)."""
    keys, d = [], start
    while len(keys) < count:
        p = page_of_the_day(d)
        if p:
            keys.append(p['key'])
        d += timedelta(days=1)
    return keys


def test_same_day_gives_same_page():
    """Текст сообщения и кнопка собираются разными вызовами — если выбор
    не стабилен внутри дня, в тексте будет Талеб, а на кнопке молитва."""
    d = date(2026, 8, 5)                       # среда
    assert page_of_the_day(d) == page_of_the_day(d)


def test_never_repeats_two_mornings_running():
    """Проверяем полгода будней подряд, включая швы между колодами."""
    keys = _weekday_keys(date(2026, 8, 5), 130)
    for a, b in zip(keys, keys[1:]):
        assert a != b, f'подряд: {a}'


def test_every_page_appears_within_two_weeks():
    """Пропуск выходных рвёт колоду, но ни одна страница не должна
    выпадать из оборота надолго."""
    for offset in range(0, 120, 10):
        window = set(_weekday_keys(date(2026, 8, 5) + timedelta(days=offset), 10))
        assert len(window) == 5, f'со сдвигом {offset} показаны только {window}'


def test_no_page_starves_over_a_month():
    """За 20 будней каждая страница должна выпасть хотя бы трижды."""
    seen = _weekday_keys(date(2026, 8, 5), 20)
    for p in PAGES:
        assert seen.count(p['key']) >= 3, f'{p["key"]}: {seen.count(p["key"])}'


def test_order_is_not_a_fixed_rotation():
    """Иначе это не рандом, а расписание: понедельник всегда молитва."""
    start = date(2026, 8, 5)
    keys = _weekday_keys(start, 60)
    cycles = [tuple(keys[i:i + 5]) for i in range(0, 60, 5)]
    assert len(set(cycles)) > 1


def test_spans_month_and_year_boundaries():
    for d in (date(2026, 8, 31), date(2026, 12, 31), date(2027, 1, 1)):
        assert page_of_the_day(d) in PAGES        # все три — будни


def test_repeats_are_at_least_three_days_apart():
    """«Стоицизм в четверг и в субботу» читается как поломка, даже если
    формально это честный рандом. Проверяем полгода, включая швы колод."""
    keys = _weekday_keys(date(2026, 8, 5), 130)
    for i in range(len(keys) - 2):
        window = keys[i:i + 3]
        assert len(set(window)) == 3, f'близкий повтор на будне {i}: {window}'


def test_no_page_on_weekend():
    """Суббота и воскресенье — без страницы: выходные и так заняты семьёй,
    лишняя ссылка в утреннем сообщении там только шумит."""
    assert page_of_the_day(date(2026, 8, 8)) is None    # суббота
    assert page_of_the_day(date(2026, 8, 9)) is None    # воскресенье


def test_weekdays_still_get_a_page():
    for d in (date(2026, 8, 10), date(2026, 8, 11), date(2026, 8, 12),
              date(2026, 8, 13), date(2026, 8, 14)):
        assert page_of_the_day(d) in PAGES


def test_weekday_only_rotation_stays_balanced():
    """Выпадение выходных не должно перекосить показы: страница, которая
    систематически попадает на субботу, исчезла бы совсем."""
    d = date(2026, 8, 3)
    seen = [p['key'] for p in
            (page_of_the_day(d + timedelta(days=i)) for i in range(364))
            if p]
    counts = [seen.count(p['key']) for p in PAGES]
    assert min(counts) >= max(counts) * 0.8, dict(zip(
        [p['key'] for p in PAGES], counts))


# ── Интеграция с сообщением ──────────────────────────────────────────────

def test_morning_message_has_no_link_on_weekend():
    """В выходные page_of_the_day возвращает None — сообщение и клавиатура
    должны это пережить, а не упасть на обращении к полю словаря."""
    import asyncio
    from datetime import datetime
    from unittest.mock import patch
    import os
    os.environ.setdefault('TELEGRAM_TOKEN', 'test-token')
    os.environ.setdefault('TELEGRAM_CHAT_ID', 'test-chat')
    from notifier import PersonalScheduleNotifier

    n = PersonalScheduleNotifier()

    class SaturdayDT(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 8, 8, 7, 30)      # суббота

    with patch('notifier.datetime', SaturdayDT):
        msg = asyncio.run(n.format_morning_day_message(
            '08.08.2026', 'saturday', n.schedule['saturday'], block='full'))
        keyboard = n.create_message_keyboard()

    assert '.html' not in msg
    urls = [b for row in keyboard['inline_keyboard'] for b in row if 'url' in b]
    assert urls == []


def test_morning_message_has_link_on_weekday():
    import asyncio
    from datetime import datetime
    from unittest.mock import patch
    from notifier import PersonalScheduleNotifier

    n = PersonalScheduleNotifier()

    class WednesdayDT(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 8, 5, 7, 30)

    with patch('notifier.datetime', WednesdayDT):
        msg = asyncio.run(n.format_morning_day_message(
            '05.08.2026', 'wednesday', n.schedule['wednesday'], block='full'))
        keyboard = n.create_message_keyboard()

    urls = [b['url'] for row in keyboard['inline_keyboard'] for b in row
            if 'url' in b]
    assert len(urls) == 1
    assert urls[0] in msg


# ── Перерисовка сообщения трекером ───────────────────────────────────────

def _tracker():
    import os
    os.environ.setdefault('TELEGRAM_TOKEN', 'test-token')
    os.environ.setdefault('TELEGRAM_CHAT_ID', 'test-chat')
    from tracker_bot import TaskTrackerBot
    return TaskTrackerBot()


def test_redraw_keeps_single_page_link():
    """Инцидент 05.08.2026: утром пришла одна ссылка, но после первого
    нажатия трекер перерисовывал клавиатуру со своим захардкоженным
    списком — возвращались все прежние страницы, кроме Стоицизма."""
    b = _tracker()
    header = '🌅 <b>Доброе утро! План на Среда 05.08.2026</b>\n\n• задача'
    kb = b._redraw_keyboard(header)
    urls = [x['url'] for row in kb['inline_keyboard'] for x in row if 'url' in x]
    assert len(urls) == 1, f'ожидалась одна ссылка, пришло {len(urls)}: {urls}'


def test_redraw_link_matches_the_message_date():
    """Кнопка должна вести на страницу того дня, к которому относится
    сообщение, а не на сегодняшнюю: вечером правишь утреннее сообщение —
    ссылка не должна подмениться."""
    b = _tracker()
    for d in (date(2026, 8, 5), date(2026, 8, 6), date(2026, 8, 7)):
        header = f'🌅 <b>Доброе утро! План на Среда {d.strftime("%d.%m.%Y")}</b>'
        kb = b._redraw_keyboard(header)
        urls = [x['url'] for row in kb['inline_keyboard'] for x in row
                if 'url' in x]
        assert urls == [page_url(page_of_the_day(d))], d


def test_redraw_has_no_link_on_weekend():
    b = _tracker()
    header = '🌅 <b>Доброе утро! План на Суббота 08.08.2026</b>'
    kb = b._redraw_keyboard(header)
    assert not [x for row in kb['inline_keyboard'] for x in row if 'url' in x]


def test_redraw_day_and_evening_have_no_links():
    """Ссылки только в утреннем сообщении — правило от 09.07.2026."""
    b = _tracker()
    for header in ('☀️ <b>Дневной блок · Среда 05.08.2026</b>',
                   '🌙 <b>Вечерний план на Среда 05.08.2026</b>'):
        kb = b._redraw_keyboard(header)
        assert not [x for row in kb['inline_keyboard'] for x in row
                    if 'url' in x], header
