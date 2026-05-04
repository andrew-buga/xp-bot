# 🔧 SETUP GUIDE — Налаштування системи REQUEST PIPELINE

## Швидкий старт (5 хвилин)

### Крок 1: Встань рuff (для лінтингу)
```bash
pip install ruff
```

### Крок 2: Перевір що працює
```bash
python request_processor.py validate
```

Повинен вивести:
```
✓ bot.py
✓ database.py
✓ config.py
✓ Синтаксис OK для N файлів
✓ Лінтинг OK
✓ VALIDATION PASSED
```

### Крок 3: Запускай перед коміту
```bash
python pre_commit_checks.py
```

---

## 📚 Як користуватися

### Сценарій 1️⃣: Пишеш новий скрипт для аналізи

```bash
# 1. Пишеш analyze_user_activity.py
# 2. Перевіряєш синтаксис + лінтинг
python request_processor.py validate

# 3. Якщо помилки — поправляєш
# 4. Пишеш тести (test_analyze_user_activity.py)

# 5. Запускаєш тести
python request_processor.py test

# 6. Якщо всі зелені — готово!
```

### Сценарій 2️⃣: Фіх критичного баги в bot.py

```bash
# 1. Редагуєш bot.py
# 2. Быстра перевірка:
python request_processor.py validate

# 3. Запускаєш тести:
python request_processor.py test

# 4. Якщо ОК — деплой:
python request_processor.py deploy
```

### Сценарій 3️⃣: Перед кожним Git Commit

```bash
# ОБОВ'ЯЗКОВО запусти:
python pre_commit_checks.py

# Якщо вывів ✅ — можна коммітити
# Якщо красного ❌ — поправ помилки в коді
```

### Сценарій 4️⃣: Перед деплоєм на сервер

```bash
# Повна перевірка (усі 3 стадії):
python request_processor.py check-pre-commit

# Якщо ВСЕ зелено ✅:
python request_processor.py deploy
```

---

## 🎯 Типові помилки та рішення

### Помилка: "Ruff not installed"
```bash
pip install ruff
python request_processor.py validate
```

### Помилка: "SyntaxError in bot.py"
```
Check the error message carefully
Fix the syntax
python request_processor.py validate  # перевір знову
```

### Помилка: "Tests failed"
```
1. Дивись в яких тестах помилки
2. Поправ логіку в коді
3. python request_processor.py test  # запусти знову
```

### Помилка: "Database backup failed"
```
1. Перевір що bot_data.db існує
2. Перевір права доступу (chmod)
3. Мав місце на диску?
```

---

## 🔗 VS Code Integration (опціонально)

Якщо хочеш автоматичних перевірок в VS Code:

### 1. Встань Pylance
- `Ctrl+Shift+X` → пошук "Pylance"
- Встань

### 2. Встань Ruff extension
- `Ctrl+Shift+X` → пошук "Ruff"
- Встань та вибери "Ruff" (не "Ruff LSP")

### 3. Додай до `.vscode/settings.json`:
```json
{
  "[python]": {
    "editor.defaultFormatter": "charliermarsh.ruff",
    "editor.formatOnSave": true,
    "editor.codeActionsOnSave": {
      "source.organizeImports": "explicit"
    }
  },
  "ruff.lint.select": ["F", "E", "W"],
  "ruff.lint.ignore": ["E501"]
}
```

Тепер VS Code буде показувати помилки на льоту, як у тебе в IDE.

---

## 📊 Контроль якості на різних рівнях

```
┌─────────────────────────────────────────┐
│   LEVEL 1: VS CODE (на льоту)          │
│   Pylance + Ruff                        │
│   → помилки червоне підкреслення        │
└─────────────────────────────────────────┘
            ↓
┌─────────────────────────────────────────┐
│   LEVEL 2: PRE-COMMIT (перед git)       │
│   python pre_commit_checks.py            │
│   → синтаксис + лінтинг за 5 сек        │
└─────────────────────────────────────────┘
            ↓
┌─────────────────────────────────────────┐
│   LEVEL 3: PIPELINE (перед деплоєм)     │
│   python request_processor.py            │
│   → VALIDATE → TEST → DEPLOY             │
│   → усі тести повинні пройти             │
└─────────────────────────────────────────┘
            ↓
┌─────────────────────────────────────────┐
│   PRODUCTION: Live система               │
│   Логи моніторяться (journalctl)         │
│   Щоодини: backup БД                    │
└─────────────────────────────────────────┘
```

---

## 🚀 Автоматичні Git Hooks (Advanced)

Якщо хочеш що систем замет АВТОМАТИЧНО перевіряв код перед комітом:

### 1. Створ `.git/hooks/pre-commit`:
```bash
#!/bin/sh
python pre_commit_checks.py
exit $?
```

### 2. Дай права:
```bash
chmod +x .git/hooks/pre-commit
```

Тепер при `git commit` буде автоматично:
- Синтаксис + лінтинг перевірка
- Якщо помилки → commit скасовується
- Якщо ОК → commit пройде

---

## 📝 Приклад повного workflow

```bash
# День 1: Пишеш новий скрипт
$ nano analyze_xp_trends.py

# Перевіряєш синтаксис
$ python request_processor.py validate
✓ Синтаксис OK
✓ Лінтинг OK
✓ VALIDATION PASSED

# Пишеш тести
$ nano test_analyze_xp_trends.py

# Запускаєш тести
$ python request_processor.py test
✓ test_analyze_xp_trends.py passed
✓ Database integrity OK
✓ TESTING PASSED

# Готово для коміту! Спочатку перевіка:
$ python pre_commit_checks.py
✓ ВСІ ПЕРЕВІРКИ ПРОЙШЛИ — можна коммітити!

# Коміт:
$ git add -A
$ git commit -m "feat: add XP trends analysis"

# На машинах відпустити: перевірка + деплой
$ python request_processor.py deploy
✓ BACKUP created
✓ Git push successful
✓ Service restarted
✓ DEPLOYMENT COMPLETE
```

---

## ⚠️ ВАЖНІ ПРАВИЛА

1. **НИКОГДА не коміть без перевірки**
   ```bash
   python pre_commit_checks.py  # ОБОВ'ЯЗКОВО!
   ```

2. **НИКОГДА не деплоїй без тестів**
   ```bash
   python request_processor.py deploy  # має пройти test автоматично
   ```

3. **НИКОГДА не чираю базу без резервної копії**
   ```
   request_processor.py автоматично робить backup перед деплоєм
   ```

4. **Якщо щось не ясно — СПРОСИ перед комітом**
   ```
   Краще 5 хвилин запитання, ніж 2 години debug
   ```

---

## 📞 Потрібна допомога?

Дивись:
- `REQUEST_PIPELINE.md` — повна документація системи
- `python request_processor.py` — вихідний код скрипта (все відкрито)
- `pre_commit_checks.py` — перевірки перед комітом

Made for xp-bot 🐿️
