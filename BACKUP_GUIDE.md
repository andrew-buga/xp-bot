# 💾 Automatyczne Kopie Zapasowe (Backup) Bazy Danych

## 📋 Opис

Після кожного коміту automatically створюється резервна копія БД (`bot_data.db`) на
твій комп'ютер. Резервні копії зберігаються у папці `backups/` з часовою міткою і commit hash.

## 🚀 Налаштування на Windows (Git Bash / PowerShell)

### Крок 1: Включи Git Hooks
```powershell
# PowerShell
cd c:\xp-bot
git config core.hooksPath .git/hooks
```

### Крок 2: Роблять скрипт виконуваним (якщо потрібно)
На Windows це часто не потрібно, але якщо Git Hooks не запускаються:

```bash
# Git Bash
chmod +x .git/hooks/post-commit
```

### Крок 3: Тестуй налаштування
Зробимо тестовий комміт:
```bash
git add .
git commit -m "🔄 Test backup"
```

Після цього повинен:
- Виконатися комміт
- Автоматично запуститься `backup_db.py`
- У папці `backups/` з'явиться новий файл

## 📁 Структура резервних копій

```
backups/
├── bot_data_abc1234_20260405_153042.db   (25 MB) - 2026-04-05 15:30:42
├── bot_data_abc1234_20260405_151530.db   (25 MB) - 2026-04-05 15:15:30
├── bot_data_9ef5678_20260404_200000.db   (24 MB) - 2026-04-04 20:00:00
└── current_bot_data_20260405_150000.db   (25 MB) - Резервна копія перед відновленням
```

**Формат імені файлу:**
```
bot_data_COMMIT_YYYYMMDD_HHMMSS.db
           └─┬─┘  └──┬──┘  └──┬──┘
      Commit Hash  Date    Time
```

## 🎯 Використання

### Список усіх резервних копій
```bash
python backup_db.py list
```

Результат:
```
📚 Всього резервних копій: 12

 1. bot_data_db13b8f_20260405_154230.db (25.34 MB) - 2026-04-05 15:42:30
 2. bot_data_db13b8f_20260405_151530.db (25.32 MB) - 2026-04-05 15:15:30
 3. bot_data_704f186_20260404_200000.db (24.89 MB) - 2026-04-04 20:00:00
 ...
15. bot_data_abc1234_20260402_093015.db (23.45 MB) - 2026-04-02 09:30:15
```

### Створити резервну копію вручну
```bash
python backup_db.py
```

Результат:
```
✅ Резервна копія створена: backups\bot_data_db13b8f_20260405_154500.db
   📊 Розмір: 25.34 MB
   🔗 Комміт: db13b8f
   📝 Повідомлення: 🔄 Test backup
   🌳 Branch: master
```

### Відновити найновішу резервну копію
```bash
python backup_db.py restore
```

**Результат:**
```
⚠️  Поточна БД збережена: current_bot_data_20260405_154645.db
✅ БД відновлена з: bot_data_704f186_20260404_200000.db
```

### Відновити конкретну резервну копію
```bash
python backup_db.py restore bot_data_704f186_20260404_200000.db
```

## ⚙️ Налаштування

### Проблема: Backup не створюється після коміту

**Рішення 1: Перевір Git Hooks Path**
```bash
git config core.hooksPath
# Має показати: .git/hooks
```

**Рішення 2: Перевір права доступу**
```bash
ls -la .git/hooks/post-commit
# Має бути виконуваний (rwxr-xr-x)
```

**Рішення 3: Запусти скрипт вручну**
```bash
python backup_db.py
# Повинна виконатись без помилок
```

**Рішення 4: Перевір наявність bot_data.db**
```bash
ls -la bot_data.db
# File must exist
```

### Видаль старі резервні копії вручну
```powershell
# PowerShell
Remove-Item backups\bot_data_*.db | Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-7) }
```

Скрипт **автоматично** зберігає тільки **15 найновіших** резервних копій.

## 🔄 Відновлення після помилки

Якщо щось пошло не так:

### 1. Перейди в папку проекту
```bash
cd c:\xp-bot
```

### 2. Список всіх бекапів
```bash
python backup_db.py list
```

### 3. Вибери відповідний backup (зазвичай найновший або останній перед помилкою)
```bash
python backup_db.py restore bot_data_704f186_20260404_200000.db
```

### 4. Перевір БД
```bash
python detailed_integrity_check.py
```

## 📊 Порівняння резервних копій

Щоб з'ясувати, яка резервна копія найкраща:

1. Перегляни список: `python backup_db.py list`
2. Можеш видалити старіші файли вручну з папки `backups/`
3. Скрипт автоматично видалить файли, якщо їх більше ніж 15

## 🛡️ Безпека та резервування

**Что происходит:**
- ✅ Кожний комміт автоматично створює снимок БД
- ✅ Последние 15 файлів зберігаються в `backups/`
- ✅ Старші файли автоматично видаляютсья
- ✅ Ім'я файлу містить commit hash для ідентифікації

**Рекомендації:**
- 📦 Час від часу завантажь резервні копій на вовнішній диск
- 💾 Зберігай важливі бекапи на хмарному сховищі (Google Drive, OneDrive)
- 🔄 Тестуй відновлення раз на місяць

## 📝 Git Hooks Требования

Файли hooks в папці `.git/hooks/`:

| Файл | Обяснення | При |
|------|-----------|-----|
| `post-commit` | Python скрипт (Unix/Mac) | Автоматичні backup |
| `post-commit.bat` | Batch скрипт (Windows) | Автоматичні backup |
| `backup_db.py` | Основной скрипт | Резервування БД |

**На Windows** Git Bash / PowerShell повинна автоматично запустити файл hook.
Якщо це не відбувається, запусти:

```bash
git config core.hooksPath .git/hooks
```

## 🆘 Помощь

Якщо щось не так відбувається, виконай:

```bash
cd c:\xp-bot

# 1. Переконайся, що Python встановлен
python --version

# 2. Запусти скрипт вручну
python backup_db.py

# 3. Перевір папку backups
dir backups\

# 4. Список всіх бекапів
python backup_db.py list

# 5. Запусти integrity check
python detailed_integrity_check.py
```

---

**Статус:** ✅ Готово до використання!
