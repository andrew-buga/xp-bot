import sqlite3
from datetime import datetime

DB_PATH = "bot_data.db"


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id        INTEGER PRIMARY KEY,
            username      TEXT,
            first_name    TEXT,
            xp            INTEGER DEFAULT 0,
            total_xp      INTEGER DEFAULT 0,
            spendable_xp  INTEGER DEFAULT 0,
            joined_at     TEXT,
            is_banned     INTEGER DEFAULT 0,
            banned_at     TEXT
        )
    """)

    # Lightweight migration for existing databases.
    c.execute("PRAGMA table_info(users)")
    user_columns = {row[1] for row in c.fetchall()}
    if "is_banned" not in user_columns:
        c.execute("ALTER TABLE users ADD COLUMN is_banned INTEGER DEFAULT 0")
    if "banned_at" not in user_columns:
        c.execute("ALTER TABLE users ADD COLUMN banned_at TEXT")
    if "total_xp" not in user_columns:
        c.execute("ALTER TABLE users ADD COLUMN total_xp INTEGER DEFAULT 0")
        c.execute("UPDATE users SET total_xp = xp")
    if "spendable_xp" not in user_columns:
        c.execute("ALTER TABLE users ADD COLUMN spendable_xp INTEGER DEFAULT 0")
        c.execute("UPDATE users SET spendable_xp = xp")

    c.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            title       TEXT NOT NULL,
            description TEXT,
            xp_reward   INTEGER DEFAULT 10,
            is_active   INTEGER DEFAULT 1
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS submissions (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id      INTEGER,
            task_id      INTEGER,
            proof_text   TEXT,
            proof_file_id TEXT,
            status       TEXT DEFAULT 'pending',
            submitted_at TEXT,
            reviewed_at  TEXT,
            reviewer_id  INTEGER,
            FOREIGN KEY(user_id) REFERENCES users(user_id),
            FOREIGN KEY(task_id) REFERENCES tasks(id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key   TEXT PRIMARY KEY,
            value TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS shop (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL,
            description TEXT,
            price       INTEGER NOT NULL,
            is_active   INTEGER DEFAULT 1
        )
    """)

    # Стартові завдання (додаються лише якщо таблиця порожня)
    c.execute("SELECT COUNT(*) FROM tasks")
    if c.fetchone()[0] == 0:
        default_tasks = [
            ("Підписатися на канал",
             "Підпишись на наш Telegram-канал і надішли скріншот підписки.", 10),
            ("Поділитися постом",
             "Репостни будь-який пост з каналу до себе і надішли скріншот.", 20),
            ("Запросити друга",
             "Запроси друга до каналу — надішли його @username.", 30),
        ]
        c.executemany(
            "INSERT INTO tasks (title, description, xp_reward) VALUES (?,?,?)",
            default_tasks
        )

    conn.commit()
    conn.close()


# ---------- Users ----------

def register_user(user):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        INSERT OR IGNORE INTO users (user_id, username, first_name, xp, total_xp, spendable_xp, joined_at)
        VALUES (?, ?, ?, 0, 0, 0, ?)
    """, (user.id, user.username, user.first_name, datetime.now().isoformat()))
    c.execute("""
        UPDATE users SET username=?, first_name=? WHERE user_id=?
    """, (user.username, user.first_name, user.id))
    conn.commit()
    conn.close()


def get_user(user_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row


def is_user_banned(user_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT is_banned FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    return bool(row and row["is_banned"])


def add_xp(user_id, amount):
    conn = get_conn()
    c = conn.cursor()
    # Add XP to both balances
    c.execute("""
        UPDATE users SET
            xp = xp + ?,
            total_xp = total_xp + ?,
            spendable_xp = spendable_xp + ?
        WHERE user_id=?
    """, (amount, amount, amount, user_id))
    conn.commit()
    conn.close()


def spend_xp(user_id, price):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT spendable_xp FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    if not row or row[0] < price:
        conn.close()
        return False
    new_spendable = row[0] - price
    c.execute("UPDATE users SET spendable_xp=? WHERE user_id=?", (new_spendable, user_id))
    conn.commit()
    conn.close()
    return True


def admin_subtract_xp(user_id, amount):
    conn = get_conn()
    c = conn.cursor()
    # Subtract XP from both balances, but spendable_xp cannot go below zero
    c.execute("SELECT spendable_xp FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    spendable_xp = row[0] if row else 0
    new_spendable = max(0, spendable_xp - amount)
    c.execute("""
        UPDATE users SET
            xp = xp - ?,
            total_xp = total_xp - ?,
            spendable_xp = ?
        WHERE user_id=?
    """, (amount, amount, new_spendable, user_id))
    conn.commit()
    conn.close()


def ban_user(user_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "UPDATE users SET is_banned=1, banned_at=? WHERE user_id=?",
        (datetime.now().isoformat(), user_id),
    )
    changed = c.rowcount > 0
    conn.commit()
    conn.close()
    return changed


def unban_user(user_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "UPDATE users SET is_banned=0, banned_at=NULL WHERE user_id=?",
        (user_id,),
    )
    changed = c.rowcount > 0
    conn.commit()
    conn.close()
    return changed


def get_leaderboard(limit=10):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM users ORDER BY total_xp DESC LIMIT ?", (limit,))
    rows = c.fetchall()
    conn.close()
    return rows


def count_users():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    total = c.fetchone()[0]
    conn.close()
    return total


def list_users(limit=10, offset=0):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        """
        SELECT user_id, username, first_name, xp, total_xp, spendable_xp, joined_at, is_banned, banned_at
        FROM users
        ORDER BY joined_at DESC
        LIMIT ? OFFSET ?
        """,
        (limit, offset),
    )
    rows = c.fetchall()
    conn.close()
    return rows


def get_user_summary(user_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        """
        SELECT user_id, username, first_name, xp, total_xp, spendable_xp, joined_at, is_banned, banned_at
        FROM users
        WHERE user_id=?
        """,
        (user_id,),
    )
    row = c.fetchone()
    conn.close()
    return row


def get_user_rank(user_id):
    conn = get_conn()
    c = conn.cursor()
    user = get_user(user_id)
    if not user:
        return None, None
    c.execute("SELECT COUNT(*) + 1 FROM users WHERE total_xp > ?", (user["total_xp"],))
    rank = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM users")
    total = c.fetchone()[0]
    conn.close()
    return rank, total


# ---------- Tasks ----------

def get_tasks():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM tasks WHERE is_active=1")
    rows = c.fetchall()
    conn.close()
    return rows


def get_task(task_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM tasks WHERE id=?", (task_id,))
    row = c.fetchone()
    conn.close()
    return row


# ---------- Shop ----------

def add_product(name, description, price):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "INSERT INTO shop (name, description, price) VALUES (?, ?, ?)",
        (name, description, price)
    )
    product_id = c.lastrowid
    conn.commit()
    conn.close()
    return product_id


def update_product(product_id, name=None, description=None, price=None, is_active=None):
    conn = get_conn()
    c = conn.cursor()
    fields = []
    values = []
    if name is not None:
        fields.append("name=?")
        values.append(name)
    if description is not None:
        fields.append("description=?")
        values.append(description)
    if price is not None:
        fields.append("price=?")
        values.append(price)
    if is_active is not None:
        fields.append("is_active=?")
        values.append(is_active)
    values.append(product_id)
    if fields:
        c.execute(f"UPDATE shop SET {', '.join(fields)} WHERE id=?", values)
    conn.commit()
    conn.close()


def delete_product(product_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("DELETE FROM shop WHERE id=?", (product_id,))
    conn.commit()
    conn.close()


def list_products(active_only=True):
    conn = get_conn()
    c = conn.cursor()
    if active_only:
        c.execute("SELECT * FROM shop WHERE is_active=1")
    else:
        c.execute("SELECT * FROM shop")
    rows = c.fetchall()
    conn.close()
    return rows


def get_product(product_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM shop WHERE id=?", (product_id,))
    row = c.fetchone()
    conn.close()
    return row


def add_task(title, description, xp_reward):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "INSERT INTO tasks (title, description, xp_reward) VALUES (?,?,?)",
        (title, description, xp_reward)
    )
    task_id = c.lastrowid
    conn.commit()
    conn.close()
    return task_id


def delete_task(task_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("UPDATE tasks SET is_active=0 WHERE id=?", (task_id,))
    conn.commit()
    conn.close()


# ---------- Submissions ----------

def add_submission(user_id, task_id, proof_text, proof_file_id=None):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        INSERT INTO submissions
            (user_id, task_id, proof_text, proof_file_id, status, submitted_at)
        VALUES (?, ?, ?, ?, 'pending', ?)
    """, (user_id, task_id, proof_text, proof_file_id, datetime.now().isoformat()))
    sub_id = c.lastrowid
    conn.commit()
    conn.close()
    return sub_id


def get_submission(submission_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM submissions WHERE id=?", (submission_id,))
    row = c.fetchone()
    conn.close()
    return row


def review_submission(submission_id, status, reviewer_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        UPDATE submissions
        SET status=?, reviewed_at=?, reviewer_id=?
        WHERE id=?
    """, (status, datetime.now().isoformat(), reviewer_id, submission_id))
    conn.commit()
    conn.close()


def has_pending(user_id, task_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        SELECT id FROM submissions
        WHERE user_id=? AND task_id=? AND status='pending'
    """, (user_id, task_id))
    row = c.fetchone()
    conn.close()
    return row is not None


def has_approved(user_id, task_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        SELECT id FROM submissions
        WHERE user_id=? AND task_id=? AND status='approved'
    """, (user_id, task_id))
    row = c.fetchone()
    conn.close()
    return row is not None


def get_stats():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    users = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM submissions WHERE status='pending'")
    pending = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM submissions WHERE status='approved'")
    approved = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM tasks WHERE is_active=1")
    tasks = c.fetchone()[0]
    conn.close()
    return users, tasks, pending, approved


def get_setting(key, default=None):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key=?", (key,))
    row = c.fetchone()
    conn.close()
    if row is None:
        return default
    return row["value"]


def set_setting(key, value):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO settings (key, value)
        VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value
        """,
        (key, value),
    )
    conn.commit()
    conn.close()
