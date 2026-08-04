# -*- coding: utf-8 -*-
"""Прополка message_states.

Файл состояний рос без ограничения: 64 записи = 383 КБ, и каждый запуск
целиком уходил в коммит (.git разросся до 17 МБ). Прогресс правится только
у свежих сообщений — старые состояния держать незачем.

Проверяем, что прополка встроена в оба пути записи (локальный файл и синк
с GitHub) и что она никогда не выкидывает актуальное состояние.
"""
import json
import os
import sys
import tempfile

import pytest

sys.path.insert(0, '.')

os.environ.setdefault('TELEGRAM_TOKEN', 'test-token')
os.environ.setdefault('TELEGRAM_CHAT_ID', 'test-chat')

from core import STATE_KEEP_LAST
from tracker_bot import TaskTrackerBot


@pytest.fixture
def bot(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    b = TaskTrackerBot()
    b.message_state_file = str(tmp_path / 'message_states.json')
    b.message_state = {}
    return b


def _state(n):
    return {'tasks': {'day': [f'task {n}']}, 'completed': {'day': []},
            'original_text': f'msg {n}', 'clean_original': f'msg {n}'}


def test_save_prunes_old_states_on_disk(bot):
    bot.message_state = {i: _state(i) for i in range(1, 201)}
    bot.save_message_states()

    with open(bot.message_state_file, encoding='utf-8') as f:
        saved = json.load(f)

    assert len(saved) == STATE_KEEP_LAST
    assert '200' in saved                      # свежее сохранено
    assert '1' not in saved                    # древнее выброшено


def test_save_keeps_newest_state_intact(bot):
    bot.message_state = {i: _state(i) for i in range(1, 201)}
    bot.save_message_states()

    with open(bot.message_state_file, encoding='utf-8') as f:
        saved = json.load(f)

    assert saved['200']['clean_original'] == 'msg 200'
    assert saved['200']['tasks']['day'] == ['task 200']


def test_save_prunes_in_memory_too(bot):
    """Иначе память процесса растёт, а на диск каждый раз пишется срез —
    расхождение между тем, что бот помнит, и тем, что переживёт рестарт."""
    bot.message_state = {i: _state(i) for i in range(1, 201)}
    bot.save_message_states()
    assert len(bot.message_state) == STATE_KEEP_LAST


def test_small_state_is_untouched(bot):
    bot.message_state = {7: _state(7), 8: _state(8)}
    bot.save_message_states()

    with open(bot.message_state_file, encoding='utf-8') as f:
        saved = json.load(f)

    assert set(saved) == {'7', '8'}


def test_file_stays_small_after_prune(bot):
    """Регресс-страховка на исходную проблему: 383 КБ в каждом коммите."""
    bot.message_state = {i: _state(i) for i in range(1, 501)}
    bot.save_message_states()
    assert os.path.getsize(bot.message_state_file) < 50_000


def test_startup_merge_prunes(bot):
    """Старт: локальные состояния из файла + догрузка с GitHub.

    Прополка только на записи оставляла процесс с полным набором в памяти
    до первого нажатия кнопки (лог 04.08: «Загружено 20 … Всего: 64»).
    """
    bot.message_state = {i: _state(i) for i in range(1, 65)}     # локальный файл
    github = {i: _state(i) for i in range(1, 21)}                # реплика в репо

    bot.merge_github_states(github)

    assert len(bot.message_state) == STATE_KEEP_LAST
    assert max(bot.message_state) == 64


def test_startup_merge_prefers_local_state():
    """Локальное состояние новее реплики — GitHub не должен его затирать."""
    os.environ.setdefault('TELEGRAM_TOKEN', 'test-token')
    b = TaskTrackerBot()
    b.message_state = {5: {'clean_original': 'локальное'}}
    b.merge_github_states({5: {'clean_original': 'из репо'}})
    assert b.message_state[5]['clean_original'] == 'локальное'


def test_startup_merge_adds_missing_from_github():
    b = TaskTrackerBot()
    b.message_state = {5: _state(5)}
    b.merge_github_states({6: _state(6)})
    assert set(b.message_state) == {5, 6}
