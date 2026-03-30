#!/usr/bin/env python3
from database import *

# Check tables
conn = get_conn()
c = conn.cursor()
c.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [row[0] for row in c.fetchall()]
print('Tables:', ', '.join(tables))

# Check if users_departments exists
if 'users_departments' in tables:
    c.execute("SELECT COUNT(*) FROM users_departments")
    print('Users in departments:', c.fetchone()[0])
else:
    print('users_departments table does NOT exist')

# Check users
c.execute("SELECT COUNT(*) FROM users")
print('Total users:', c.fetchone()[0])

# Check users with departments_json
c.execute("SELECT user_id, first_name, departments_json FROM users LIMIT 5")
rows = c.fetchall()
print('\nSample users:')
for row in rows:
    print(f"  User {row[0]}: {row[1]}, departments_json: {row[2]}")

conn.close()
