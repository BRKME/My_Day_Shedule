# -*- coding: utf-8 -*-
"""Сборка HTML из текста и разметки Telegram.

Трекер перерисовывал сообщение из message['text'] — это голый текст без
форматирования. После первой галочки пропадали курсив, жирный и ссылки.
Telegram присылает разметку отдельным списком entities; из него HTML
собирается обратно.

Главная ловушка: offset и length в entities — единицы UTF-16, а не
символы Python. Эмодзи вроде 🌅 занимает две единицы, и при подсчёте
символами все теги после него съезжали бы на одну позицию.
"""
import sys

sys.path.insert(0, '.')

from core import entities_to_html


def _utf16_len(s):
    return len(s.encode('utf-16-le')) // 2


def test_no_entities_is_just_escaped_text():
    assert entities_to_html('a < b & c', []) == 'a &lt; b &amp; c'


def test_bold_and_italic():
    text = 'План дня'
    ents = [{'type': 'bold', 'offset': 0, 'length': 4},
            {'type': 'italic', 'offset': 5, 'length': 3}]
    assert entities_to_html(text, ents) == '<b>План</b> <i>дня</i>'


def test_text_link_keeps_the_url():
    text = 'English в дороге'
    ents = [{'type': 'text_link', 'offset': 0, 'length': 16,
             'url': 'https://youtube.com/@englishbyjay.official'}]
    assert entities_to_html(text, ents) == (
        '<a href="https://youtube.com/@englishbyjay.official">English в дороге</a>')


def test_offsets_count_emoji_as_two_units():
    """🌅 — две единицы UTF-16. Считай мы символами Python, жирный начался
    бы на одну позицию левее и захватил бы пробел."""
    text = '🌅 Доброе утро'
    start = _utf16_len('🌅 ')
    ents = [{'type': 'bold', 'offset': start, 'length': _utf16_len('Доброе утро')}]
    assert entities_to_html(text, ents) == '🌅 <b>Доброе утро</b>'


def test_several_emoji_before_a_link():
    text = '📋 ☀️ задачи\n• English в дороге · аудио'
    start = _utf16_len('📋 ☀️ задачи\n• ')
    ents = [{'type': 'text_link', 'offset': start,
             'length': _utf16_len('English в дороге'), 'url': 'https://x.y'},
            {'type': 'italic', 'offset': start + _utf16_len('English в дороге · '),
             'length': _utf16_len('аудио')}]
    out = entities_to_html(text, ents)
    assert '• <a href="https://x.y">English в дороге</a> · <i>аудио</i>' in out


def test_nested_entities_close_in_the_right_order():
    text = 'жирный курсив'
    ents = [{'type': 'bold', 'offset': 0, 'length': 13},
            {'type': 'italic', 'offset': 7, 'length': 6}]
    assert entities_to_html(text, ents) == '<b>жирный <i>курсив</i></b>'


def test_text_inside_tags_is_escaped():
    text = 'a<b'
    ents = [{'type': 'bold', 'offset': 0, 'length': 3}]
    assert entities_to_html(text, ents) == '<b>a&lt;b</b>'


def test_url_in_link_is_escaped():
    text = 'x'
    ents = [{'type': 'text_link', 'offset': 0, 'length': 1,
             'url': 'https://a.b/?q=1&r="2"'}]
    assert entities_to_html(text, ents) == (
        '<a href="https://a.b/?q=1&amp;r=&quot;2&quot;">x</a>')


def test_unknown_entity_types_are_ignored():
    """Хэштеги, упоминания, голые URL Telegram размечает сам — тегами их
    оборачивать не нужно."""
    text = '#тег @user https://a.b'
    ents = [{'type': 'hashtag', 'offset': 0, 'length': 4},
            {'type': 'mention', 'offset': 5, 'length': 5},
            {'type': 'url', 'offset': 11, 'length': 11}]
    assert entities_to_html(text, ents) == text


def test_roundtrip_of_a_real_morning_message():
    """Сообщение, собранное нотификатором, после прохода через Telegram
    и обратно должно дать тот же HTML."""
    html = ('🌅 <b>Доброе утро! План на Среда 23.09.2026</b>\n\n'
            '<b>📋 Дневные задачи · утро:</b>\n'
            '• Зарядка — 5м · <i>засчитывается сразу</i>\n'
            '• <a href="https://youtube.com/@englishbyjay.official">English в дороге</a>'
            ' · <i>аудио</i>')
    text, ents = _telegram_parse(html)
    assert entities_to_html(text, ents) == html


def _telegram_parse(html):
    """Упрощённая имитация того, что делает Telegram с parse_mode=HTML:
    текст без тегов плюс entities в единицах UTF-16."""
    import re
    text, ents, stack, pos = '', [], [], 0
    for m in re.finditer(r'<(/?)(b|i|a)(?: href="([^"]*)")?>|([^<]+)', html):
        closing, tag, href, chunk = m.groups()
        if chunk:
            text += chunk
            pos += _utf16_len(chunk)
        elif not closing:
            stack.append((tag, pos, href))
        else:
            t, start, h = stack.pop()
            e = {'type': {'b': 'bold', 'i': 'italic', 'a': 'text_link'}[t],
                 'offset': start, 'length': pos - start}
            if h:
                e['url'] = h
            ents.append(e)
    return text, ents


# ── Встраивание в трекер ─────────────────────────────────────────────────

def _tracker():
    import os
    os.environ.setdefault('TELEGRAM_TOKEN', 'test-token')
    os.environ.setdefault('TELEGRAM_CHAT_ID', 'test-chat')
    from tracker_bot import TaskTrackerBot
    return TaskTrackerBot()


HTML = ('🌅 <b>Доброе утро! План на Среда 23.09.2026</b>\n\n'
        '<b>📋 Дневные задачи · утро:</b>\n'
        '• Зарядка — 5м · <i>засчитывается сразу</i>\n'
        '• <a href="https://youtube.com/@englishbyjay.official">English в дороге</a>'
        ' · <i>аудио</i>')


def test_tracker_reads_html_from_a_telegram_message():
    text, ents = _telegram_parse(HTML)
    b = _tracker()
    assert b.message_html({'text': text, 'entities': ents}) == HTML


def test_task_names_on_buttons_have_no_tags():
    """Кнопки чек-листа берут имя задачи целиком. С HTML на кнопке
    вылезло бы «<a href=...»."""
    tasks = _tracker().parse_tasks(HTML)
    assert 'English в дороге · аудио' in tasks['day']
    assert not any('<' in t for t in tasks['day'])


def test_link_and_italics_survive_a_progress_update():
    """Ради этого всё: после галочки ссылка и курсив на месте."""
    b = _tracker()
    tasks = b.parse_tasks(HTML)
    updated = b.update_original_message_with_progress(
        HTML, tasks, {'morning': [], 'day': [1], 'cant_do': [], 'evening': []})
    assert '<a href="https://youtube.com/@englishbyjay.official">' in updated
    assert '<i>засчитывается сразу</i>' in updated
