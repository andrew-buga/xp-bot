# 🚨 Критична Проблема: Втрата Даних Користувачів при Оновленні

##診斷(Diagnosis)

### Проблема
Після оновлення коду бота користувачи мають заново вибирати департамент, втрачаючи свої дані.

### Root Cause (Корінь Проблеми)
**Міграція бази даних була НЕЗАВЕРШЕНА:**

1. ✅ Дані були мігровані з `users.departments_json` → `users_departments` таблиця
2. ✅ Колонка `departments_json` була видалена з таблиці `users`
3. ❌ **АЛЕ функції `get_user_departments()`, `add_user_department()` і т.д. все ще намагаються читати/писати до видаленої колонки!**

### Дані НЕ Втрачені!
```sql
-- Дані ВСЕ ЕЩЕ у базі:
SELECT COUNT(*) FROM users_departments;  -- 4 записи
```

Существующие пользователи:
- **Robert** (498249299) → department: 5 ✓
- **viskas** (1058602390) → department: 5 ✓  
- **Andrey** (5266708533) → departments: 4, 5 ✓

Функции просто не могли их прочитать!

---

## Розв'язання (Solution)

### Що Було Виконано

#### 1. **Переписано 4 Критичні Функції** 
Всі функції тепер читають/пишуть до таблиці `users_departments` замість видаленої колонки:

**Функція: `get_user_departments(user_id)`**  
Раніше:
```python
c.execute("SELECT departments_json FROM users WHERE user_id=?")  # ✗ Колонка видалена!
```

Тепер:
```python
c.execute("SELECT department_id FROM users_departments WHERE user_id=?")  # ✓ Правильна таблиця
return sorted([row['department_id'] for row in rows])
```

**Функція: `add_user_department(user_id, dept_id)`**  
Раніше:
```python
c.execute("UPDATE users SET departments_json=?")  # ✗ Колонка видалена!
```

Тепер:
```python
c.execute("""INSERT INTO users_departments (user_id, department_id, dept_role, joined_at)
           VALUES (?, ?, 'member', ?)""")  # ✓ INSERT у правильну таблицю
```

**Функція: `remove_user_department(user_id, dept_id)`**  
Тепер правильно видаляє з таблиці:
```python
c.execute("DELETE FROM users_departments WHERE user_id=? AND department_id=?")
```

**Функція: `has_user_department(user_id, dept_id)`**  
Тепер правильно перевіряє наявність:
```python
c.execute("SELECT COUNT(*) FROM users_departments WHERE user_id=? AND department_id=?")
```

#### 2. **Тестування**
```
✓ TEST 1: Loading existing user departments
  User: Robert               (498249299) → departments: [5]
  User: viskas               (1058602390) → departments: [5]
  User: Andrey               (5266708533) → departments: [4, 5]

✓ TEST 2: Adding new department to user
  Adding department 1 to user 999888777
  After add: [1]

✓ TEST 3: Checking department membership
  User 5266708533 has department 4? True
```

---

## Що Буде Далі (Next Steps)

### 1. **Завантажити Оновлений Код на Сервер** ✅
```bash
git add database.py
git commit -m "Fix critical persistence bug: restore user department data loading"
git push origin master
ssh root@... "cd /opt/xp-bot && git pull && systemctl restart xp-bot"
```

### 2. **Очікуваний Результат**
При перезапуску бота:

**Раніше (BROKEN):**
```
User 498249299 запускає бот
→ /start вибирає департамент (форсовано)
→ Дані не зберігаються
```

**Тепер (FIXED):**
```
User 498249299 запускає бот
→ Система завантажує його дані з бази
→ Департамент: 5 (зберігається в users_departments)
→ Меню показується без повторного запиту
→ Дані зберігаються при кожному виборі
```

### 3. **Відновлення Даних ІСНУЮЧИХ користувачів**
Дані вже там! Не потрібна окрема міграція.

Але у користувачів може бути кеш в пам'яті Telegram бота. Їм потрібно:
- Видалити чат з ботом та стикнути його заново
- АБО виконати `/start` знову

### 4. **Гарантування Персистентності на Майбутнє**

**Правила:**
1. ✅ Всі дані користувачів в `users` таблиці
2. ✅ Всі department-to-user mappings в `users_departments` таблиці (PRIMARY KEY)
3. ✅ Функції НЕ мають читати/писати до deleted/deprecated колонок
4. ✅ При кожному обновленні - ЗАВЖДИ тестувати: `python test_fix.py`

---

## Детальна Архітектура Бази Даних

```
┌─────────────────────────────────────┐
│         users TABLE                  │
├─────────────────────────────────────┤
│ user_id (PK)                        │
│ username                            │
│ first_name                          │
│ xp, total_xp, spendable_xp          │
│ joined_at                           │
│ is_banned, banned_at                │
│ language                            │
│ is_verified, verified_at            │
│ needs_recheck                       │
│ role (global: 'user', 'admin')      │
└─────────────────────────────────────┘
          ↓ (user_id FK)
┌─────────────────────────────────────┐
│    users_departments TABLE (JUNCTION)│
├─────────────────────────────────────┤
│ user_id (PK)                        │ Stores:
│ department_id (PK)                  │ - Which departments user belongs to
│ dept_role: 'member', 'supervisor'   │ - User's role in that department
│ joined_at                           │ - When they joined
└─────────────────────────────────────┘
          ↓ (department_id FK)
┌─────────────────────────────────────┐
│      departments TABLE              │
├─────────────────────────────────────┤
│ id (PK): 1-5                        │
│ name: "SMM та Медіа", "Фінанси"    │
│ emoji: "📱", "💰"                  │
└─────────────────────────────────────┘
```

**CRITICAL:** 
- ❌ Так як НЕ використовуються: `users.department_id`, `users.departments_json`
- ✅ ПРАВИЛЬНО використовуються: `users_departments` таблиця

---

## Перевірка Коду

Всі ці функції тепер ПРАВИЛЬО працюють:
- `get_user_departments()` - ✅ FIXED
- `add_user_department()` - ✅ FIXED  
- `remove_user_department()` - ✅ FIXED
- `has_user_department()` - ✅ FIXED
- `set_user_dept_role()` - ✅ (залежить від вищих)
- `get_user_dept_role()` - ✅ (уже правильно)
- `get_user_all_dept_roles()` - ✅ (уже правильно)
- `get_dept_supervisors()` - ✅ (уже правильно)
- `is_supervisor_of_dept()` - ✅ (уже правильно)

---

## Висновок

**ЩО БУЛО:**
- Дані існували в БД
- Функції їх не могли прочитати
- Користувачи вимушені були заново вибирати

**ЩО ТЕПЕР:**
- Дані існують в БД ✅
- Функції їх правильно читають ✅
- Користувачи бачать свої збережені департаменти ✅
- Нові выбори одразу зберігаються ✅

**МАСШТАБОВАНІСТЬ:**
- БД масштабується до мільйонів користувачів
- SQLite справляється добре для текущего масштабу
- Коли потрібна більша масштабованість → MongoDB/PostgreSQL (по запиту)
