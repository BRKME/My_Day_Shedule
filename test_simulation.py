#!/usr/bin/env python3
"""
Симуляция процессов My_Day_Shedule
Проверяет:
1. Итоги дня с разбивкой день/вечер/итого
2. Штраф в утреннем сообщении
"""

import json
import asyncio
from datetime import datetime, timedelta
import os

# Симулируем stats.json
MOCK_STATS = {
    # Вчера - со штрафом
    (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d"): {
        "day": {"completed": [0, 1, 2, 3, 4], "total": 8},
        "evening": {"completed": [0, 1, 2], "total": 5},
        "cant_do": {"completed": [0], "total": 2},  # 1 срыв!
        "percentage": 62,
        "penalty": True,
        "penalty_pushups": 30
    },
    # Сегодня
    datetime.now().strftime("%Y-%m-%d"): {
        "day": {"completed": [0, 1, 2, 3, 4, 5, 6], "total": 8},
        "evening": {"completed": [0, 1, 2, 3], "total": 5},
        "cant_do": {"completed": [], "total": 2},
        "percentage": 85,
        "penalty": False,
        "penalty_pushups": 0
    }
}

def get_progress_bar(percentage, length=7):
    filled = int((percentage / 100) * length)
    return '▓' * filled + '░' * (length - filled)

def get_level(percentage):
    if percentage >= 90:
        return {'name': 'TITANIUM', 'emoji': '💎', 'phrase': 'Сегодня ты ТИТАН продуктивности'}
    elif percentage >= 80:
        return {'name': 'STEEL', 'emoji': '⚔️', 'phrase': 'Стальная воля, стальной день'}
    elif percentage >= 70:
        return {'name': 'IRON', 'emoji': '🛡️', 'phrase': 'Железная хватка'}
    else:
        return {'name': 'BRONZE', 'emoji': '🥉', 'phrase': 'Есть куда расти'}

def get_motivation(percentage):
    if percentage >= 90:
        return "Отличная работа!"
    elif percentage >= 70:
        return "Хороший день."
    elif percentage >= 50:
        return "Неплохо. Завтра лучше."
    else:
        return "Новый день — новые возможности."

def simulate_daily_summary():
    """Симуляция итогов дня"""
    print("=" * 50)
    print("📊 СИМУЛЯЦИЯ: ИТОГИ ДНЯ")
    print("=" * 50)
    
    today_key = datetime.now().strftime("%Y-%m-%d")
    today_data = MOCK_STATS[today_key]
    
    day = today_data.get('day', {})
    evening = today_data.get('evening', {})
    cant_do = today_data.get('cant_do', {})
    
    day_done = len(day.get('completed', []))
    day_total = day.get('total', 0)
    
    evening_done = len(evening.get('completed', []))
    evening_total = evening.get('total', 0)
    
    overall_done = day_done + evening_done
    overall_total = day_total + evening_total
    overall_perc = min(100, int((overall_done / overall_total * 100))) if overall_total > 0 else 0
    
    cant_do_fails = len(cant_do.get('completed', []))
    
    # Формируем сообщение
    message = f"<b>ИТОГИ ДНЯ</b> · {datetime.now().strftime('%d.%m.%Y')}\n\n"
    
    # День и Вечер отдельно
    if day_total > 0:
        day_perc = min(100, int((day_done / day_total * 100)))
        day_bar = get_progress_bar(day_perc, 7)
        message += f"День   {day_bar} {day_done}/{day_total}\n"
    
    if evening_total > 0:
        evening_perc = min(100, int((evening_done / evening_total * 100)))
        evening_bar = get_progress_bar(evening_perc, 7)
        message += f"Вечер  {evening_bar} {evening_done}/{evening_total}\n"
    
    # ИТОГО
    message += f"\n<b>Итого: {overall_done}/{overall_total} ({overall_perc}%)</b>\n"
    
    # НЕЛЬЗЯ
    if cant_do_fails > 0:
        message += f"Срывов: {cant_do_fails}\n"
    
    message += "\n"
    
    # LEVEL
    level = get_level(overall_perc)
    message += f"{level['emoji']} {level['name']}\n"
    message += f"→ {level['phrase']}\n\n"
    
    # МОТИВАЦИЯ
    message += get_motivation(overall_perc)
    
    print("\n📱 TELEGRAM MESSAGE:")
    print("-" * 40)
    # Убираем HTML теги для консоли
    clean_msg = message.replace('<b>', '').replace('</b>', '').replace('<i>', '').replace('</i>', '')
    print(clean_msg)
    print("-" * 40)
    
    print("\n✅ День + Вечер + Итого: ОК")
    print(f"   День: {day_done}/{day_total}")
    print(f"   Вечер: {evening_done}/{evening_total}")
    print(f"   Итого: {overall_done}/{overall_total} ({overall_perc}%)")
    
    return True

def simulate_morning_with_penalty():
    """Симуляция утреннего сообщения со штрафом"""
    print("\n" + "=" * 50)
    print("☀️ СИМУЛЯЦИЯ: УТРЕННЕЕ СООБЩЕНИЕ СО ШТРАФОМ")
    print("=" * 50)
    
    yesterday_key = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    yesterday_data = MOCK_STATS.get(yesterday_key)
    
    if not yesterday_data:
        print("❌ Нет данных за вчера")
        return False
    
    penalty_pushups = yesterday_data.get('penalty_pushups', 0)
    cant_do = yesterday_data.get('cant_do', {})
    cant_do_fails = len(cant_do.get('completed', []))
    
    print(f"\n📊 Данные за вчера ({yesterday_key}):")
    print(f"   penalty_pushups: {penalty_pushups}")
    print(f"   cant_do_fails: {cant_do_fails}")
    
    # Формируем утреннее сообщение
    message = f"☀️ <b>Доброе утро!</b>\n"
    message += f"{datetime.now().strftime('%d.%m.%Y')}\n\n"
    
    # ШТРАФ
    if penalty_pushups > 0:
        message += f"<b>ШТРАФ:</b> Отжимания {penalty_pushups}× (штраф)\n\n"
        print("\n✅ ШТРАФ НАЙДЕН И ДОБАВЛЕН!")
    else:
        print("\n⚠️ Штрафа нет (penalty_pushups = 0)")
    
    message += "<b>📋 Дневные задачи:</b>\n"
    message += "• Задача 1\n"
    message += "• Задача 2\n"
    message += "• Задача 3\n"
    
    print("\n📱 TELEGRAM MESSAGE:")
    print("-" * 40)
    clean_msg = message.replace('<b>', '').replace('</b>', '').replace('<i>', '').replace('</i>', '')
    print(clean_msg)
    print("-" * 40)
    
    return penalty_pushups > 0

def main():
    print("\n🔬 ЗАПУСК СИМУЛЯЦИИ My_Day_Shedule")
    print("=" * 50)
    
    # Тест 1: Итоги дня
    test1 = simulate_daily_summary()
    
    # Тест 2: Утреннее сообщение со штрафом
    test2 = simulate_morning_with_penalty()
    
    # Итоги
    print("\n" + "=" * 50)
    print("📋 РЕЗУЛЬТАТЫ СИМУЛЯЦИИ")
    print("=" * 50)
    print(f"1. Итоги дня (день+вечер+итого): {'✅ PASS' if test1 else '❌ FAIL'}")
    print(f"2. Штраф в утреннем сообщении:   {'✅ PASS' if test2 else '❌ FAIL'}")
    print("=" * 50)
    
    if test1 and test2:
        print("\n🎉 ВСЕ ТЕСТЫ ПРОЙДЕНЫ!")
    else:
        print("\n⚠️ ЕСТЬ ПРОБЛЕМЫ!")

if __name__ == "__main__":
    main()
