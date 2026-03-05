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
            user_id    INTEGER PRIMARY KEY,
            username   TEXT,
            first_name TEXT,
            xp         INTEGER DEFAULT 0,
            joined_at  TEXT,
            is_banned  INTEGER DEFAULT 0,
            banned_at  TEXT
        )
    """)

    # Lightweight migration for existing databases.
    c.execute("PRAGMA table_info(users)")
    user_columns = {row[1] for row in c.fetchall()}
    if "is_banned" not in user_columns:
        c.execute("ALTER TABLE users ADD COLUMN is_banned INTEGER DEFAULT 0")
    if "banned_at" not in user_columns:
        c.execute("ALTER TABLE users ADD COLUMN banned_at TEXT")

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
        INSERT OR IGNORE INTO users (user_id, username, first_name, xp, joined_at)
        VALUES (?, ?, ?, 0, ?)
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
    c.execute("UPDATE users SET xp = xp + ? WHERE user_id=?", (amount, user_id))
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
    c.execute("SELECT * FROM users ORDER BY xp DESC LIMIT ?", (limit,))
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
        SELECT user_id, username, first_name, xp, joined_at, is_banned, banned_at
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
        SELECT user_id, username, first_name, xp, joined_at, is_banned, banned_at
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
    c.execute("SELECT COUNT(*) + 1 FROM users WHERE xp > ?", (user["xp"],))
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
