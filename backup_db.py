#!/usr/bin/env python3
"""
💾 Database Backup Script with Git Integration

Можна запустити вручну або через Git post-commit hook.
На Windows: python backup_db.py
На Linux/Mac: python backup_db.py або додати в .git/hooks/post-commit
"""

import shutil
from pathlib import Path
from datetime import datetime
import subprocess

def get_git_info():
    """Отримати інформацію про поточний комміт"""
    try:
        # Отримай commit hash
        commit_hash = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True
        ).stdout.strip()
        
        # Отримай commit message
        commit_msg = subprocess.run(
            ["git", "log", "-1", "--pretty=%B"],
            capture_output=True,
            text=True,
            check=True
        ).stdout.strip()
        
        # Отримай branch name
        branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            check=True
        ).stdout.strip()
        
        return {
            'hash': commit_hash,
            'message': commit_msg[:30],  # Перші 30 символів повідомлення
            'branch': branch
        }
    except Exception as e:
        print(f"⚠️  Не можна отримати інформацію про Git: {e}")
        return {
            'hash': 'unknown',
            'message': 'unknown',
            'branch': 'unknown'
        }

def backup_database(verbose=True):
    """Створити резервну копію БД з часовою міткою та git інформацією"""
    
    db_path = Path("bot_data.db")
    backups_dir = Path("backups")
    
    if not db_path.exists():
        print("❌ bot_data.db не знайдено")
        return False
    
    # Створи папку для бекапів
    backups_dir.mkdir(exist_ok=True)
    
    # Отримай інформацію про комміт
    git_info = get_git_info()
    
    # Створи назву файлу: bot_data_COMMIT_YYYYMMDD_HHMMSS.db
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    commit_part = git_info['hash']
    backup_name = f"bot_data_{commit_part}_{timestamp}.db"
    backup_path = backups_dir / backup_name
    
    try:
        # Скопіюй БД
        shutil.copy2(db_path, backup_path)
        
        if verbose:
            file_size = backup_path.stat().st_size / (1024 * 1024)  # MB
            print(f"✅ Резервна копія створена: {backup_path}")
            print(f"   📊 Розмір: {file_size:.2f} MB")
            print(f"   🔗 Комміт: {commit_part}")
            print(f"   📝 Повідомлення: {git_info['message']}")
            print(f"   🌳 Branch: {git_info['branch']}")
        
        # Очисти старі бекапи (зберігай тільки останніх 15)
        backup_files = sorted(backups_dir.glob("bot_data_*.db"))
        if len(backup_files) > 15:
            removed_count = len(backup_files) - 15
            for old_backup in backup_files[:-15]:
                old_backup.unlink()
                if verbose and removed_count <= 3:
                    print(f"🗑️  Видалено старий бекап: {old_backup.name}")
            if removed_count > 3:
                print(f"🗑️  Видалено {removed_count} старих бекапів (зберігти останні 15)")
        
        return True
    
    except Exception as e:
        print(f"❌ Помилка під час створення резервної копії: {e}")
        return False

def restore_backup(backup_name=None):
    """Відновити БД з резервної копії"""
    
    backups_dir = Path("backups")
    db_path = Path("bot_data.db")
    
    if not backups_dir.exists():
        print("❌ Папка backups не знайдена")
        return False
    
    # Якщо не вказана конкретна резервна копія, використай найновішу
    if backup_name is None:
        backup_files = sorted(backups_dir.glob("bot_data_*.db"))
        if not backup_files:
            print("❌ Резервні копії не знайдені")
            return False
        backup_path = backup_files[-1]
    else:
        backup_path = backups_dir / backup_name
    
    if not backup_path.exists():
        print(f"❌ Резервна копія не знайдена: {backup_name}")
        return False
    
    try:
        # Зробимо резервну копію поточної БД перед відновленням
        if db_path.exists():
            current_backup = backups_dir / f"current_bot_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
            shutil.copy2(db_path, current_backup)
            print(f"⚠️  Поточна БД збережена: {current_backup.name}")
        
        # Відновлення
        shutil.copy2(backup_path, db_path)
        print(f"✅ БД відновлена з: {backup_path.name}")
        return True
    
    except Exception as e:
        print(f"❌ Помилка під час відновлення: {e}")
        return False

def list_backups():
    """Список усіх резервних копій"""
    
    backups_dir = Path("backups")
    
    if not backups_dir.exists():
        print("❌ Папка backups не знайдена")
        return
    
    backup_files = sorted(backups_dir.glob("bot_data_*.db"), reverse=True)
    
    if not backup_files:
        print("❌ Резервні копії не знайдені")
        return
    
    print(f"\n📚 Всього резервних копій: {len(backup_files)}\n")
    
    for idx, backup_file in enumerate(backup_files[:15], 1):
        size = backup_file.stat().st_size / (1024 * 1024)
        mtime = datetime.fromtimestamp(backup_file.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        print(f"{idx:2}. {backup_file.name} ({size:.2f} MB) - {mtime}")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        command = sys.argv[1].lower()
        
        if command == "restore":
            backup_name = sys.argv[2] if len(sys.argv) > 2 else None
            restore_backup(backup_name)
        
        elif command == "list":
            list_backups()
        
        else:
            print(f"❌ Невідома команда: {command}")
            print("\nДоступні команди:")
            print("  python backup_db.py              - Створити резервну копію")
            print("  python backup_db.py list         - Список резервних копій")
            print("  python backup_db.py restore      - Відновити найновішу резервну копію")
            print("  python backup_db.py restore NAME - Відновити певну резервну копію")
    else:
        # За замовчуванням - створи резервну копію
        backup_database()
