# -*- coding: utf-8 -*-
"""Архив заданий программы «365 дней».

Отклонённые задания не удаляются, а переносятся в отдельный файл: видно,
что выкинуто и когда, и вернуть можно одной строкой.
"""
import json
import sys

sys.path.insert(0, '.')

from core import DAILY_TASKS


def _archive():
    return json.load(open('data/daily_tasks_archive.json', encoding='utf-8'))


def test_archived_task_is_out_of_rotation():
    assert not any('лучшая цена' in t['task'] for t in DAILY_TASKS)


def test_archived_task_is_kept_with_a_date():
    hit = [t for t in _archive() if 'лучшая цена' in t['task']]
    assert hit and hit[0].get('archived')


def test_nothing_is_both_active_and_archived():
    active = {t['task'] for t in DAILY_TASKS}
    assert not active & {t['task'] for t in _archive()}
