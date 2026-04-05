#!/usr/bin/env python3
"""
🔄 Full Data Recovery Script
Відновлює усі втрачені дані користувачів з логів, резервних копій та аналітики.
Ігнорує дані, які співпадають з актуальними.
"""

import json
from pathlib import Path
import database

def get_all_users_from_db():
    """Отримати всіх користувачів з БД"""
    conn = database.get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM users ORDER BY user_id")
    users = [dict(row) for row in c.fetchall()]
    conn.close()
    return users

def get_user_history_from_analytics():
    """Отримати історію користувачів з логів аналітики"""
    events_file = Path("analytics/events.jsonl")
    if not events_file.exists():
        print("❌ Файл analytics/events.jsonl не знайдено")
        return {}
    
    user_history = {}
    
    with open(events_file, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                event = json.loads(line.strip())
                if not event:
                    continue
                
                user_id = event.get('user_id')
                if not user_id:
                    continue
                
                if user_id not in user_history:
                    user_history[user_id] = {
                        'username': None,
                        'first_name': None,
                        'departments': set(),
                        'xp_events': [],
                        'profile_events': [],
                        'submission_events': []
                    }
                
                # Записуй дані з профілю
                if 'username' in event:
                    user_history[user_id]['username'] = event['username']
                if 'first_name' in event:
                    user_history[user_id]['first_name'] = event['first_name']
                
                # Записуй дані з départements
                if event.get('event_type') == 'department_selected':
                    dept_id = event.get('department_id')
                    if dept_id:
                        user_history[user_id]['departments'].add(dept_id)
                
                # Записуй XP evento
                if event.get('event_type') == 'xp_awarded':
                    user_history[user_id]['xp_events'].append(event)
                
                # Записуй дані профілю
                if event.get('event_type') in ['user_registered', 'profile_updated']:
                    user_history[user_id]['profile_events'].append(event)
                
                # Записуй дані про завдання
                if event.get('event_type') in ['task_submitted', 'task_approved']:
                    user_history[user_id]['submission_events'].append(event)
            
            except json.JSONDecodeError:
                continue
    
    return user_history

def compare_current_with_history(current_users, user_history):
    """Порівняй поточні дані з історичними та знайди розбіжності"""
    
    print("\n" + "="*70)
    print("📊 ПОРІВНЯННЯ ПОТОЧНИХ ДАНИХ З ІСТОРІЄЮ")
    print("="*70 + "\n")
    
    discrepancies = []
    
    for user in current_users:
        user_id = user['user_id']
        
        if user_id not in user_history:
            print(f"⚠️  UID {user_id}: Немає записів у логах")
            continue
        
        history = user_history[user_id]
        
        # Перевір департамента
        current_depts = set(database.get_user_departments(user_id) or [])
        historical_depts = history['departments']
        
        if historical_depts and current_depts != historical_depts:
            print(f"📍 UID {user_id} ({user['username']}):")
            print(f"   Актуальні дepts: {sorted(current_depts)}")
            print(f"   Історичні depts: {sorted(historical_depts)}")
            missing = historical_depts - current_depts
            if missing:
                print(f"   ⚠️  ВІДСУТНІ: {sorted(missing)}")
                discrepancies.append({
                    'user_id': user_id,
                    'type': 'departments',
                    'missing': missing,
                    'current': current_depts,
                    'historical': historical_depts
                })
        
        # Перевір профіль
        if history['username'] and history['username'] != user['username']:
            print(f"👤 UID {user_id}: Прізвище відрізняється")
            print(f"   Актуальне: {user['username']}")
            print(f"   Історичне: {history['username']}")
            discrepancies.append({
                'user_id': user_id,
                'type': 'username',
                'current': user['username'],
                'historical': history['username']
            })
        
        if history['first_name'] and history['first_name'] != user['first_name']:
            print(f"📝 UID {user_id}: Ім'я відрізняється")
            print(f"   Актуальне: {user['first_name']}")
            print(f"   Історичне: {history['first_name']}")
    
    return discrepancies

def restore_missing_data(discrepancies):
    """Відновлення відсутніх даних"""
    
    print("\n" + "="*70)
    print("🔄 ВІДНОВЛЕННЯ ВТРАЧЕНИХ ДАНИХ")
    print("="*70 + "\n")
    
    if not discrepancies:
        print("✅ Немає розбіжностей! Всі дані актуальні.")
        return
    
    restored_count = 0
    
    for disc in discrepancies:
        user_id = disc['user_id']
        
        if disc['type'] == 'departments':
            missing = disc['missing']
            current = disc['current']
            
            print(f"📍 Відновлення департаментів для UID {user_id}...")
            
            for dept_id in missing:
                if current and dept_id not in current:
                    try:
                        database.add_user_department(user_id, dept_id)
                        print(f"   ✅ Додано департамент {dept_id}")
                        restored_count += 1
                    except Exception as e:
                        print(f"   ❌ Помилка додавання {dept_id}: {e}")
        
        elif disc['type'] == 'username':
            print(f"👤 Оновлення username для UID {user_id}...")
            try:
                database.update_user_username(
                    user_id, 
                    disc['historical'], 
                    None
                )
                print(f"   ✅ Оновлено username: {disc['historical']}")
                restored_count += 1
            except Exception as e:
                print(f"   ❌ Помилка оновлення: {e}")
    
    print(f"\n✅ Видновлено {restored_count} елементів даних")

def print_recovery_summary(current_users, user_history):
    """Вивести звіт про відновлення"""
    
    print("\n" + "="*70)
    print("📈 ИТОГОВЫЙ ОТЧЕТ")
    print("="*70 + "\n")
    
    print(f"👥 Користувачів у БД: {len(current_users)}")
    print(f"📊 Користувачів у логах: {len(user_history)}")
    
    for user in current_users:
        user_id = user['user_id']
        depts = database.get_user_departments(user_id) or []
        
        print(f"\n👤 {user['username'] or 'N/A'} (UID: {user_id})")
        print(f"   📍 Департамента: {len(depts)} → {depts}")
        print(f"   ⭐ XP: {user['xp']}/{user['total_xp']}")
        print(f"   💰 Spendable XP: {user['spendable_xp']}")
        
        if user_id in user_history:
            hist = user_history[user_id]
            if hist['departments']:
                print(f"   📜 Історично мав дepts: {sorted(hist['departments'])}")

def main():
    print("🔄 Запуск відновлення даних користувачів...\n")
    
    database.init_db()
    
    # Отримай поточні дані
    current_users = get_all_users_from_db()
    print(f"✅ Загружено {len(current_users)} користувачів з БД")
    
    # Отримай історичні дані
    user_history = get_user_history_from_analytics()
    print(f"✅ Загружено історія для {len(user_history)} користувачів\n")
    
    # Порівняй
    discrepancies = compare_current_with_history(current_users, user_history)
    
    # Відновлення
    if discrepancies:
        response = input("\n🤔 Хочеш відновити втрачені дані? (y/n): ").strip().lower()
        if response == 'y':
            restore_missing_data(discrepancies)
    
    # Звіт
    print_recovery_summary(current_users, user_history)
    
    print("\n" + "="*70)
    print("✅ Відновлення завершено!")
    print("="*70)

if __name__ == '__main__':
    main()
