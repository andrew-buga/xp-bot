# 🔄 REQUEST PIPELINE — Система обробки запитів

## Процес: REQUEST → CHECK → TEST → DEPLOY

Це ваш чек-лист для **кожного** запиту: фіксу, фічі, скрипту.

---

## STAGE 1️⃣: VALIDATION (Перевірка)

### Що перевіряємо?
```
✅ Синтаксис Python (py_compile)
✅ Лінтинг (Ruff) — без F841, F541, неузніхованих імпортів
✅ Відсутні SQL injection-подібні конструкції
✅ Логування вмикається тільки в БД операціях
✅ Критичні скрипти мають резервну копію БД перед запуском
```

### Команда
```bash
python request_processor.py validate
```

### Що відбувається:
1. `python -m py_compile` для всіх `.py` файлів
2. `ruff check .` — знаходить невикористані імпорти, змінні
3. Перевіряє критичні файли (bot.py, database.py, config.py)
4. **Вихід**: PASS или FAIL + список проблем

### ❌ Якщо FAIL:
→ Вправ проблеми в коді  
→ Запусти `validate` знову  
→ Тільки потім йди до STAGE 2

---

## STAGE 2️⃣: TESTING (Тести)

### Що тестуємо?
```
✅ Усі наявні unit-тести (test_*.py)
✅ Базова функціональність скриптів
✅ Database integrity checks
✅ Миграції (якщо є)
```

### Команда
```bash
python request_processor.py test
```

### Що відбувається:
1. `pytest` або `python -m unittest` для всіх тестів
2. Запускає `detailed_integrity_check.py` (перевірка БД)
3. Перевіряє 3-5 критичних функцій вручну
4. **Вихід**: TEST REPORT з результатами

### ❌ Якщо тестові FAIL:
→ Іди до коду, поправ логіку  
→ Запусти `test` знову  
→ **НЕ ДЕПЛОЇЙ** поки тести не проходять!

---

## STAGE 3️⃣: DEPLOYMENT (Деплой)

### Pre-Deploy Checklist
```
✅ VALIDATION passed
✅ TESTS passed
✅ Немає відкритих конфліктів в git
✅ Всі зміни закомічені
✅ Запасна копія БД зроблена
```

### Команда
```bash
python request_processor.py deploy
```

### Що відбувається:
1. Перевіряє всі чек-листи ( abort якщо щось не так)
2. Резервна копія БД → `backups/bot_data.db.backup.TIMESTAMP`
3. `git push` → deploy
4. `systemctl restart xp-bot` → перезавантаж сервісу
5. Перевіряє логи: нема помилок? ✅ SUCCESS

### ❌ Якщо помилка при деплої:
1. Тут же `systemctl status xp-bot` — дивись логи
2. `git revert HEAD` — відкатись на попередню версію
3. Повтори STAGE 1 і 2
4. **НИКОГДА** не гадай — дивись логи!

---

## 🎯 Типові випадки

### Випадок 1: Новий скрипт для аналізу
```
1. Пишеш analyze_requests.py
2. python request_processor.py validate → OK?
3. Пишеш test_analyze_requests.py
4. python request_processor.py test → OK?
5. python request_processor.py deploy
```

### Випадок 2: Фіх баги в bot.py
```
1. Редагуєш bot.py
2. python request_processor.py validate → OK?
3. python request_processor.py test → OK?
4. python request_processor.py deploy
```

### Випадок 3: Критичний фіх БД
```
1. Редагуєш database.py + пишеш migration скрипт
2. python request_processor.py validate → OK?
3. Вручну тестуєш миграцію на копії БД
4. python request_processor.py test → OK?
5. python request_processor.py deploy
```

---

## 📋 Quick Reference

| Команда | Це робить | Вихід |
|---------|-----------|-------|
| `python request_processor.py validate` | Синтаксис + лінтинг | PASS/FAIL |
| `python request_processor.py test` | Запускає тести | TEST REPORT |
| `python request_processor.py deploy` | Деплой + рестарт | SUCCESS/ROLLBACK |
| `python request_processor.py check-pre-commit` | Всі 3 стадії разом | ✅ READY FOR DEPLOYMENT |

---

## 🚨 Правила, які НЕ ЛАМУТЬ

### 1️⃣ НИКОГДА не деплоїй без VALIDATION
→ Невиконаний синтаксис упадає на production

### 2️⃣ НИКОГДА не деплоїй без TESTS
→ Логіка може сломатися на реальних даних

### 3️⃣ НИКОГДА не деплоїй БД-скрипти без резервної копії
→ Якщо щось піде не так, у тебе буде щось для відновлення

### 4️⃣ Якщо щось не ясно — СПРОСИ, не гадай
→ Краще 5 хвилин запитання, ніж 2 години лагідження bugs

---

## 📝 Лог успішного деплою

```
✅ Stage 1/3: VALIDATION
  ✓ Syntax check passed
  ✓ Ruff check passed
  ✓ No critical issues found
  
✅ Stage 2/3: TESTING
  ✓ 5 tests passed
  ✓ Database integrity OK
  ✓ 0 failures
  
✅ Stage 3/3: DEPLOYMENT
  ✓ Backup created: backups/bot_data.db.backup.2026-04-15_14-30-45
  ✓ Git push successful
  ✓ Service restarted
  ✓ No errors in logs
  
🎉 DEPLOYMENT COMPLETE — System is live!
```

---

## 🔧 Конфігурація

Пиши конфіг `REQUEST_PIPELINE_CONFIG.yaml` (опціонально):

```yaml
# Які файли НЕ перевіряти
exclude_from_validation:
  - check_*.py
  - test_*.py

# Критичні файли (без них не деплоїм)
critical_files:
  - bot.py
  - database.py
  - config.py

# Де лежать тести
test_paths:
  - test_*.py
  - tests/

# Де робити резервні копії
backup_path: backups/

# Команда для рестарту сервісу
restart_command: systemctl restart xp-bot
```

---

**Made for xp-bot** 🐿️
