# -*- coding: utf-8 -*-
"""Нотификатор не затирает чужие данные в stats.json.

Аудит 22.09.2026, находка №2. Нотификатор в Actions заливал в GitHub
весь stats.json — снимок, сделанный при старте запуска. Галочка,
отмеченная, пока шёл запуск, в GitHub пропадала.

Теперь он берёт свежее содержимое из того же ответа, где спрашивает
версию файла, и меняет в нём только свои служебные поля за сегодня.
"""
import base64
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, '.')

os.environ.setdefault('TELEGRAM_TOKEN', 'test-token')
os.environ.setdefault('TELEGRAM_CHAT_ID', 'test-chat')
os.environ['GITHUB_TOKEN'] = 'test-gh'


class _Resp:
    def __init__(self, status, payload=None):
        self.status_code = status
        self._payload = payload or {}

    def json(self):
        return self._payload


def _run(monkeypatch, tmp_path, remote, local, message):
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'stats.json').write_text(json.dumps(local), encoding='utf-8')
    puts = []

    def fake_get(url, headers=None, timeout=None):
        body = base64.b64encode(json.dumps(remote).encode()).decode()
        return _Resp(200, {'sha': 'abc', 'content': body})

    def fake_put(url, headers=None, json=None, timeout=None):
        puts.append(json)
        return _Resp(200)

    import notifier
    monkeypatch.setattr(notifier.requests, 'get', fake_get)
    monkeypatch.setattr(notifier.requests, 'put', fake_put)
    n = notifier.PersonalScheduleNotifier()
    n.save_today_tasks(message)
    assert puts, 'в GitHub ничего не ушло'
    sent = puts[-1]
    return sent, json.loads(base64.b64decode(sent['content']).decode())


def _morning(n_date='23.09.2026'):
    import asyncio
    from notifier import PersonalScheduleNotifier
    n = PersonalScheduleNotifier()
    return asyncio.run(n.format_morning_day_message(
        n_date, 'wednesday', n.schedule['wednesday'], block='morning'))


def test_tracker_tap_on_github_survives(monkeypatch, tmp_path):
    today = datetime.now().strftime('%Y-%m-%d')
    remote = {today: {'day': {'completed': [0], 'total': 7}, 'percentage': 14},
              'weight': {today: 91.0}}
    local = {}                                   # снимок Actions: галочки нет
    sent, content = _run(monkeypatch, tmp_path, remote, local, _morning())
    assert content[today]['day']['completed'] == [0]
    assert content['weight'] == {today: 91.0}
    assert '_tasks' in content[today]
    assert sent['sha'] == 'abc'


def test_other_days_on_github_are_untouched(monkeypatch, tmp_path):
    remote = {'2026-09-01': {'percentage': 70}}
    local = {'2026-08-01': {'percentage': 10}}   # старый снимок
    sent, content = _run(monkeypatch, tmp_path, remote, local, _morning())
    assert content['2026-09-01'] == {'percentage': 70}
    assert '2026-08-01' not in content
