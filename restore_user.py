#!/usr/bin/env python3
"""Restore missing user data from backup"""

import sqlite3
from datetime import datetime

backup_file = './backups/bot_data_2026-03-06_03-00-01.db'
current_file = 'bot_data.db'

print('Восстановление Robert из резервной копии...')
print('=' * 60)

try:
    # Читаємо бекап
    backup_conn = sqlite3.connect(backup_file)
    backup_c = backup_conn.cursor()
    
    # Подивимось на структуру старої БД
    backup_c.execute('PRAGMA table_info(users)')
    columns = [row[1] for row in backup_c.fetchall()]
    print(f'Колонки в старій БД: {columns}')
    
    # Читаємо дані Robert з доступних колонок
    backup_c.execute('SELECT user_id, username, first_name FROM users WHERE user_id = 498249299')
    robert_data = backup_c.fetchone()
    
    if not robert_data:
        print('❌ Robert не знайдений')
        backup_conn.close()
        exit(1)
    
    print(f'✓ Знайдено Robert: {robert_data}')
    
    # Читаємо departments (якщо таблиця існує)
    backup_c.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in backup_c.fetchall()]
    
    if 'users_departments' in tables:
        backup_c.execute('SELECT department_id FROM users_departments WHERE user_id = 498249299')
        robert_depts = [row[0] for row in backup_c.fetchall()]
        print(f'✓ Департаменти: {robert_depts}')
    else:
        print('✓ users_departments таблиці немає, використовуємо IT як default')
        robert_depts = [5]  # По замовчуванню IT
    
    backup_conn.close()
    
    # Вставляємо в текущу БД
    current_conn = sqlite3.connect(current_file)
    current_c = current_conn.cursor()
    
    # Вставляємо користувача
    current_c.execute('''
        INSERT OR REPLACE INTO users 
        (user_id, username, first_name, xp, total_xp, spendable_xp, joined_at, language, role)
        VALUES (?, ?, ?, 0, 0, 0, ?, ?, ?)
    ''', (robert_data[0], robert_data[1], robert_data[2], datetime.now().isoformat(), 'uk', 'user'))
    
    # Вставляємо департаменти
    for dept_id in robert_depts:
        current_c.execute('''
            INSERT OR IGNORE INTO users_departments
            (user_id, department_id, dept_role, joined_at)
            VALUES (?, ?, ?, ?)
        ''', (robert_data[0], dept_id, 'member', datetime.now().isoformat()))
    
    current_conn.commit()
    current_conn.close()
    
    print(f'✓ Успішно! Robert відновлений!')
    
    # Перевіримо
    check_conn = sqlite3.connect(current_file)
    check_c = check_conn.cursor()
    
    check_c.execute('SELECT first_name FROM users WHERE user_id = 498249299')
    result = check_c.fetchone()
    
    if result:
        print(f'✓ Перевірка: {result[0]} успішно в БД')
    else:
        print(f'❌ Перевірка не пройшла')
    
    check_conn.close()
    
except Exception as e:
    print(f'❌ Помилка: {e}')
    import traceback
    traceback.print_exc()
