#!/usr/bin/env python3
"""
Database recovery and validation utility for XP Bot
- Checks for orphan records
- Restores missing users from backup
- Validates data consistency
"""

import sqlite3
import os
from datetime import datetime

def check_database_health(db_file='bot_data.db'):
    """Check if database has orphan records and missing users"""
    
    try:
        conn = sqlite3.connect(db_file)
        c = conn.cursor()
        
        print("=" * 60)
        print("DATABASE HEALTH CHECK")
        print("=" * 60)
        
        # Count users and dependencies
        c.execute("SELECT COUNT(*) FROM users")
        users_count = c.fetchone()[0]
        
        c.execute("SELECT COUNT(*) FROM users_departments")
        depts_count = c.fetchone()[0]
        
        print(f"\n✓ Users table: {users_count} records")
        print(f"✓ Users_departments table: {depts_count} records")
        
        # Check for orphans (in users_departments but not in users)
        c.execute('''
            SELECT DISTINCT ud.user_id FROM users_departments ud
            WHERE ud.user_id NOT IN (SELECT user_id FROM users)
        ''')
        orphans = c.fetchall()
        
        if orphans:
            print(f"\n❌ ORPHAN RECORDS FOUND: {len(orphans)}")
            for orphan in orphans:
                print(f"  - User {orphan[0]} in departments but NOT in users table")
            return False
        else:
            print(f"\n✓ No orphan records")
        
        # List all users
        print(f"\n✓ All users:")
        c.execute("SELECT user_id, first_name FROM users ORDER BY user_id")
        for row in c.fetchall():
            c2 = conn.cursor()
            c2.execute("SELECT department_id FROM users_departments WHERE user_id = ?", (row[0],))
            depts = [str(d[0]) for d in c2.fetchall()]
            print(f"  {row[1]:20} ({row[0]:10}) → [{', '.join(depts)}]")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def restore_from_backup(backup_file, current_db='bot_data.db'):
    """Restore missing users from backup database"""
    
    if not os.path.exists(backup_file):
        print(f"❌ Backup file not found: {backup_file}")
        return False
    
    try:
        # Read from backup
        backup_conn = sqlite3.connect(backup_file)
        backup_c = backup_conn.cursor()
        
        # Get list of tables
        backup_c.execute("SELECT name FROM sqlite_master WHERE type='table'")
        backup_tables = [row[0] for row in backup_c.fetchall()]
        
        if 'users' not in backup_tables:
            print(f"❌ Backup missing 'users' table")
            backup_conn.close()
            return False
        
        # Get all users from backup
        backup_c.execute("SELECT user_id, username, first_name FROM users")
        backup_users = backup_c.fetchall()
        
        # Check what's missing in current DB
        current_conn = sqlite3.connect(current_db)
        current_c = current_conn.cursor()
        
        current_c.execute("SELECT user_id FROM users")
        current_users = set(row[0] for row in current_c.fetchall())
        
        missing_users = [u for u in backup_users if u[0] not in current_users]
        
        if not missing_users:
            print("✓ No missing users to restore")
            backup_conn.close()
            current_conn.close()
            return True
        
        print(f"\n🔄 Restoring {len(missing_users)} missing users...")
        
        for user_id, username, first_name in missing_users:
            print(f"  Restoring: {first_name} ({user_id})")
            
            # Insert user
            current_c.execute('''
                INSERT OR REPLACE INTO users 
                (user_id, username, first_name, xp, total_xp, spendable_xp, joined_at, language, role)
                VALUES (?, ?, ?, 0, 0, 0, ?, ?, ?)
            ''', (user_id, username, first_name, datetime.now().isoformat(), 'uk', 'user'))
            
            # Restore departments if table exists in backup
            if 'users_departments' in backup_tables:
                backup_c.execute('SELECT department_id FROM users_departments WHERE user_id = ?', (user_id,))
                backup_depts = [row[0] for row in backup_c.fetchall()]
            else:
                # Default to IT department if no info available
                backup_depts = [5]
            
            for dept_id in backup_depts:
                current_c.execute('''
                    INSERT OR IGNORE INTO users_departments
                    (user_id, department_id, dept_role, joined_at)
                    VALUES (?, ?, ?, ?)
                ''', (user_id, dept_id, 'member', datetime.now().isoformat()))
        
        current_conn.commit()
        current_conn.close()
        backup_conn.close()
        
        print(f"✓ Restoration complete!")
        return True
        
    except Exception as e:
        print(f"❌ Error during restoration: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == '__main__':
    import sys
    import glob
    
    # First check current database
    if not check_database_health():
        print("\n❌ Database health check failed")
        
        # Try to restore from most recent backup
        backups = sorted(glob.glob('./backups/bot_data_*.db'), reverse=True)
        
        if backups:
            print(f"\n🔄 Attempting to restore from {backups[0]}...")
            if restore_from_backup(backups[0]):
                print("\n✓ Restoration successful! Running health check again...")
                check_database_health()
            else:
                print("\n❌ Restoration failed")
                sys.exit(1)
        else:
            print("\n❌ No backups found")
            sys.exit(1)
