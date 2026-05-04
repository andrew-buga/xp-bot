# 💡 WORKFLOW EXAMPLES — Приклади роботи з системою

Це конкретні реальні приклади, як користуватися REQUEST PIPELINE для різних задач.

---

## 📌 Приклад 1: Новий скрипт для отримання статистики

### Завдання
Написати скрипт `export_user_stats.py`, який виводить статистику користувачів в CSV.

### Workflow

```bash
# STEP 1: Пишу скрипт
cat > export_user_stats.py << 'EOF'
#!/usr/bin/env python3
"""Export user statistics to CSV"""

import csv
from database import Database

def export_stats():
    db = Database()
    users = db.get_all_users()
    
    with open('user_stats.csv', 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['user_id', 'username', 'xp', 'level'])
        for user in users:
            writer.writerow([user['id'], user['name'], user['xp'], user['level']])
    
    print(f"Exported {len(users)} users to user_stats.csv")

if __name__ == '__main__':
    export_stats()
EOF

# STEP 2: Перевіка синтаксису та лінтингу
python request_processor.py validate

# Вихід:
# ✓ export_user_stats.py
# ✓ Синтаксис OK для 47 файлів
# ✓ Лінтинг OK
# ✓ VALIDATION PASSED — перейди до тестів

# STEP 3: Пишу тест
cat > test_export_user_stats.py << 'EOF'
#!/usr/bin/env python3
"""Test export_user_stats"""

import os
from export_user_stats import export_stats

def test_export():
    export_stats()
    assert os.path.exists('user_stats.csv'), "CSV file not created"
    with open('user_stats.csv') as f:
        lines = f.readlines()
        assert len(lines) > 1, "CSV is empty"
    print("✓ Test passed")

if __name__ == '__main__':
    test_export()
EOF

# STEP 4: Запускаю тести
python request_processor.py test

# Вихід:
# → Знайдено 3 тестові файлів: test_*.py
# → Запускаємо test_export_user_stats.py...
# ✓ test_export_user_stats.py пройшов
# ✓ TESTING PASSED — готово для деплою

# STEP 5: Деплойю!
python request_processor.py deploy

# Вихід:
# ✓ Резервна копія: backups/bot_data.db.backup.2026-04-15_14-30-45
# ✓ Git push успішний
# ✓ Сервіс перезавантажений ✓
# ✓ Логи в порядку ✓
# ✓ DEPLOYMENT COMPLETE — система live!
```

**Результат**: Новий скрипт на production, усі перевірки пройшли ✅

---

## 📌 Приклад 2: Фіх критичного баги в bot.py

### Завдання
У bot.py в обробнику `/info` команди не відображується рівень користувача.

### Workflow

```bash
# STEP 1: Читаю code, знаходжу проблему
# В bot.py, function send_profile():
#   message = f"Name: {user['name']}\nXP: {user['xp']}"
# Пропущен рівень!

# STEP 2: Фіксю
# Редагую bot.py, заміняю на:
#   message = f"Name: {user['name']}\nXP: {user['xp']}\nLevel: {user['level']}"

# STEP 3: Перевіка синтаксису
python request_processor.py validate

# Вихід:
# ✓ bot.py
# ✓ Синтаксис OK для 47 файлів
# ✓ Лінтинг OK
# ✓ VALIDATION PASSED

# STEP 4: Тест вже є (test_fix.py)
python request_processor.py test

# Вихід:
# → test_fix.py...
# ✓ test_fix.py пройшов
# ✓ TESTING PASSED

# STEP 5: Деплой
python request_processor.py deploy

# Вихід:
# ✓ Git push успішний
# ✓ Сервіс перезавантажений
# ✓ DEPLOYMENT COMPLETE

# STEP 6: Перевіряю на продакшені
# Запускаю /info комаду в Telegram → Рівень нарешті видиться ✓
```

**Час від проблеми до продакшену**: ~3 хвилини ✅

---

## 📌 Приклад 3: Критична миграція БД

### Завдання
Додати колонку `is_verified` до таблиці `users`.

### Workflow (НАЙБІЛЬШ ОБЕРЕЖНИЙ)

```bash
# STEP 1: Пишу миграційний скрипт
cat > migrate_add_is_verified.py << 'EOF'
#!/usr/bin/env python3
"""Migrate: add is_verified column to users"""

import sqlite3
from database import DATABASE_PATH

def migrate():
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    # Перевіряємо чи колонка вже існує
    cursor.execute("PRAGMA table_info(users)")
    columns = [col[1] for col in cursor.fetchall()]
    
    if 'is_verified' not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN is_verified INTEGER DEFAULT 0")
        print("✓ Added is_verified column")
    else:
        print("Column already exists")
    
    conn.commit()
    conn.close()

if __name__ == '__main__':
    migrate()
EOF

# STEP 2: Перевіка синтаксису
python request_processor.py validate

# STEP 3: Пишу тест міграції
cat > test_migrate_is_verified.py << 'EOF'
#!/usr/bin/env python3
"""Test migration"""

import sqlite3
from pathlib import Path
import shutil
from migrate_add_is_verified import migrate
from database import DATABASE_PATH

def test_migration():
    # Копіюємо БД для тесту
    test_db = Path('test_bot_data.db')
    if test_db.exists():
        test_db.unlink()
    
    shutil.copy(DATABASE_PATH, test_db)
    
    # Запускаємо міграцію
    migrate()
    
    # Перевіряємо що колонка існує
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(users)")
    columns = {col[1]: col[2] for col in cursor.fetchall()}
    conn.close()
    
    assert 'is_verified' in columns, "is_verified column not found"
    print("✓ Migration test passed")
    
    # Очищуємо
    test_db.unlink()

if __name__ == '__main__':
    test_migration()
EOF

# STEP 4: Запускаю тести
python request_processor.py test

# Вихід:
# ✓ test_migrate_is_verified.py пройшов
# ✓ TESTING PASSED

# STEP 5: ПЕРЕД деплоєм — вручну тестую на машині
# Копіюю БД на локальну машину
cp backups/bot_data.db.backup test_migration.db

# Запускаю міграцію на копії
DATABASE_PATH=test_migration.db python migrate_add_is_verified.py

# Перевіряю результат
sqlite3 test_migration.db "PRAGMA table_info(users);"
# Вихід має показати is_verified колонку

# ✓ Работає!

# STEP 6: Тепер деплойю
python request_processor.py deploy

# Вихід:
# ✓ Резервна копія: backups/bot_data.db.backup.2026-04-15
# ✓ Git push успішний
# ✓ Service restarted
# ✓ No errors in logs
# ✓ DEPLOYMENT COMPLETE

# STEP 7: Перевіряю на продакшені
sqlite3 bot_data.db "SELECT COUNT(*) FROM users WHERE is_verified = 0;"
# Усі користувачі мають is_verified = 0 (default) ✓
```

**Ключ**: Міграція мала резервну копію, прошла тести, нема помилок в логах ✅

---

## 📌 Приклад 4: Повний workflow — від ідеї до продакшену

### Завдання
Додати новий бот-команду `/leaderboard` яка показує топ-10 користувачів по XP.

### День 1: Planning + Development

```bash
# STEP 1: Пишу функцію в bot.py
# Додаю в bot.py:

async def handle_leaderboard(update, context):
    """Send top 10 users by XP"""
    db = Database()
    top_users = db.get_top_users(10)
    
    message = "🏆 TOP 10 LEADERBOARD\n\n"
    for i, user in enumerate(top_users, 1):
        message += f"{i}. {user['name']} — {user['xp']} XP\n"
    
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=message
    )

# Додаю команду в main():
app.add_handler(CommandHandler('leaderboard', handle_leaderboard))

# STEP 2: Додаю метод в database.py
# def get_top_users(self, limit=10):
#     return self.query(
#         'SELECT id, name, xp FROM users ORDER BY xp DESC LIMIT ?',
#         (limit,)
#     )

# STEP 3: Перевіка синтаксису
python request_processor.py validate

# STEP 4: Пишу тести
cat > test_leaderboard.py << 'EOF'
#!/usr/bin/env python3
"""Test leaderboard command"""

from database import Database
from unittest.mock import AsyncMock, MagicMock

async def test_leaderboard():
    db = Database()
    top_users = db.get_top_users(10)
    
    assert len(top_users) > 0, "No users in leaderboard"
    assert top_users[0]['xp'] >= top_users[-1]['xp'], "Not sorted by XP"
    print("✓ Leaderboard test passed")

if __name__ == '__main__':
    import asyncio
    asyncio.run(test_leaderboard())
EOF

# STEP 5: Запускаємо тести
python request_processor.py test

# ✓ test_leaderboard.py пройшов

# STEP 6: Git commit
python pre_commit_checks.py
# ✓ ВСІ ПЕРЕВІРКИ ПРОЙШЛИ

git add -A
git commit -m "feat: add /leaderboard command"

# На конец дня: всі зміни в git, тести зелені ✓
```

### День 2: Production Deployment

```bash
# STEP 1: Утром перевіляю що все нормально на локальній машині
python request_processor.py check-pre-commit

# Вихід:
# ✅ Stage 1/3: VALIDATION passed
# ✅ Stage 2/3: TESTING passed
# ✓ Усі перевірки пройшли! Готово для деплою

# STEP 2: Деплойю на продакшен
python request_processor.py deploy

# Вихід:
# ✓ Backup created
# ✓ Git push successful
# ✓ Service restarted
# ✓ DEPLOYMENT COMPLETE

# STEP 3: Вручну тестую на Telegram
# Запускаю /leaderboard
# Отримую:
#   🏆 TOP 10 LEADERBOARD
#   1. Vasya — 850 XP
#   2. Anya — 720 XP
#   ...

# ✅ LIVE!
```

**Timeline**: Середа-четвер, безпечна, надійна ✅

---

## 📌 Приклад 5: Швидкий фіх (Hotfix)

### Завдання (CRÍTICO)
Користувачі не можуть зареєструватися — помилка в `registration` команді!

### Workflow (TURBO-MODE)

```bash
# STEP 1: Дивлюся в логи
journalctl -u xp-bot -n 50

# Вихід:
# ...
# ERROR: AttributeError: 'NoneType' object has no attribute 'user_id'
# In: bot.py, line 234, handle_registration()

# STEP 2: Гарячий фіх в bot.py
# Лінія 234 була: user_id = update.message.from_user.id
# Повинна бути: user_id = update.effective_user.id

# STEP 3: ШВИДКІСНА перевірка
python pre_commit_checks.py
# ✓ Синтаксис OK

# STEP 4: ШВИДКІСНА перевірка + деплой
python request_processor.py deploy
# (він автоматично запускає validate + test перед deploy)

# Вихід:
# ✓ VALIDATION passed
# ✓ TESTING passed
# ✓ DEPLOYMENT COMPLETE

# STEP 5: Перевіляю в Telegram
# /start → реєстрація → ✅ WORK!

# Total time: ~2 хвилини від проблеми до fix ✓
```

---

## ✅ Чек-лист для кожного workflow

### Перед Commit:
```bash
☐ Написав код
☐ python request_processor.py validate  → ✅ PASS
☐ python pre_commit_checks.py           → ✅ PASS
☐ git commit
```

### Перед Deploy (локально):
```bash
☐ python request_processor.py check-pre-commit → ✅ PASS
☐ python request_processor.py deploy          → ✅ PASS
```

### На Production:
```bash
☐ Перевірити логи: journalctl -u xp-bot
☐ Вручно тестувати kritichne функції в Telegram
☐ Якщо проблема → git revert + git push
```

---

## 🎯 Типові помилки при використанні

❌ **MISTAKE**: Деплойю без перевіри тестів
✅ **CORRECT**: Запускаю `python request_processor.py deploy` який автоматично запускає усі перевірки

❌ **MISTAKE**: Забуваю про резервну копію БД
✅ **CORRECT**: `request_processor.py` автоматично робить backup перед деплоєм

❌ **MISTAKE**: Редагую БД вручну без тестів
✅ **CORRECT**: Пишу миграційний скрипт, тестую на копії, потім деплойю

❌ **MISTAKE**: Коміт без синтаксис перевірки
✅ **CORRECT**: `python pre_commit_checks.py` перед кожним git commit

---

**Made for xp-bot** 🐿️
