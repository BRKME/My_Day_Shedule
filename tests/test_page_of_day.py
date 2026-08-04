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


def test_same_day_gives_same_page():
    """Текст сообщения и кнопка собираются разными вызовами — если выбор
    не стабилен внутри дня, в тексте будет Талеб, а на кнопке молитва."""
    d = date(2026, 8, 5)
    assert page_of_the_day(d) == page_of_the_day(d)


def test_never_repeats_two_mornings_running():
    """Проверяем полгода подряд, включая швы между колодами."""
    d = date(2026, 8, 5)
    for i in range(180):
        today = page_of_the_day(d + timedelta(days=i))
        tomorrow = page_of_the_day(d + timedelta(days=i + 1))
        assert today != tomorrow, f'повтор на {d + timedelta(days=i)}'


def test_each_deck_covers_all_pages():
    """Колода — пять дней подряд от границы цикла: все пять страниц."""
    first = date(2026, 8, 5)
    first += timedelta(days=(-first.toordinal()) % 5)   # выравниваем на колоду
    for c in range(30):
        deck = [page_of_the_day(first + timedelta(days=c * 5 + i))['key']
                for i in range(5)]
        assert len(set(deck)) == 5, f'колода {c} с повтором: {deck}'


def test_no_page_starves_over_a_month():
    """За 30 дней каждая страница должна выпасть хотя бы четырежды."""
    d = date(2026, 8, 5)
    seen = [page_of_the_day(d + timedelta(days=i))['key'] for i in range(30)]
    for p in PAGES:
        assert seen.count(p['key']) >= 4, f'{p["key"]}: {seen.count(p["key"])}'


def test_order_is_not_a_fixed_rotation():
    """Иначе это не рандом, а расписание: понедельник всегда молитва."""
    start = date(2026, 8, 5)
    cycles = [[page_of_the_day(start + timedelta(days=c * 5 + i))['key']
               for i in range(5)] for c in range(12)]
    assert len(set(map(tuple, cycles))) > 1


def test_spans_month_and_year_boundaries():
    for d in (date(2026, 8, 31), date(2026, 12, 31), date(2027, 1, 1)):
        assert page_of_the_day(d) in PAGES


def test_repeats_are_at_least_three_days_apart():
    """«Стоицизм в четверг и в субботу» читается как поломка, даже если
    формально это честный рандом. Проверяем полгода, включая швы колод."""
    d = date(2026, 8, 5)
    keys = [page_of_the_day(d + timedelta(days=i))['key'] for i in range(180)]
    for i in range(len(keys) - 2):
        window = keys[i:i + 3]
        assert len(set(window)) == 3, f'близкий повтор на дне {i}: {window}'
