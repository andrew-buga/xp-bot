import sqlite3
from datetime import datetime, timedelta

DB_PATH = "bot_data.db"


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    c = conn.cursor()

    # ============ USERS TABLE ============
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id        INTEGER PRIMARY KEY,
            username       TEXT,
            first_name     TEXT,
            xp             INTEGER DEFAULT 0,
            total_xp       INTEGER DEFAULT 0,
            spendable_xp   INTEGER DEFAULT 0,
            joined_at      TEXT,
            is_banned      INTEGER DEFAULT 0,
            banned_at      TEXT,
            language       TEXT DEFAULT 'uk',
            department_id  INTEGER,
            is_verified    INTEGER DEFAULT 0,
            verified_at    TEXT,
            needs_recheck  INTEGER DEFAULT 0
        )
    """)

    # Lightweight migration for existing databases
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
    if "language" not in user_columns:
        c.execute("ALTER TABLE users ADD COLUMN language TEXT DEFAULT 'uk'")
    if "department_id" not in user_columns:
        c.execute("ALTER TABLE users ADD COLUMN department_id INTEGER")
    if "is_verified" not in user_columns:
        c.execute("ALTER TABLE users ADD COLUMN is_verified INTEGER DEFAULT 0")
    if "verified_at" not in user_columns:
        c.execute("ALTER TABLE users ADD COLUMN verified_at TEXT")
    if "needs_recheck" not in user_columns:
        c.execute("ALTER TABLE users ADD COLUMN needs_recheck INTEGER DEFAULT 0")

    # ============ DEPARTMENTS TABLE ============
    c.execute("""
        CREATE TABLE IF NOT EXISTS departments (
            id   INTEGER PRIMARY KEY,
            name TEXT UNIQUE NOT NULL,
            emoji TEXT
        )
    """)

    # Insert departments if empty
    c.execute("SELECT COUNT(*) FROM departments")
    if c.fetchone()[0] == 0:
        departments = [
            (1, "SMM та Медіа", "📱"),
            (2, "Фінанси", "💰"),
            (3, "Project Management", "🎉"),
            (4, "Комунікація", "🤝"),
            (5, "IT", "💻"),
        ]
        c.executemany("INSERT INTO departments (id, name, emoji) VALUES (?, ?, ?)", departments)

    # ============ TASKS TABLE ============
    c.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            title           TEXT NOT NULL,
            description     TEXT,
            xp_reward       INTEGER DEFAULT 10,
            is_active       INTEGER DEFAULT 1,
            difficulty_level TEXT DEFAULT 'easy',
            department_id   INTEGER,
            FOREIGN KEY(department_id) REFERENCES departments(id)
        )
    """)

    # Migrate old tasks table (add new columns if they don't exist)
    c.execute("PRAGMA table_info(tasks)")
    task_columns = {row[1] for row in c.fetchall()}
    
    if "difficulty_level" not in task_columns:
        c.execute("ALTER TABLE tasks ADD COLUMN difficulty_level TEXT DEFAULT 'easy'")
    if "department_id" not in task_columns:
        c.execute("ALTER TABLE tasks ADD COLUMN department_id INTEGER")

    # ============ SUBMISSIONS TABLE ============
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

    # ============ SETTINGS TABLE ============
    c.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key   TEXT PRIMARY KEY,
            value TEXT
        )
    """)

    # ============ SHOP TABLE ============
    c.execute("""
        CREATE TABLE IF NOT EXISTS shop (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL,
            description TEXT,
            price       INTEGER NOT NULL,
            is_active   INTEGER DEFAULT 1
        )
    """)

    # ============ INVENTORY TABLE ============
    c.execute("""
        CREATE TABLE IF NOT EXISTS inventory (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id      INTEGER NOT NULL,
            product_id   INTEGER NOT NULL,
            product_name TEXT NOT NULL,
            price_paid   INTEGER NOT NULL,
            bought_at    TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(user_id)
        )
    """)

    # ============ IDEAS TABLE (new) ============
    c.execute("""
        CREATE TABLE IF NOT EXISTS ideas (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL,
            text       TEXT NOT NULL,
            created_at TEXT,
            is_reviewed INTEGER DEFAULT 0,
            FOREIGN KEY(user_id) REFERENCES users(user_id)
        )
    """)

    # ============ INSERT 60+ TASKS IF TABLE IS EMPTY ============
    c.execute("SELECT COUNT(*) FROM tasks")
    if c.fetchone()[0] == 0:
        tasks = get_all_tasks_list()
        for title, description, xp, difficulty, dept_id in tasks:
            c.execute(
                "INSERT INTO tasks (title, description, xp_reward, difficulty_level, department_id) VALUES (?, ?, ?, ?, ?)",
                (title, description, xp, difficulty, dept_id)
            )

    conn.commit()
    conn.close()


def get_all_tasks_list():
    """
    Returns list of tuples: (title, description, xp_reward, difficulty_level, department_id)
    - difficulty_level: 'easy', 'medium', 'hard'
    - department_id: 1-5 (specific dept) or None (for all depts)
    """
    return [
        # ========== EASY - BASE (5 for all depts, dept_id=None) ==========
        ("Підписатися на всі соцмережі ATUR",
         "Підпишись на Instagram, TikTok, Facebook та Telegram канал ATUR і надішли скріншот. 🔗",
         20, "easy", None),
        ("Поставити лайк на 3 останніх пости ATUR",
         "Заходь на наш Instagram та поставляй лайки під 3 останніми постами. 👍",
         15, "easy", None),
        ("Запросити одного друга в Telegram",
         "Знаєш крутого друга? Запроси його в наш Telegram-канал ATUR. 🤝",
         20, "easy", None),
        ("Залишити коментар під постом ATUR",
         "Заходь на Instagram, знайди останній пост ATUR і напиши цікавий коментар. ✍️",
         15, "easy", None),
        ("Зробити репост поста ATUR",
         "Репостни будь-який пост ATUR у своїх соцмережах або сторіз. 📤",
         15, "easy", None),

        # ========== EASY - SMM та Медіа (2) ==========
        ("Надіслати ідею для поста",
         "Думаєш, що було б класно опублікувати? Напиши ідею в чат департаменту. 💡",
         10, "easy", 1),
        ("Зробити скріншот сторі ATUR і поділитися",
         "Зроби скріншот однієї з наших сторіз та покажи друзям. 📸",
         10, "easy", 1),

        # ========== EASY - Фінанси (2) ==========
        ("Знайти грант для молодіжних організацій",
         "Знайди 1 відкритий грант для молодіжних організацій і поділись посиланням у чаті. 💰",
         15, "easy", 2),
        ("Переглянути навчальне відео про грантрайтинг",
         "Подивись 15-хвилинне відео про грантрайтинг і напиши 3 висновки. 📚",
         10, "easy", 2),

        # ========== EASY - PM (2) ==========
        ("Запропонувати ідею для нового івенту",
         "Маєш хорошу ідею для нашого наступного заходу? Напиши її в чат департаменту. 🎉",
         10, "easy", 3),
        ("Знайти варіанти локацій для зустрічі",
         "Знайди та надішли 2 варіанти локацій для майбутньої зустрічі ATUR в своєму місті. 📍",
         15, "easy", 3),

        # ========== EASY - Комунікація (2) ==========
        ("Знайти новину про українську діаспору у Румунії",
         "Знайди актуальну новину про українців у Румунії і поділись в чаті. 📰",
         10, "easy", 4),
        ("Перекласти короткий пост ATUR",
         "Перекласти один короткий пост ATUR на румунську або англійську мову. 🌍",
         15, "easy", 4),

        # ========== EASY - IT (2) ==========
        ("Знайти баг або помилку на сайті ATUR",
         "Помітив помилку на нашому сайті? Повідоми нам про це з деталями. 🐛",
         10, "easy", 5),
        ("Запропонувати ідею для Telegram-бота Валєри",
         "Маєш ідею як покращити Валєру? Напиши просто і зрозуміло. 🤖",
         10, "easy", 5),

        # ========== MEDIUM - SMM та Медіа (5) ==========
        ("Написати текст-пост для Instagram",
         "Напиши готовий текст для поста Instagram про ATUR (мінімум 150 слів). ✍️",
         60, "medium", 1),
        ("Створити 3 варіанти сторі у Canva",
         "Спроєктуй 3 варіанти привітальних сторіз у Canva або аналогічному сервісі. 🎨",
         70, "medium", 1),
        ("Скласти контент-план на 1 тиждень",
         "Розроби контент-план на 7 днів з темами, форматами та основними ідеями для постів. 📋",
         80, "medium", 1),
        ("Відповісти на 10+ коментарів під постами",
         "Енергійно та дружньо відповідай на коментарі під постами ATUR від його імені. 💬",
         50, "medium", 1),
        ("Розробити нову рубрику для соцмереж",
         "Придумай нову рубрику з концепцією та напиши 3 приклади постів для неї. 🎯",
         75, "medium", 1),

        # ========== MEDIUM - Фінанси (5) ==========
        ("Скласти бюджет для невеликого івенту",
         "Спроєктуй бюджет для гіпотетичного невеликого івенту (до 500 євро). 💵",
         60, "medium", 2),
        ("Дослідити 3 потенційні гранти для ATUR",
         "Знайди 3 актуальні гранти для молодіжних організацій і оформи таблицю з дедлайнами. 📊",
         80, "medium", 2),
        ("Написати розділ для грантової заявки",
         "Напиши розділ 'Опис організації' для грантової заявки (300-400 слів). 📝",
         70, "medium", 2),
        ("Знайти потенційних спонсорів",
         "Знайди 2 потенційних спонсорів для ATUR і підготуй обґрунтування партнерства. 🤝",
         65, "medium", 2),
        ("Скласти шаблон фінансового звіту",
         "Розроби шаблон фінансового звіту для івенту з усіма необхідними категоріями. 📄",
         55, "medium", 2),

        # ========== MEDIUM - PM (5) ==========
        ("Скласти план-сценарій онлайн-зустрічі",
         "Напиши детальний план-сценарій для онлайн-зустрічі ATUR з часом та активностями. ⏰",
         70, "medium", 3),
        ("Знайти та зв'язатися зі спікерами",
         "Знайди та напиши листи 2 потенційним спікерам для нашого наступного заходу. 📧",
         75, "medium", 3),
        ("Створити Google Form для фідбеку",
         "Спроєктуй Google Form для збору фідбеку після нашого івенту (10-15 запитань). 📋",
         50, "medium", 3),
        ("Скласти логістичний план для заходу",
         "Розроби логістичний план офлайн-заходу: локація, час, обладнання, прилади. 🎪",
         80, "medium", 3),
        ("Організувати тімбілдинг активність",
         "Придумай та організуй цікаву тімбілдинг активність для групи 10-20 осіб. 🎮",
         85, "medium", 3),

        # ========== MEDIUM - Комунікація (5) ==========
        ("Написати офіційного листа до університету",
         "Напиши офіційного листа до університету від імені ATUR (правильна структура). 📬",
         70, "medium", 4),
        ("Скласти базу контактів партнерів",
         "Знайди та оформи контакти 5 потенційних партнерів (ВНЗ, НГО, мерія). 📇",
         60, "medium", 4),
        ("Підготувати прес-реліз про захід",
         "Напиши прес-реліз про найближчий захід ATUR (400-600 слів, журналістський стиль). 📰",
         75, "medium", 4),
        ("Перекласти офіційний документ ATUR",
         "Перекласти офіційний документ організації (UA → RO або EN) з збереженням змісту. 🔄",
         65, "medium", 4),
        ("Додати записи до CRM-бази партнерів",
         "Додай/онови 3 записи в CRM-базу партнерів з контактами та статусом協ації. 💾",
         50, "medium", 4),

        # ========== MEDIUM - IT (5) ==========
        ("Оновити розділ на сайті ATUR",
         "Онови або виправ один з розділів на сайті ATUR (контент, ремонт, оптимізація). 🔧",
         65, "medium", 5),
        ("Налаштувати аналітику для сторінки",
         "Налаштуй Google Analytics для однієї сторінки сайту і подай звіт про гієні. 📊",
         70, "medium", 5),
        ("Розробити UI/UX макет нової функції",
         "Спроєктуй UI/UX макет нової функції для сайту або Telegram-бота Валєри. 🎨",
         80, "medium", 5),
        ("Провести аудит доступів команди",
         "Переглянь та онови права доступу членів команди до сайту та інших систем. 🔐",
         60, "medium", 5),
        ("Написати ТЗ для нової функції Валєри",
         "Напиши технічне завдання (ТЗ) для нової функції в нашому Telegram-боті Валєри. 📋",
         75, "medium", 5),

        # ========== HARD - SMM та Медіа (4) ==========
        ("Зняти та змонтувати Reels/TikTok",
         "Зніми та змонтуй повноцінний Reels або TikTok для ATUR соцмереж (мін. 30 сек). 🎥",
         300, "hard", 1),
        ("Провести аналіз статистики соцмереж",
         "Проаналізуй статистику Instagram за місяць і подай детальний звіт з висновками. 📊",
         150, "hard", 1),
        ("Розробити гайдлайн фірмового стилю ATUR",
         "Напиши повний гайдлайн: кольори, шрифти, логотип, іконографія, шаблони дизайну. 📐",
         200, "hard", 1),
        ("Спроєктувати макет мерчу ATUR",
         "Спроєктуй дизайн мерчу (футболка, стікери, сумка) в фірмовому стилі ATUR. 👕",
         180, "hard", 1),

        # ========== HARD - Фінанси (4) ==========
        ("Написати повну грантову заявку",
         "Напиши грантову заявку від А до Я (від дослідження до фінального тексту). 📄",
         250, "hard", 2),
        ("Запустити краудфандинг для проєкту",
         "Розроби та запусти кампанію краудфандингу для конкретного проєкту ATUR. 💸",
         200, "hard", 2),
        ("Скласти річний бюджет організації",
         "Спроєктуй річний бюджет ATUR з усіма статтями доходів і видатків. 📊",
         220, "hard", 2),
        ("Подати документи для кампанії 3,5% податків",
         "Підготуй та подай всю документацію для участі в кампанії 3,5% португальських податків. 📑",
         150, "hard", 2),

        # ========== HARD - PM (4) ==========
        ("Організувати та провести повноцінний івент",
         "Організуй та проведи офлайн-захід ATUR від планування до закриття. 🎉",
         400, "hard", 3),
        ("Координувати волонтерів на івенті",
         "Буди on-site координатором на реальному івенті ATUR, керуй волонтерами і розписанням. 👥",
         350, "hard", 3),
        ("Підготувати пост-аналіз івенту",
         "Склади детальний звіт про івент: статистика, фідбек, аналіз, висновки та рекомендації. 📈",
         180, "hard", 3),
        ("Знайти локацію та підписати угоду",
         "Знайди локацію для великого заходу ATUR, домовись про умови та підпиши угоду. 🤝",
         200, "hard", 3),

        # ========== HARD - Комунікація (3) ==========
        ("Провести офіційну зустріч з партнером",
         "Організуй та проведи офіційну зустріч з представником ВНЗ, НГО або організації. 💼",
         200, "hard", 4),
        ("Налагодити офіційне партнерство",
         "З інціативи до підписання: напиши лист, проведи зустріч, підпиши меморандум взаємодії. 📜",
         250, "hard", 4),
        ("Перекласти на англійську або румунську",
         "Перекласти офіційний матеріал ATUR на англійську або румунську з професійним якістю. 🌍",
         150, "hard", 4),

        # ========== HARD - IT (4) ==========
        ("Розробити та задеплоїти нову фічу Валєри",
         "Розроби та реально задеплой нову функцію для нашого Telegram-бота Валєри. 💻",
         350, "hard", 5),
        ("Провести технічний аудит сайту ATUR",
         "Проаналізуй сайт ATUR: швидкість, SEO, безпеку, доступність - подай детальний звіт. 🔍",
         200, "hard", 5),
        ("Розробити нову сторінку сайту",
         "Спроєктуй та розроби нову функціональну сторінку або секцію на сайті ATUR. 🌐",
         280, "hard", 5),
        ("Інтегрувати нову систему в інфраструктуру",
         "Запровади нову систему (аналітика, форми, CRM, чат) в інфраструктуру ATUR. 🔗",
         300, "hard", 5),

        # ========== HARD - Shared/All (5) ==========
        ("Волонтерити 2 години на заході",
         "Пришли 2 години часу на реєстрації або логістиці одного з наших офлайн-заходів. ⏱️",
         300, "hard", None),
        ("Провести ігровий вечір для команди",
         "Організуй та проведи ігровий вечір для волонтерів ATUR (Skribbl, Gartic, Мафія). 🎲",
         400, "hard", None),
        ("Провести менторинг з новачком",
         "Зустрінься з новичком, розповіж про ATUR та допоможи адаптуватися до команди. 👥",
         150, "hard", None),
        ("Збірити плейлист української музики",
         "Збери якісний плейлист (2-3 години) української музики для офлайн-зустріч ATUR. 🎵",
         100, "hard", None),
        ("Організувати нетворкінг-сесію",
         "Організуй нетворкінг-сесію між ATUR та діаспорою в новому місті Румунії. 🌟",
         250, "hard", None),
    ]


# ============ USERS ----------

def register_user(user):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        INSERT OR IGNORE INTO users (user_id, username, first_name, xp, total_xp, spendable_xp, joined_at, language)
        VALUES (?, ?, ?, 0, 0, 0, ?, 'uk')
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


def get_user_language(user_id):
    """Get user's language preference"""
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT language FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row["language"] if row else "uk"


def set_user_language(user_id, language):
    """Save user's language preference"""
    conn = get_conn()
    c = conn.cursor()
    c.execute("UPDATE users SET language=? WHERE user_id=?", (language, user_id))
    conn.commit()
    conn.close()


def get_user_department(user_id):
    """Get user's department_id"""
    user = get_user(user_id)
    return user["department_id"] if user else None


def select_department(user_id, department_id):
    """Assign user to department after verification"""
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "UPDATE users SET department_id=? WHERE user_id=?",
        (department_id, user_id)
    )
    conn.commit()
    conn.close()


def mark_verified(user_id):
    """Mark user as verified (subscribed to channel)"""
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "UPDATE users SET is_verified=1, verified_at=?, needs_recheck=0 WHERE user_id=?",
        (datetime.now().isoformat(), user_id)
    )
    conn.commit()
    conn.close()


def mark_unverified(user_id):
    """Unverify user (if unsubscribed)"""
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "UPDATE users SET is_verified=0 WHERE user_id=?",
        (user_id,)
    )
    conn.commit()
    conn.close()


def set_needs_recheck(user_id):
    """Mark user for weekly recheck"""
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "UPDATE users SET needs_recheck=1 WHERE user_id=?",
        (user_id,)
    )
    conn.commit()
    conn.close()


def get_users_needing_recheck():
    """Get users who need weekly subscription recheck"""
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT user_id FROM users WHERE is_verified=1 AND (verified_at IS NULL OR verified_at < ?)", 
              (datetime.isoformat(datetime.now() - timedelta(days=7)),))
    rows = c.fetchall()
    conn.close()
    return [row["user_id"] for row in rows]


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


# ============ DEPARTMENTS ----------

def get_departments():
    """Get all departments"""
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM departments ORDER BY id")
    rows = c.fetchall()
    conn.close()
    return rows


def get_department(department_id):
    """Get specific department"""
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM departments WHERE id=?", (department_id,))
    row = c.fetchone()
    conn.close()
    return row


# ============ TASKS ----------

def get_tasks():
    """Get all active tasks (no filtering)"""
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM tasks WHERE is_active=1")
    rows = c.fetchall()
    conn.close()
    return rows


def get_tasks_by_difficulty(difficulty):
    """Get tasks filtered by difficulty (easy, medium, hard)"""
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM tasks WHERE is_active=1 AND difficulty_level=?", (difficulty,))
    rows = c.fetchall()
    conn.close()
    return rows


def get_tasks_filtered(difficulty, user_dept_id=None):
    """
    Get tasks filtered by difficulty and optionally by department.
    - For 'easy': returns all easy tasks (dept_id=None) + user's dept-specific easy tasks
    - For 'medium'/'hard': returns only user's department tasks
    """
    conn = get_conn()
    c = conn.cursor()
    
    if difficulty == "easy":
        # Easy: show base tasks (dept_id=NULL) + user's dept-specific tasks
        if user_dept_id:
            c.execute("""
                SELECT * FROM tasks 
                WHERE is_active=1 AND difficulty_level=?
                AND (department_id IS NULL OR department_id=?)
                ORDER BY id
            """, (difficulty, user_dept_id))
        else:
            c.execute("""
                SELECT * FROM tasks 
                WHERE is_active=1 AND difficulty_level=? AND department_id IS NULL
                ORDER BY id
            """, (difficulty,))
    else:
        # Medium/Hard: show only user's department tasks
        if user_dept_id:
            c.execute("""
                SELECT * FROM tasks 
                WHERE is_active=1 AND difficulty_level=? AND (department_id=? OR department_id IS NULL)
                ORDER BY id
            """, (difficulty, user_dept_id))
        else:
            c.execute("""
                SELECT * FROM tasks 
                WHERE is_active=1 AND difficulty_level=?
                ORDER BY id
            """, (difficulty,))
    
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


def add_task(title, description, xp_reward, difficulty_level="easy", department_id=None):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "INSERT INTO tasks (title, description, xp_reward, difficulty_level, department_id) VALUES (?,?,?,?,?)",
        (title, description, xp_reward, difficulty_level, department_id)
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


# ============ SUBMISSIONS ----------

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


# ============ SETTINGS ----------

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


# ============ SHOP ----------

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


# ============ INVENTORY ----------

def add_to_inventory(user_id, product_id, product_name, price_paid):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "INSERT INTO inventory (user_id, product_id, product_name, price_paid, bought_at) VALUES (?,?,?,?,?)",
        (user_id, product_id, product_name, price_paid, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


def get_inventory(user_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "SELECT product_name, price_paid, bought_at FROM inventory WHERE user_id=? ORDER BY id DESC",
        (user_id,),
    )
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


# ============ IDEAS (NEW) ----------

def add_idea(user_id, text):
    """User submits an idea"""
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "INSERT INTO ideas (user_id, text, created_at) VALUES (?, ?, ?)",
        (user_id, text, datetime.now().isoformat())
    )
    idea_id = c.lastrowid
    conn.commit()
    conn.close()
    return idea_id


def get_unreviewed_ideas():
    """Get all ideas that haven't been reviewed"""
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "SELECT * FROM ideas WHERE is_reviewed=0 ORDER BY created_at DESC"
    )
    rows = c.fetchall()
    conn.close()
    return rows


def mark_idea_reviewed(idea_id):
    """Mark idea as reviewed"""
    conn = get_conn()
    c = conn.cursor()
    c.execute("UPDATE ideas SET is_reviewed=1 WHERE id=?", (idea_id,))
    conn.commit()
    conn.close()
