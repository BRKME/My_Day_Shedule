# -*- coding: utf-8 -*-
"""Общее ядро My_Day_Shedule.

Здесь живёт логика, которую используют ОБА процесса:
  • notifier.py    — GitHub Actions, шлёт сообщения по расписанию;
  • tracker_bot.py — VPS systemd, обрабатывает нажатия и копит стату.

Раньше эта логика была скопирована в оба файла и разъезжалась: фикс
`load_stats_from_github` (16.07) пришлось вносить дважды, а нормализация
задач существовала только в notifier — трекер парсил уже отрендеренный
текст. Один источник истины дешевле, чем синхронизация двух копий.

Модуль намеренно без внешних зависимостей (только stdlib) — его импортируют
и раннер GitHub Actions, и systemd-сервис на VPS.
"""
import json
import os
import re

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')

EVENING_END = "23:30"          # конец вечернего окна для бюджета времени

# Сколько состояний сообщений храним.
# Telegram запрещает боту редактировать сообщение старше 48 часов — состояние
# древнее этого срока физически бесполезно: нажать чекбокс уже нельзя.
# 4 сообщения в день (утро/день/вечер/подтягивания) × 48 ч = 8 живых состояний,
# 20 — запас на пропущенные дни и отпуск. Всё остальное было мёртвым весом,
# который каждый запуск целиком уезжал в коммит.
STATE_KEEP_LAST = 20

# Приоритет границ утро/день: будни — дорога, суббота — «Мозг» (11.07.2026)
MORNING_BOUNDARIES = ("Читать 📖 в дороге", "Включи 🧠 Мозг")

_EMOJI_RE = re.compile(
    '(?:[\U0001F1E6-\U0001F1FF]{2}'          # флаги — пары regional indicators
    '|[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF]\uFE0F?'
    '[\U0001F3FB-\U0001F3FF]?)')
_MIN_RE = re.compile(r'(\d+)\s*(?:min|мин|м)\b', re.IGNORECASE)


# ── Текст задач ──────────────────────────────────────────────────────────

def _lower_cyr(text: str) -> str:
    """Опустить первую букву, только если она кириллическая: 'Есть'→'есть',
    но 'Project' остаётся — латинские имена собственные не трогаем."""
    if text and 'А' <= text[0] <= 'я' or text[:1] in ('Ё',):
        return text[0].lower() + text[1:]
    return text


def task_minutes(task: str) -> int:
    """Минуты из строки задачи в любом из форматов: '(30 min ...)', '— 30м'."""
    m = _MIN_RE.search(task)
    return int(m.group(1)) if m else 0


def normalize_task(task: str) -> str:
    """Единый формат строки: '{эмодзи} {Текст} — {N}м · <i>{мотивация}</i>'.

    Принимает исторический формат ('Читать 📖 в дороге <i>(30 min это
    Спорт для мозга)</i>') и не трогает уже нормальные строки. Данные
    расписания остаются как есть — вся косметика на рендере.
    """
    src = task.strip()
    # 1) вынуть <i>(...)</i>-хвост
    minutes, motivation = 0, ''
    m = re.search(r'<i>\s*\(?(.*?)\)?\s*</i>\s*$', src)
    if m:
        inner = m.group(1).strip()
        src = src[:m.start()].strip()
        # Хвост уже нормализованной строки отделён ' · ' — снимаем разделитель,
        # иначе повторный рендер даёт '— 30м · · <i>…</i>'. Идемпотентность
        # обязательна: текст задачи возвращается из stats.json и сообщений
        # Telegram уже отрендеренным и проходит нормализацию второй раз.
        src = src.rstrip(' ·')
        mm = _MIN_RE.search(inner)
        if mm:
            minutes = int(mm.group(1))
            inner = (inner[:mm.start()] + inner[mm.end():]).strip()
            inner = re.sub(r'^(это|—|-|·)\s*', '', inner, flags=re.IGNORECASE)
        motivation = inner.strip(' .()') + ('.' if inner.rstrip().endswith('.') else '')
        motivation = motivation.strip()
    # 2) эмодзи в начало строки
    em = _EMOJI_RE.search(src)
    if em and em.start() > 0:
        emoji = em.group(0)
        before = src[:em.start()].strip()
        after = src[em.end():].strip()
        text = (before + (' ' + _lower_cyr(after) if after else '')).strip()
        src = f'{emoji} {text}'
    # 3) собрать
    out = src
    if minutes:
        out += f' — {minutes}м'
    if motivation:
        out += f' · <i>{_lower_cyr(motivation)}</i>'
    return out


def fmt_dur(minutes: int) -> str:
    h, m = divmod(max(0, int(minutes)), 60)
    if h and m:
        return f'{h}ч {m}м'
    return f'{h}ч' if h else f'{m}м'


def budget_header(tasks, now, end_hhmm: str = EVENING_END) -> str:
    """Строка бюджета времени: план vs окно до конца вечера.

    План, который не влезает, тренирует привычку его не выполнять —
    перегруз показываем сразу, с кандидатом на перенос (самая длинная
    задача). Строка начинается с '⏱' (не '📊' и не '•' — см. инварианты).
    """
    total = sum(task_minutes(t) for t in tasks)
    eh, em = map(int, end_hhmm.split(':'))
    window = (eh * 60 + em) - (now.hour * 60 + now.minute)
    window = max(0, window)
    head = f'⏱ В плане {fmt_dur(total)} · окно до {end_hhmm} ~{fmt_dur(window)}'
    over = total - window
    if over > 0:
        head += f' · ⚠️ перегруз {fmt_dur(over)}'
        longest = max(tasks, key=task_minutes, default=None)
        if longest and task_minutes(longest) > 0:
            name = re.sub(r'\s*—\s*\d+м.*$', '', longest).strip()
            head += (f'\n↪️ кандидат на перенос: {name} '
                     f'({task_minutes(longest)}м)')
    else:
        head += f' · запас {fmt_dur(-over)}'
    return head


# ── Разбиение дневного блока ─────────────────────────────────────────────

def split_day_tasks(tasks):
    """Сплит дневного списка на утренний и дневной блок (04.07.2026).

    Границы проверяются по приоритету (11.07.2026):
    будни — «Читать в дороге», суббота (дороги нет) — «Включи Мозг».
    Утро — всё до границы ВКЛЮЧИТЕЛЬНО, день — остаток.
    Ни одного маркера нет — fail-safe: всё уходит в утро, дневной
    блок пуст (лучше одно полное сообщение, чем потерянные задачи)."""
    for marker in MORNING_BOUNDARIES:
        for i, t in enumerate(tasks):
            if marker in t:
                return tasks[:i + 1], tasks[i + 1:]
    return tasks, []


# ── Уровни ───────────────────────────────────────────────────────────────
# Порог — нижняя граница включительно. Таблица вместо лестницы if/elif:
# уровни правятся как данные и проверяются тестом на монотонность.
LEVELS = (
    {'min': 0,   'name': 'Хаос',               'emoji': '😴', 'rank': 1,
     'phrase': 'Начни с одной задачи',   'bar': '🟩⬜⬜⬜⬜⬜⬜'},
    {'min': 30,  'name': 'Режим',              'emoji': '🚶', 'rank': 2,
     'phrase': 'Ты в движении',          'bar': '🟩🟩⬜⬜⬜⬜⬜'},
    {'min': 50,  'name': 'Система',            'emoji': '⚙',  'rank': 3,
     'phrase': 'Механизм работает',      'bar': '🟩🟩🟩⬜⬜⬜⬜'},
    {'min': 70,  'name': 'Дисциплина',         'emoji': '🎯', 'rank': 4,
     'phrase': 'Ты управляешь днём',     'bar': '🟩🟩🟩🟩⬜⬜⬜'},
    {'min': 85,  'name': 'Железная воля',      'emoji': '🦾', 'rank': 5,
     'phrase': 'Тебя не свернуть',       'bar': '🟩🟩🟩🟩🟩⬜⬜'},
    {'min': 95,  'name': 'Несгибаемый',        'emoji': '💎', 'rank': 6,
     'phrase': 'Почти безупречно',       'bar': '🟩🟩🟩🟩🟩🟩⬜'},
    {'min': 100, 'name': 'Абсолютный контроль', 'emoji': '👑', 'rank': 7,
     'phrase': 'Идеальный день. Ноль слитого.', 'bar': '🟩🟩🟩🟩🟩🟩🟩'},
)


def get_level(percentage) -> dict:
    """Уровень по проценту выполнения — RPG-стиль.

    Возвращает копию, чтобы вызывающий код не мог случайно испортить
    таблицу (dict из LEVELS раньше уходил наружу и клался в стату)."""
    chosen = LEVELS[0]
    for level in LEVELS:
        if percentage >= level['min']:
            chosen = level
    return {k: v for k, v in chosen.items() if k != 'min'}


# ── Статистика ───────────────────────────────────────────────────────────

def merge_stats(github_stats: dict, local_stats: dict) -> dict:
    """Слияние статистики: объединение дней, при конфликте локальный
    день побеждает. Локальный stats.json на VPS — источник истины
    (бот пишет в него каждое действие); GitHub — реплика, которая может
    отставать (16.07: синк умер с отзывом PAT, репо застряло на 13.07,
    и старая загрузка при рестарте откатила бы прогресс)."""
    return {**github_stats, **local_stats}


def prune_message_states(states: dict, keep_last: int = STATE_KEEP_LAST) -> dict:
    """Оставить только `keep_last` самых свежих состояний сообщений.

    message_id в Telegram монотонно растёт, поэтому «свежее» = больше id.
    Ключи могут быть и int (локально), и str (после round-trip через JSON
    и GitHub) — сортируем численно, иначе '9' окажется больше '100' и
    прополка выкинет как раз актуальные состояния.

    Без прополки файл рос бесконечно: 64 записи = 383 КБ, и каждый запуск
    целиком уезжал в коммит (.git разросся до 17 МБ).
    """
    if len(states) <= keep_last:
        return states
    keys = sorted(states, key=lambda k: int(k), reverse=True)[:keep_last]
    return {k: states[k] for k in keys}


# ── Данные расписания ────────────────────────────────────────────────────

def _load_json(name: str):
    with open(os.path.join(DATA_DIR, name), 'r', encoding='utf-8') as f:
        return json.load(f)


def load_schedule() -> dict:
    """Недельное расписание задач из data/schedule.json.

    Данные отделены от кода: правка расписания — правка JSON, без риска
    задеть логику рендера и без диффа в 1900-строчном модуле."""
    return _load_json('schedule.json')


def load_kids_schedule() -> dict:
    """Расписание занятий детей из data/kids_schedule.json."""
    return _load_json('kids_schedule.json')


# ── GitHub Contents API ──────────────────────────────────────────────────
# Транспорт у процессов разный (notifier — requests, tracker_bot — aiohttp),
# общее здесь только формирование URL и кодирование содержимого.

GITHUB_REPO = "BRKME/My_Day_Shedule"


def github_contents_url(path: str, repo: str = GITHUB_REPO) -> str:
    return f"https://api.github.com/repos/{repo}/contents/{path}"


def github_headers(token: str) -> dict:
    return {"Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json"}
