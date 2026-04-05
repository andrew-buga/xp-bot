import sqlite3

conn = sqlite3.connect('bot_data.db')
conn.row_factory = sqlite3.Row
c = conn.cursor()

print("=== DATABASE INTEGRITY REPORT ===\n")

# 1. Users with approved submissions but 0 departments
c.execute("""
    SELECT DISTINCT u.user_id, u.username, u.xp, u.total_xp, u.spendable_xp,
           COUNT(s.id) as approved_count
    FROM users u
    LEFT JOIN submissions s ON u.user_id = s.user_id AND s.status = 'approved'
    WHERE u.user_id NOT IN (
        SELECT DISTINCT user_id FROM users_departments
    )
    AND (u.total_xp > 0 OR u.username IS NOT NULL)
    GROUP BY u.user_id
    ORDER BY approved_count DESC
""")

users_no_depts = c.fetchall()
if users_no_depts:
    print("⚠️  USERS WITHOUT DEPARTMENTS (but have data):\n")
    for user in users_no_depts:
        print(f"  User {user['user_id']}: {user['username']}")
        print(f"    - Approved tasks: {user['approved_count']}")
        print(f"    - XP: {user['total_xp']} total, {user['spendable_xp']} spendable")
        print()
else:
    print("✅ All users with data have departments\n")

# 2. Users with submitted tasks
c.execute("""
    SELECT DISTINCT u.user_id, u.username, 
           COUNT(CASE WHEN s.status='submitted' THEN 1 END) as submitted,
           COUNT(CASE WHEN s.status='approved' THEN 1 END) as approved,
           COUNT(CASE WHEN s.status='rejected' THEN 1 END) as rejected
    FROM users u
    LEFT JOIN submissions s ON u.user_id = s.user_id
    WHERE s.id IS NOT NULL
    GROUP BY u.user_id
    ORDER BY u.user_id DESC
""")

print("=== USERS WITH SUBMISSIONS ===\n")
print(f"{'User ID':<12} {'Username':<20} {'Submitted':<10} {'Approved':<10} {'Rejected':<10}")
print("-" * 65)

for row in c.fetchall():
    username = row['username'] or "(No username)"
    print(f"{row['user_id']:<12} {username:<20} {row['submitted']:<10} {row['approved']:<10} {row['rejected']:<10}")

# 3. XP consistency check
print("\n=== XP CONSISTENCY CHECK ===\n")

c.execute("""
    SELECT u.user_id, u.username, u.xp, u.total_xp, u.spendable_xp,
           SUM(CASE WHEN s.status='approved' THEN t.xp_reward ELSE 0 END) as should_have
    FROM users u
    LEFT JOIN submissions s ON u.user_id = s.user_id
    LEFT JOIN tasks t ON s.task_id = t.id
    WHERE u.username IS NOT NULL OR u.total_xp > 0
    GROUP BY u.user_id
    HAVING u.total_xp != COALESCE(should_have, 0)
""")

inconsistencies = c.fetchall()
if inconsistencies:
    print("⚠️  XP INCONSISTENCIES FOUND:\n")
    for user in inconsistencies:
        print(f"  User {user['user_id']}: {user['username']}")
        print(f"    - Has: total_xp={user['total_xp']}, spendable_xp={user['spendable_xp']}")
        print(f"    - Should have: {user['should_have']} (from approved submissions)")
        print()
else:
    print("✅ All XP values are consistent with approved submissions\n")

# 4. Summary
c.execute("SELECT COUNT(*) as cnt FROM users")
total_users = c.fetchone()['cnt']

c.execute("SELECT COUNT(*) as cnt FROM users_departments")
dept_assignments = c.fetchone()['cnt']

c.execute("SELECT COUNT(*) as cnt FROM submissions WHERE status='approved'")
approved_total = c.fetchone()['cnt']

c.execute("SELECT COALESCE(SUM(t.xp_reward), 0) as total FROM submissions s JOIN tasks t ON s.task_id=t.id WHERE s.status='approved'")
xp_awarded_total = c.fetchone()['total']

c.execute("SELECT COALESCE(SUM(total_xp), 0) as total FROM users")
xp_in_db = c.fetchone()['total']

print("=== SUMMARY ===")
print(f"Total users: {total_users}")
print(f"Department assignments: {dept_assignments}")
print(f"Approved submissions: {approved_total}")
print(f"XP awarded (by tasks): {xp_awarded_total}")
print(f"XP in database: {xp_in_db}")

if xp_awarded_total == xp_in_db:
    print("\n✅ All XP is accounted for!")
else:
    print(f"\n⚠️  XP MISMATCH: {xp_in_db} in DB vs {xp_awarded_total} should be there")

conn.close()
