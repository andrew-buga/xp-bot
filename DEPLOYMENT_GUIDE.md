# 📖 Как Развернуть Критический Патч Персистентности

## Статус
- ✅ Код локально исправлен и протестирован
- ✅ Коммит создан: `0aa3f22` - "🚨 CRITICAL FIX: Restore user data persistence"
- ✅ Закоммичено в GitHub: https://github.com/andrew-buga/xp-bot
- ⏳ **ОЖИДАЕТ РАЗВЕРТЫВАНИЯ НА СЕРВЕР**

## Что было исправлено

### Проблема
```
users.departments_json колонка была удалена из БД
↓
функции get_user_departments() и подобные все еще пытались читать из нее
↓
ВСЕ пользовательские отделы не загружались при перезапуске
```

### Решение
Переписаны 4 функции в `database.py`:
1. `get_user_departments()` - теперь читает из `users_departments` таблицы
2. `add_user_department()` - теперь вставляет в `users_departments` таблицу
3. `remove_user_department()` - теперь удаляет из `users_departments` таблицы
4. `has_user_department()` - теперь проверяет `users_departments` таблицу

## Развертывание на Production

### Вариант 1: Через SSH (если у вас есть ключи)
```bash
ssh root@209.38.246.50 "cd /opt/xp-bot && git pull origin master && systemctl restart xp-bot"
```

### Вариант 2: Ручное развертывание (если SSH не доступен)
```bash
# На сервере:
cd /opt/xp-bot
git pull origin master

# Проверить синтаксис:
python -m py_compile database.py bot.py

# Перезагрузить сервис:
systemctl restart xp-bot

# Проверить статус:
systemctl status xp-bot
```

## Проверка После Развертывания

### Логи
```bash
journalctl -u xp-bot -f
```

### Тестирование
Попросите одного из существующих пользователей запустить `/start`:
- **Раньше:** Заново выбирал отдел (БУ)
- **Теперь:** Должен загрузить сохраненный отдел (ИСПРАВЛЕНО)

### Данные в БД
```bash
# На сервере, проверить данные:
python3 << 'EOF'
from database import get_user_departments, get_user

for uid in [498249299, 1058602390, 5266708533]:
    depts = get_user_departments(uid)
    user = get_user(uid)
    if user:
        print(f"User: {user['first_name']:20} ({uid}) → departments: {depts}")
EOF
```

## Ожидаемый Результат

### ДО расправертывания (BROKEN)
```
User запускает /start
→ Система просит выбрать отдел (хотя он уже выбран)
→ Данные не сохраняются
```

### ПОСЛЕ развертывания (FIXED)
```
User запускает /start  
→ Система загружает его отделы из БД
→ Меню показывается БЕЗ повторного запроса
→ Если выбирает новый отдел → сохраняется в БД
→ При следующем /start → загружает оба отдела
```

## Откат (если что-то пойдет не так)
```bash
# Вернуться к предыдущей версии:
cd /opt/xp-bot
git revert HEAD      # создает ревертный коммит
git push origin master
# или просто:
git reset --hard f093167  # вернуться к предыдущему коммиту
```

## Команды для проверки

### Проверить текущий коммит на сервере
```bash
cd /opt/xp-bot
git log --oneline -1  # должно быть: 0aa3f22 CRITICAL FIX: Restore...
```

### Проверить версию БД на сервере
```bash
# Убедитесь, что таблица users_departments есть и содержит данные:
python3 -c "
import sqlite3
conn = sqlite3.connect('bot_data.db')
c = conn.cursor()
c.execute('SELECT COUNT(*) FROM users_departments')
print(f'Total department mappings: {c.fetchone()[0]}')
conn.close()
"
```

## Риски
- ✅ **LOW** - это исправление функций, данные не трогаются
- ✅ **SAFE** - протестировано локально с реальными данными
- ✅ **REVERSIBLE** - можно откатить если потребуется

## Контрольный Список
- [ ] Развернуть на prod: `git pull origin master`
- [ ] Перезагрузить бот: `systemctl restart xp-bot`
- [ ] Проверить логи: `journalctl -u xp-bot -f`
- [ ] Попросить пользователя запустить /start
- [ ] Убедиться, что отдел загружается из БД
- [ ] Убедиться, что новый выбор отдела сохраняется
