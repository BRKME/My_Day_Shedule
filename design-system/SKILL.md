# UI/UX Pro Max Skill

При создании любого UI (HTML страницы, лендинги, дашборды) — сначала прочитай этот файл.

## Данные

Данные находятся в `design-system/data/`:

| Файл | Описание |
|------|----------|
| `styles.csv` | 67 UI стилей с описаниями |
| `colors.csv` | 161 цветовая палитра по типам продуктов |
| `typography.csv` | 57 шрифтовых пар с Google Fonts |
| `ui-reasoning.csv` | Правила выбора стиля по типу продукта |
| `ux-guidelines.csv` | UX best practices |

## Процесс

1. **Определи тип продукта** (SaaS, финтех, wellness, portfolio...)
2. **Найди в ui-reasoning.csv** правила для этого типа
3. **Выбери стиль** из styles.csv
4. **Подбери палитру** из colors.csv
5. **Подбери шрифты** из typography.csv

## Anti-Patterns (НИКОГДА не делай)

### Цвета
- ❌ AI purple/pink gradients (#667eea → #764ba2) — выглядит как "сделано AI"
- ❌ Низкий контраст текста (< 4.5:1)
- ❌ Одинаковые цвета для разных проектов

### Шрифты
- ❌ Inter, Roboto, Arial, system fonts — скучно и банально
- ❌ Больше 2 шрифтов на странице
- ❌ Одинаковый размер для всего текста

### Иконки
- ❌ Emoji как иконки (🎨 🚀 ⚙️)
- ❌ Смешивание filled и outline стилей
- ❌ Разные размеры иконок без системы

### Лейаут
- ❌ Всё по центру без иерархии
- ❌ Одинаковые отступы везде
- ❌ Edge-to-edge текст на больших экранах

## Quick Reference

### Хорошие стили по типам

| Тип | Рекомендуемые стили |
|-----|---------------------|
| SaaS/Tech | Glassmorphism, Minimalism, Bento Grid |
| Fintech | Swiss Modernism, Dark Mode OLED |
| Wellness/Beauty | Soft UI, Organic Biophilic |
| Portfolio | Brutalism, Motion-Driven |
| E-commerce | Feature-Rich, Social Proof |
| Gaming | Cyberpunk, Retro-Futurism |

### Контраст (WCAG)
- Мелкий текст: минимум 4.5:1
- Крупный текст/иконки: минимум 3:1
- Всегда проверяй и light и dark mode

### Тайминги анимаций
- Micro-interactions: 150-300ms
- Page transitions: 300-500ms
- Exit быстрее чем enter

### Touch targets
- iOS: минимум 44×44pt
- Android: минимум 48×48dp

## Источник

Данные из [UI UX Pro Max](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) (43K+ stars).
