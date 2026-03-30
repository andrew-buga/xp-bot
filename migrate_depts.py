#!/usr/bin/env python3
"""Migrate users to users_departments table."""
from database import *
import json
from datetime import datetime

conn = get_conn()
c = conn.cursor()

# Create the users_departments table if it doesn't exist
c.execute("""
    CREATE TABLE IF NOT EXISTS users_departments (
        user_id INTEGER NOT NULL,
        department_id INTEGER NOT NULL,
        dept_role TEXT DEFAULT 'member',
        joined_at TEXT,
        PRIMARY KEY (user_id, department_id),
        FOREIGN KEY(user_id) REFERENCES users(user_id),
        FOREIGN KEY(department_id) REFERENCES departments(id)
    )
""")

print("✅ Created users_departments table")

# Get all users
c.execute("SELECT user_id, departments_json FROM users")
rows = c.fetchall()

migrated_count = 0
for user_id, departments_json in rows:
    # Parse departments_json if it exists
    if departments_json:
        try:
            dept_list = json.loads(departments_json)
            for dept_id in dept_list:
                c.execute(
                    """
                    INSERT OR IGNORE INTO users_departments 
                    (user_id, department_id, dept_role, joined_at)
                    VALUES (?, ?, 'member', ?)
                    """,
                    (user_id, dept_id, datetime.now().isoformat())
                )
                migrated_count += 1
        except json.JSONDecodeError:
            print(f"⚠️  User {user_id} has invalid departments_json: {departments_json}")

conn.commit()
conn.close()

print(f"✅ Migrated {migrated_count} user-department assignments")

# Check result
conn = get_conn()
c = conn.cursor()
c.execute("SELECT COUNT(*) FROM users_departments")
count = c.fetchone()[0]
c.execute("SELECT * FROM users_departments")
assignments = c.fetchall()
print(f"\n📊 Total assignments in users_departments: {count}")
if assignments:
    print("Assignments:")
    for row in assignments:
        print(f"  User {row[0]} → Department {row[1]} ({row[2]})")
conn.close()
