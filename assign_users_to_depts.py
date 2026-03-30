#!/usr/bin/env python3
"""Assign test users to departments."""
from database import *
from datetime import datetime

conn = get_conn()
c = conn.cursor()

# Get users
c.execute("SELECT user_id FROM users LIMIT 2")
user_ids = [row[0] for row in c.fetchall()]

if len(user_ids) >= 2:
    # Assign first user to IT (dept_id=5)
    c.execute(
        "INSERT OR IGNORE INTO users_departments (user_id, department_id, dept_role, joined_at) VALUES (?, ?, 'member', ?)",
        (user_ids[0], 5, datetime.now().isoformat())
    )
    print(f"✅ Assigned User {user_ids[0]} to IT department")
    
    # Assign second user to Communications (dept_id=4)
    c.execute(
        "INSERT OR IGNORE INTO users_departments (user_id, department_id, dept_role, joined_at) VALUES (?, ?, 'member', ?)",
        (user_ids[1], 4, datetime.now().isoformat())
    )
    print(f"✅ Assigned User {user_ids[1]} to Communications department")
    
    conn.commit()

# Show result
c.execute("""
    SELECT ud.user_id, ud.department_id, d.name, d.emoji, ud.dept_role
    FROM users_departments ud
    LEFT JOIN departments d ON ud.department_id = d.id
""")
rows = c.fetchall()
print(f"\n📊 Current assignments:")
for row in rows:
    print(f"  User {row[0]} → {row[3]} {row[2]} ({row[4]})")

conn.close()
