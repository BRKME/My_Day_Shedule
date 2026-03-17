# Superpowers Methodology

Методологии разработки из [obra/superpowers](https://github.com/obra/superpowers) (40K+ stars).

## Когда использовать

Перед любой серьёзной разработкой (новые фичи, баг-фиксы, рефакторинг) прочитай соответствующий skill.

## Workflow

```
1. BRAINSTORMING → уточни что строим
2. WRITING-PLANS → разбей на задачи 2-5 мин
3. EXECUTING-PLANS → выполняй с checkpoints
4. TDD → RED-GREEN-REFACTOR
5. VERIFICATION → убедись что работает
```

## Skills (читай перед работой)

| Skill | Когда использовать | Файл |
|-------|-------------------|------|
| **brainstorming** | Перед ЛЮБЫМ кодом — уточни требования | `skills/brainstorming/SKILL.md` |
| **writing-plans** | После дизайна — разбей на bite-sized задачи | `skills/writing-plans/SKILL.md` |
| **executing-plans** | Выполнение плана с batch checkpoints | `skills/executing-plans/SKILL.md` |
| **test-driven-development** | При написании кода — RED-GREEN-REFACTOR | `skills/test-driven-development/SKILL.md` |
| **systematic-debugging** | При багах — 4-фазный процесс | `skills/systematic-debugging/SKILL.md` |
| **verification-before-completion** | Перед "готово" — убедись что работает | `skills/verification-before-completion/SKILL.md` |

## Ключевые принципы

### HARD GATES (никогда не нарушай)

1. **Brainstorming → Design → Code** — никогда не пиши код без утверждённого дизайна
2. **TDD Iron Law** — никакого production кода без failing test сначала
3. **Verification** — не говори "готово" без проверки

### Anti-Patterns (избегай)

- "Это слишком просто для дизайна" → всё проходит через brainstorming
- "Напишу тесты потом" → тесты СНАЧАЛА, иначе удали код
- "Уже вручную проверил" → автотесты или не считается
- "Потратил X часов, жалко удалять" → sunk cost fallacy

### YAGNI + DRY + TDD

- **YAGNI** — You Aren't Gonna Need It, убирай лишнее
- **DRY** — Don't Repeat Yourself
- **TDD** — Test-Driven Development, тесты первые

## Quick Reference: TDD Cycle

```
RED    → напиши failing test
       → запусти, убедись что FAILS
GREEN  → напиши МИНИМАЛЬНЫЙ код для pass
       → запусти, убедись что PASSES
REFACTOR → почисти код
       → убедись что всё ещё PASSES
COMMIT → зафиксируй
```

## Quick Reference: Brainstorming Checklist

1. Изучи контекст проекта (файлы, docs, commits)
2. Задавай вопросы ПО ОДНОМУ
3. Предложи 2-3 подхода с trade-offs
4. Презентуй дизайн секциями, получи approval
5. Запиши spec в файл
6. Только после approval → writing-plans

## Quick Reference: Task Granularity

Каждый шаг = 2-5 минут:
- "Напиши failing test" — шаг
- "Запусти, убедись что fails" — шаг  
- "Напиши минимальный код" — шаг
- "Запусти, убедись что passes" — шаг
- "Commit" — шаг

## Источник

[github.com/obra/superpowers](https://github.com/obra/superpowers) — MIT License
