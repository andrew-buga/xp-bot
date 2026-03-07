import logging
import time
from collections import defaultdict, deque
from functools import wraps

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from config import ADMIN_IDS, BOT_TOKEN
from database import (
    admin_subtract_xp,
    add_submission,
    add_task,
    add_xp,
    ban_user,
    count_users,
    delete_task,
    get_leaderboard,
    get_stats,
    get_submission,
    get_task,
    get_tasks,
    get_user,
    get_user_rank,
    get_user_summary,
    get_setting,
    has_approved,
    has_pending,
    init_db,
    is_user_banned,
    list_users,
    register_user,
    review_submission,
    set_setting,
    unban_user,
    add_product,
    update_product,
    delete_product,
    list_products,
    get_product,
    spend_xp,
)



logging.basicConfig(format="%(asctime)s | %(levelname)s | %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# Anti-flood defaults: max 8 updates per 10 seconds for one user.
RATE_LIMIT_WINDOW_SEC = 10
RATE_LIMIT_MAX_EVENTS = 8
RATE_LIMIT_NOTICE_COOLDOWN_SEC = 5
_user_events: dict[int, deque[float]] = defaultdict(deque)
_user_notice_ts: dict[int, float] = {}

ADMIN_USERS_PAGE_SIZE = 10
ADMIN_TASKS_PAGE_SIZE = 8

EDITABLE_TEXTS = {
    "welcome_text": {
        "label": "Привітання /start",
        "default": (
            "👋 Привіт, *{first_name}*!\n\n"
            "Виконуй завдання -> отримуй XP -> потрапляй у топ!\n\n"
            "📋 /tasks — список завдань\n"
            "⭐ /xp — мій профіль\n"
            "🏆 /leaderboard — таблиця лідерів\n"
            "🛒 /shop — магазин нагород\n"
            "❓ /help — як це працює"
        ),
    },
    "help_text": {
        "label": "Довідка /help",
        "default": (
            "📖 *Як це працює:*\n\n"
            "1) Переглянь завдання: /tasks\n"
            "2) Виконай завдання\n"
            "3) Натисни «📤 Здати завдання»\n"
            "4) Надішли підтвердження (скріншот або текст)\n"
            "5) Адмін перевірить і нарахує XP\n\n"
            "Щоб скасувати здачу: /cancel"
        ),
    },
}


def _is_admin(update: Update) -> bool:
    user = update.effective_user
    return bool(user and user.id in ADMIN_IDS)


def _normalize_text(text: str) -> str:
    # Recover strings that were decoded as cp1251 instead of utf-8.
    try:
        return text.encode("cp1251").decode("utf-8")
    except Exception:
        return text


def _btn(text: str, **kwargs) -> InlineKeyboardButton:
    return InlineKeyboardButton(_normalize_text(text), **kwargs)


def _normalize_markup(markup):
    if not markup:
        return markup
    if not isinstance(markup, InlineKeyboardMarkup):
        return markup

    rows = []
    for row in markup.inline_keyboard:
        new_row = []
        for button in row:
            new_row.append(
                _btn(
                    button.text,
                    callback_data=button.callback_data,
                    url=button.url,
                    switch_inline_query=button.switch_inline_query,
                    switch_inline_query_current_chat=button.switch_inline_query_current_chat,
                    callback_game=button.callback_game,
                    pay=button.pay,
                    login_url=button.login_url,
                    web_app=button.web_app,
                )
            )
        rows.append(new_row)
    return InlineKeyboardMarkup(rows)


async def _reply(update: Update, text: str, **kwargs):
    text = _normalize_text(text)
    if "reply_markup" in kwargs:
        kwargs["reply_markup"] = _normalize_markup(kwargs["reply_markup"])
    if update.effective_message:
        return await update.effective_message.reply_text(text, **kwargs)
    if update.callback_query and update.callback_query.message:
        return await update.callback_query.message.reply_text(text, **kwargs)
    return None


async def _query_answer(query, text: str | None = None, **kwargs):
    if text is None:
        return await query.answer(**kwargs)
    return await query.answer(_normalize_text(text), **kwargs)


async def _edit_message_text(query, text: str, **kwargs):
    kwargs["text"] = _normalize_text(text)
    if "reply_markup" in kwargs:
        kwargs["reply_markup"] = _normalize_markup(kwargs["reply_markup"])
    return await query.edit_message_text(**kwargs)


async def _edit_message_caption(query, caption: str, **kwargs):
    kwargs["caption"] = _normalize_text(caption)
    if "reply_markup" in kwargs:
        kwargs["reply_markup"] = _normalize_markup(kwargs["reply_markup"])
    return await query.edit_message_caption(**kwargs)


def _is_rate_limited(user_id: int) -> bool:
    now = time.monotonic()
    events = _user_events[user_id]

    while events and (now - events[0]) > RATE_LIMIT_WINDOW_SEC:
        events.popleft()

    if len(events) >= RATE_LIMIT_MAX_EVENTS:
        return True

    events.append(now)
    return False


async def _send_rate_limit_notice(update: Update) -> None:
    user = update.effective_user
    if not user:
        return

    now = time.monotonic()
    last_notice = _user_notice_ts.get(user.id, 0.0)
    if now - last_notice < RATE_LIMIT_NOTICE_COOLDOWN_SEC:
        return

    _user_notice_ts[user.id] = now
    text = "Забагато запитів. Спробуй ще раз через кілька секунд."

    if update.callback_query:
        try:
            await _query_answer(update.callback_query, text, show_alert=True)
        except Exception:
            pass
        return

    await _reply(update, text)


async def _send_ban_notice(update: Update) -> None:
    text = "Доступ до бота обмежено. Напиши адміну."
    if update.callback_query:
        try:
            await _query_answer(update.callback_query, text, show_alert=True)
        except Exception:
            pass
        return
    await _reply(update, text)


def rate_limit_user(func):
    @wraps(func)
    async def wrapper(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if not user:
            return await func(update, ctx)

        if user.id in ADMIN_IDS:
            return await func(update, ctx)

        if is_user_banned(user.id):
            await _send_ban_notice(update)
            return

        if _is_rate_limited(user.id):
            await _send_rate_limit_notice(update)
            return

        return await func(update, ctx)

    return wrapper


def admin_only(func):
    @wraps(func)
    async def wrapper(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not _is_admin(update):
            await _reply(update, "❌ Тільки для адміністраторів!")
            return
        return await func(update, ctx)
    return wrapper


# ---------- Shop ----------

@rate_limit_user
async def cmd_shop(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    register_user(user)
    products = list_products()
    if not products:
        await _reply(update, "🛒 Магазин порожній. Зазирни пізніше!")
        return
    await _reply(update, "🛒 *Магазин нагород*", parse_mode="Markdown")
    for product in products:
        text = (
            f"🎁 *{product['name']}*\n"
            f"{product['description']}\n"
            f"💸 Ціна: *{product['price']} XP*"
        )
        btn = _btn("Купити", callback_data=f"shop_buy_{product['id']}")
        await _reply(update, text, reply_markup=InlineKeyboardMarkup([[btn]]), parse_mode="Markdown")


async def handle_shop_buy(query, user_id, product_id):
    product = get_product(product_id)
    if not product or not product['is_active']:
        await _query_answer(query, "❌ Товар недоступний", show_alert=True)
        return
    db_user = get_user(user_id)
    if db_user['spendable_xp'] < product['price']:
        await _query_answer(query, "❌ Недостатньо XP для покупки", show_alert=True)
        return
    success = spend_xp(user_id, product['price'])
    if success:
        await _query_answer(query, f"✅ Куплено: {product['name']}!", show_alert=True)
    else:
        await _query_answer(query, "❌ Помилка покупки", show_alert=True)


async def shop_callback_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user = update.effective_user
    if data.startswith("shop_buy_"):
        product_id = int(data.split("_")[-1])
        await handle_shop_buy(query, user.id, product_id)


@admin_only
@rate_limit_user
async def cmd_addproduct(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        price = int(ctx.args[0])
        name = ctx.args[1]
        description = " ".join(ctx.args[2:])
        if not name or price <= 0:
            raise ValueError
    except (IndexError, ValueError):
        await _reply(update, "❌ Формат: /addproduct <ціна> <назва> <опис>")
        return
    product_id = add_product(name, description, price)
    await _reply(update, f"✅ Товар #{product_id} додано: {name} ({price} XP)")


@admin_only
@rate_limit_user
async def cmd_delproduct(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        product_id = int(ctx.args[0])
        delete_product(product_id)
        await _reply(update, f"✅ Товар #{product_id} видалено.")
    except (IndexError, ValueError):
        await _reply(update, "❌ Формат: /delproduct <product_id>")


@admin_only
@rate_limit_user
async def cmd_editproduct(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        product_id = int(ctx.args[0])
        price = int(ctx.args[1])
        name = ctx.args[2]
        description = " ".join(ctx.args[3:])
        update_product(product_id, name=name, description=description, price=price)
        await _reply(update, f"✅ Товар #{product_id} оновлено: {name} ({price} XP)")
    except (IndexError, ValueError):
        await _reply(update, "❌ Формат: /editproduct <product_id> <ціна> <назва> <опис>")


def _admin_menu_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [_btn("➕ Додати завдання", callback_data="a:add")],
            [_btn("🗑 Видалити завдання", callback_data="a:dellist:0")],
            [_btn("👥 Користувачі", callback_data="a:users:0")],
            [_btn("🎁 Нарахувати XP", callback_data="a:xp")],
            [_btn("📊 Статистика", callback_data="a:stats")],
            [_btn("🛒 Магазин товарів", callback_data="a:shop_list")],
            [_btn("🧩 Редагувати інфо бота", callback_data="be:menu")],
        ]
    )


def _display_name(row) -> str:
    if row["username"]:
        return f"@{row['username']}"
    if row["first_name"]:
        return row["first_name"]
    return f"User{row['user_id']}"


def _get_text_setting(key: str, **fmt) -> str:
    meta = EDITABLE_TEXTS[key]
    raw = get_setting(key, meta["default"])
    try:
        return raw.format(**fmt)
    except Exception:
        return raw


def _bot_infoedit_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [_btn("✍️ Змінити привітання /start", callback_data="be:edit:welcome_text")],
            [_btn("✍️ Змінити довідку /help", callback_data="be:edit:help_text")],
            [_btn("👁️ Переглянути поточні тексти", callback_data="be:preview")],
            [_btn("ℹ️ Що змінюється тільки через BotFather", callback_data="be:limits")],
            [_btn("⬅ В адмін-меню", callback_data="a:menu")],
        ]
    )


def _wizard(ctx: ContextTypes.DEFAULT_TYPE) -> dict | None:
    return ctx.user_data.get("admin_wizard")


def _clear_wizard(ctx: ContextTypes.DEFAULT_TYPE) -> None:
    ctx.user_data.pop("admin_wizard", None)


async def _wizard_prompt(ctx: ContextTypes.DEFAULT_TYPE, chat_id: int, text: str):
    msg = await ctx.bot.send_message(chat_id=chat_id, text=_normalize_text(text), parse_mode="Markdown")
    wizard = _wizard(ctx)
    if wizard is not None:
        wizard.setdefault("bot_prompt_ids", []).append(msg.message_id)


async def _cleanup_wizard_prompts(ctx: ContextTypes.DEFAULT_TYPE, chat_id: int) -> None:
    wizard = _wizard(ctx)
    if not wizard:
        return

    for msg_id in wizard.get("bot_prompt_ids", []):
        try:
            await ctx.bot.delete_message(chat_id=chat_id, message_id=msg_id)
        except Exception:
            pass


@rate_limit_user
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    register_user(user)
    text = _get_text_setting("welcome_text", first_name=user.first_name or "друже")
    await _reply(update, text, parse_mode="Markdown")


@rate_limit_user
async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await _reply(update, _get_text_setting("help_text"), parse_mode="Markdown")


@rate_limit_user
async def cmd_tasks(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    register_user(user)
    tasks = get_tasks()

    if not tasks:
        await _reply(update, "😕 Наразі завдань немає. Зазирни пізніше!")
        return

    await _reply(update, "📋 *Список завдань:*", parse_mode="Markdown")

    for task in tasks:
        done = has_approved(user.id, task["id"])
        pending = has_pending(user.id, task["id"])

        if done:
            badge = " ✅"
        elif pending:
            badge = " ⏳"
        else:
            badge = ""

        text = (
            f"📌 *{task['title']}*{badge}\n"
            f"{task['description']}\n"
            f"💎 Нагорода: *{task['xp_reward']} XP*"
        )

        if done:
            btn = _btn("✅ Виконано", callback_data="noop")
        elif pending:
            btn = _btn("⏳ На перевірці", callback_data="noop")
        else:
            btn = _btn("📤 Здати завдання", callback_data=f"submit_{task['id']}")

        await _reply(update, text, reply_markup=InlineKeyboardMarkup([[btn]]), parse_mode="Markdown")


@rate_limit_user
async def cmd_xp(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    register_user(user)
    db_user = get_user(user.id)
    rank, total = get_user_rank(user.id)

    await _reply(
        update,
        (
            f"👤 *Твій профіль {user.first_name}*\n\n"
            f"🏆 Загальний рейтинг (Leaderboard): *{db_user['total_xp']} XP*\n"
            f"💰 Доступно для витрат у Магазині: *{db_user['spendable_xp']} XP*\n"
            f"📊 Місце: *#{rank}* з {total}"
        ),
        parse_mode="Markdown",
    )


@rate_limit_user
async def cmd_leaderboard(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    top = get_leaderboard()

    if not top:
        await _reply(update, "🏆 Таблиця порожня. Будь першим!")
        return

    medals = ["🥇", "🥈", "🥉"]
    lines = ["🏆 *Таблиця лідерів* (кумулятивний XP)\n"]
    for i, user in enumerate(top):
        icon = medals[i] if i < 3 else f"{i + 1}."
        lines.append(f"{icon} {_display_name(user)} — *{user['total_xp']} XP*")

    await _reply(update, "\n".join(lines), parse_mode="Markdown")


@rate_limit_user
async def cmd_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    had_submission = bool(ctx.user_data.pop("submitting_task_id", None))
    had_wizard = bool(ctx.user_data.pop("admin_wizard", None))

    if had_submission or had_wizard:
        await _reply(update, "❌ Поточну дію скасовано.")
    else:
        await _reply(update, "Немає активної дії для скасування.")


@admin_only
@rate_limit_user
async def cmd_admin(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    _clear_wizard(ctx)
    await _reply(update, "🛠 *Адмін-панель*", reply_markup=_admin_menu_markup(), parse_mode="Markdown")


@admin_only
@rate_limit_user
async def cmd_bot_infoedit(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    _clear_wizard(ctx)
    await _reply(update, "🧩 *Редактор інформації бота*", reply_markup=_bot_infoedit_markup(), parse_mode="Markdown")


@admin_only
@rate_limit_user
async def cmd_help_admin(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await _reply(
        update,
        (
            "🛠 *Admin Help*\n\n"
            "`/admin` — відкрити адмін-меню (кнопки).\n"
            "`/bot_infoedit` — змінити тексти /start і /help.\n"
            "`/help_admin` — ця довідка.\n\n"
            "*Legacy команди:*\n"
            "`/addtask <XP> <назва> | <опис>` — додати задачу.\n"
            "`/deltask <task_id>` — деактивувати задачу.\n"
            "`/givexp <user_id> <amount>` — нарахувати/зняти XP.\n"
            "`/stats` — загальна статистика.\n"
            "`/cancel` — скасувати активний wizard.\n\n"
            "*В адмін-меню також є:*\n"
            "• Керування користувачами (перегляд, ban/unban)\n"
            "• Покрокове додавання задач\n"
            "• Покрокове нарахування XP"
        ),
        parse_mode="Markdown",
    )


@admin_only
@rate_limit_user
async def cmd_addtask(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    raw = " ".join(ctx.args)
    try:
        xp_str, rest = raw.split(" ", 1)
        xp = int(xp_str)
        title, _, description = rest.partition("|")
        title = title.strip()
        description = description.strip()
        if not title or xp <= 0:
            raise ValueError
    except ValueError:
        await _reply(
            update,
            "❌ Формат: /addtask <XP> <назва> | <опис>\n"
            "Приклад: /addtask 50 Написати відгук | Напиши відгук про бот",
        )
        return

    task_id = add_task(title, description, xp)
    await _reply(update, f"✅ Завдання #{task_id} додано!\n📌 {title}\n💎 {xp} XP")


@admin_only
@rate_limit_user
async def cmd_deltask(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        task_id = int(ctx.args[0])
        delete_task(task_id)
        await _reply(update, f"✅ Завдання #{task_id} деактивовано.")
    except (IndexError, ValueError):
        await _reply(update, "❌ Формат: /deltask <task_id>")


@admin_only
@rate_limit_user
async def cmd_givexp(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        uid = int(ctx.args[0])
        amount = int(ctx.args[1])
        if amount >= 0:
            add_xp(uid, amount)
            await _reply(update, f"✅ Нараховано {amount} XP -> {uid}")
        else:
            admin_subtract_xp(uid, -amount)
            await _reply(update, f"✅ Знято {-amount} XP -> {uid}")
    except (IndexError, ValueError):
        await _reply(update, "❌ Формат: /givexp <user_id> <кількість>")


@admin_only
@rate_limit_user
async def cmd_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    users, tasks, pending, approved = get_stats()
    await _reply(
        update,
        (
            "📊 *Статистика*\n\n"
            f"👥 Користувачів: {users}\n"
            f"📋 Активних завдань: {tasks}\n"
            f"⏳ На перевірці: {pending}\n"
            f"✅ Схвалено: {approved}"
        ),
        parse_mode="Markdown",
    )


def _render_task_page(page: int) -> tuple[str, InlineKeyboardMarkup]:
    tasks = get_tasks()
    total_pages = max(1, (len(tasks) + ADMIN_TASKS_PAGE_SIZE - 1) // ADMIN_TASKS_PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    start = page * ADMIN_TASKS_PAGE_SIZE
    chunk = tasks[start : start + ADMIN_TASKS_PAGE_SIZE]

    lines = ["🗑 *Видалення завдань*", "Натисни на завдання для деактивації.", ""]
    rows = []

    for task in chunk:
        lines.append(f"#{task['id']} — {task['title']} ({task['xp_reward']} XP)")
        rows.append(
            [
                _btn(
                    f"Видалити #{task['id']}",
                    callback_data=f"a:del:{task['id']}:{page}",
                )
            ]
        )

    nav = []
    if page > 0:
        nav.append(_btn("◀ Prev", callback_data=f"a:dellist:{page - 1}"))
    if page < total_pages - 1:
        nav.append(_btn("Next ▶", callback_data=f"a:dellist:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([_btn("⬅ В меню", callback_data="a:menu")])

    return "\n".join(lines), InlineKeyboardMarkup(rows)


def _render_user_page(page: int) -> tuple[str, InlineKeyboardMarkup]:
    total = count_users()
    total_pages = max(1, (total + ADMIN_USERS_PAGE_SIZE - 1) // ADMIN_USERS_PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))

    users = list_users(limit=ADMIN_USERS_PAGE_SIZE, offset=page * ADMIN_USERS_PAGE_SIZE)
    lines = [f"👥 *Користувачі* (сторінка {page + 1}/{total_pages})", ""]
    rows = []

    if not users:
        lines.append("Немає користувачів.")
    else:
        for user in users:
            ban_mark = "🚫" if user["is_banned"] else ""
            lines.append(
                f"`{user['user_id']}` | {_display_name(user)} | 🏆 {user['total_xp']} XP | 💰 {user['spendable_xp']} XP {ban_mark}"
            )
            rows.append([_btn(f"Деталі {user['user_id']}", callback_data=f"a:ud:{user['user_id']}:{page}")])

    nav = []
    if page > 0:
        nav.append(_btn("◀ Prev", callback_data=f"a:users:{page - 1}"))
    if page < total_pages - 1:
        nav.append(_btn("Next ▶", callback_data=f"a:users:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([_btn("⬅ В меню", callback_data="a:menu")])

    return "\n".join(lines), InlineKeyboardMarkup(rows)


def _render_user_detail(user_id: int, page: int) -> tuple[str, InlineKeyboardMarkup] | tuple[None, None]:
    user = get_user_summary(user_id)
    if not user:
        return None, None

    status = "banned" if user["is_banned"] else "active"
    lines = [
        "👤 *Картка користувача*",
        f"ID: `{user['user_id']}`",
        f"Username: {_display_name(user)}",
        f"Name: {user['first_name'] or '-'}",
        f"Joined: {user['joined_at'] or '-'}",
        f"🏆 Загальний XP: {user['total_xp']}",
        f"💰 Доступний XP: {user['spendable_xp']}",
        f"Status: *{status}*",
    ]

    if user["is_banned"]:
        action_btn = _btn("✅ Unban", callback_data=f"a:unban:{user['user_id']}:{page}")
    else:
        action_btn = _btn("🚫 Ban", callback_data=f"a:ban:{user['user_id']}:{page}")

    markup = InlineKeyboardMarkup(
        [[action_btn], [_btn("⬅ До списку", callback_data=f"a:users:{page}")]]
    )
    return "\n".join(lines), markup


def _render_shop_admin() -> tuple[str, InlineKeyboardMarkup]:
    products = list_products(active_only=False)
    lines = ["🛒 *Магазин товарів* (адмін)\n"]
    rows = []

    if not products:
        lines.append("_Товарів ще немає. Натисни \"Додати товар\"._")
    else:
        for p in products:
            status = "✅" if p["is_active"] else "🔴"
            lines.append(f"{status} #{p['id']} — *{p['name']}* ({p['price']} XP)")
            toggle_icon = "🔴 Деакт." if p["is_active"] else "✅ Акт."
            rows.append([
                _btn(f"✏️ Ред.", callback_data=f"a:shop_edit:{p['id']}"),
                _btn(toggle_icon, callback_data=f"a:shop_toggle:{p['id']}"),
                _btn(f"🗑 Вид.", callback_data=f"a:shop_del:{p['id']}"),
            ])

    rows.append([_btn("➕ Додати товар", callback_data="a:shop_add")])
    rows.append([_btn("⬅ В меню", callback_data="a:menu")])
    return "\n".join(lines), InlineKeyboardMarkup(rows)


async def _start_admin_wizard(update: Update, ctx: ContextTypes.DEFAULT_TYPE, wizard_type: str):
    chat_id = update.effective_chat.id
    if wizard_type == "add_task":
        ctx.user_data["admin_wizard"] = {
            "type": "add_task",
            "step": "title",
            "payload": {},
            "bot_prompt_ids": [],
        }
        await _wizard_prompt(ctx, chat_id, "📝 Введи *назву* завдання:")
        return

    if wizard_type == "give_xp":
        ctx.user_data["admin_wizard"] = {
            "type": "give_xp",
            "step": "user_id",
            "payload": {},
            "bot_prompt_ids": [],
        }
        await _wizard_prompt(ctx, chat_id, "🎯 Введи *user_id* користувача:")
        return

    if wizard_type == "add_product":
        ctx.user_data["admin_wizard"] = {
            "type": "add_product",
            "step": "name",
            "payload": {},
            "bot_prompt_ids": [],
        }
        await _wizard_prompt(ctx, chat_id, "🏷 Введи *назву* товару:")
        return

    if wizard_type.startswith("edit_product:"):
        product_id = int(wizard_type.split(":")[1])
        product = get_product(product_id)
        if not product:
            return
        ctx.user_data["admin_wizard"] = {
            "type": "edit_product",
            "step": "name",
            "payload": {"product_id": product_id},
            "bot_prompt_ids": [],
        }
        await _wizard_prompt(
            ctx,
            chat_id,
            f"✏️ Редагування товару #{product_id}: *{product['name']}*\n\n"
            f"🏷 Введи нову *назву* (або «.» щоб залишити поточну: {product['name']}):",
        )
        return

    if wizard_type.startswith("edit_text:"):
        setting_key = wizard_type.split(":", 1)[1]
        meta = EDITABLE_TEXTS.get(setting_key)
        if not meta:
            return
        ctx.user_data["admin_wizard"] = {
            "type": "edit_text",
            "step": "value",
            "payload": {"key": setting_key},
            "bot_prompt_ids": [],
        }
        await _wizard_prompt(
            ctx,
            chat_id,
            f"✍️ Введи новий текст для *{meta['label']}*.\n\n"
            "Можна кілька абзаців. Щоб скасувати — /cancel",
        )


@admin_only
async def _handle_admin_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data

    if data == "a:menu":
        _clear_wizard(ctx)
        await _edit_message_text(query, "🛠 *Адмін-панель*", reply_markup=_admin_menu_markup(), parse_mode="Markdown")
        return

    if data == "a:add":
        await _start_admin_wizard(update, ctx, "add_task")
        await _query_answer(query, "Майстер додавання запущено")
        return

    if data.startswith("a:dellist:"):
        page = int(data.split(":")[2])
        text, markup = _render_task_page(page)
        await _edit_message_text(query, text=text, reply_markup=markup, parse_mode="Markdown")
        return

    if data.startswith("a:del:"):
        _, _, task_id_str, page_str = data.split(":")
        delete_task(int(task_id_str))
        text, markup = _render_task_page(int(page_str))
        await _edit_message_text(query, text=f"✅ Завдання #{task_id_str} деактивовано.\n\n{text}", reply_markup=markup, parse_mode="Markdown")
        return

    if data.startswith("a:users:"):
        page = int(data.split(":")[2])
        text, markup = _render_user_page(page)
        await _edit_message_text(query, text=text, reply_markup=markup, parse_mode="Markdown")
        return

    if data.startswith("a:ud:"):
        _, _, user_id_str, page_str = data.split(":")
        text, markup = _render_user_detail(int(user_id_str), int(page_str))
        if not text:
            await _query_answer(query, "Користувача не знайдено", show_alert=True)
            return
        await _edit_message_text(query, text=text, reply_markup=markup, parse_mode="Markdown")
        return

    if data.startswith("a:ban:"):
        _, _, user_id_str, page_str = data.split(":")
        if int(user_id_str) == query.from_user.id:
            await _query_answer(query, "Не можна забанити самого себе.", show_alert=True)
            return
        ok = ban_user(int(user_id_str))
        if not ok:
            await _query_answer(query, "Користувача не знайдено", show_alert=True)
            return
        text, markup = _render_user_detail(int(user_id_str), int(page_str))
        await _edit_message_text(query, text=f"🚫 Користувача забанено.\n\n{text}", reply_markup=markup, parse_mode="Markdown")
        return

    if data.startswith("a:unban:"):
        _, _, user_id_str, page_str = data.split(":")
        ok = unban_user(int(user_id_str))
        if not ok:
            await _query_answer(query, "Користувача не знайдено", show_alert=True)
            return
        text, markup = _render_user_detail(int(user_id_str), int(page_str))
        await _edit_message_text(query, text=f"✅ Бан знято.\n\n{text}", reply_markup=markup, parse_mode="Markdown")
        return

    if data == "a:stats":
        users, tasks, pending, approved = get_stats()
        await _edit_message_text(query, 
            text=(
                "📊 *Статистика*\n\n"
                f"👥 Користувачів: {users}\n"
                f"📋 Активних завдань: {tasks}\n"
                f"⏳ На перевірці: {pending}\n"
                f"✅ Схвалено: {approved}"
            ),
            reply_markup=InlineKeyboardMarkup([[_btn("⬅ В меню", callback_data="a:menu")]]),
            parse_mode="Markdown",
        )
        return

    if data == "a:xp":
        await _start_admin_wizard(update, ctx, "give_xp")
        await _query_answer(query, "Майстер нарахування XP запущено")
        return

    if data == "a:shop_list":
        text, markup = _render_shop_admin()
        await _edit_message_text(query, text=text, reply_markup=markup, parse_mode="Markdown")
        return

    if data == "a:shop_add":
        await _start_admin_wizard(update, ctx, "add_product")
        await _query_answer(query, "Майстер додавання товару запущено")
        return

    if data.startswith("a:shop_del:"):
        product_id = int(data.split(":")[2])
        delete_product(product_id)
        text, markup = _render_shop_admin()
        await _edit_message_text(query, text=f"🗑 Товар #{product_id} видалено.\n\n{text}", reply_markup=markup, parse_mode="Markdown")
        return

    if data.startswith("a:shop_toggle:"):
        product_id = int(data.split(":")[2])
        product = get_product(product_id)
        if product:
            update_product(product_id, is_active=not product["is_active"])
        text, markup = _render_shop_admin()
        await _edit_message_text(query, text=text, reply_markup=markup, parse_mode="Markdown")
        return

    if data.startswith("a:shop_edit:"):
        product_id = int(data.split(":")[2])
        await _start_admin_wizard(update, ctx, f"edit_product:{product_id}")
        await _query_answer(query, "Майстер редагування товару запущено")
        return

    if data == "be:menu":
        _clear_wizard(ctx)
        await _edit_message_text(query, 
            text="🧩 *Редактор інформації бота*",
            reply_markup=_bot_infoedit_markup(),
            parse_mode="Markdown",
        )
        return

    if data.startswith("be:edit:"):
        setting_key = data.split(":", 2)[2]
        if setting_key not in EDITABLE_TEXTS:
            await _query_answer(query, "Невідома опція", show_alert=True)
            return
        await _start_admin_wizard(update, ctx, f"edit_text:{setting_key}")
        await _query_answer(query, "Режим редагування увімкнено")
        return

    if data == "be:preview":
        welcome_preview = _get_text_setting("welcome_text", first_name="Ім'я")
        help_preview = _get_text_setting("help_text")
        text = (
            "*Поточні тексти*\n\n"
            "*/start:*\n"
            f"{welcome_preview}\n\n"
            "*/help:*\n"
            f"{help_preview}"
        )
        await _edit_message_text(query, text=text, reply_markup=_bot_infoedit_markup(), parse_mode="Markdown")
        return

    if data == "be:limits":
        text = (
            "*Через це меню можна змінити:*\n"
            "• текст /start\n"
            "• текст /help\n\n"
            "*Тільки через @BotFather:*\n"
            "• фото бота\n"
            "• username та ім'я бота\n"
            "• about/description у профілі бота\n"
            "• токен бота"
        )
        await _edit_message_text(query, text=text, reply_markup=_bot_infoedit_markup(), parse_mode="Markdown")
        return


@rate_limit_user
async def on_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await _query_answer(query)
    data = query.data

    if data == "noop":
        return

    if data.startswith("a:") or data.startswith("be:"):
        await _handle_admin_callback(update, ctx)
        return

    if data.startswith("submit_"):
        task_id = int(data.split("_", 1)[1])
        user = query.from_user
        register_user(user)

        if has_approved(user.id, task_id):
            await _query_answer(query, "✅ Ти вже виконав це завдання!", show_alert=True)
            return
        if has_pending(user.id, task_id):
            await _query_answer(query, "⏳ Твоя відповідь вже на перевірці!", show_alert=True)
            return

        task = get_task(task_id)
        ctx.user_data["submitting_task_id"] = task_id

        await query.message.reply_text(
            (
                f"📤 *Здача: {task['title']}*\n\n"
                "Надішли підтвердження виконання:\n"
                "• 📸 Скріншот\n"
                "• 📝 Або текстовий опис\n\n"
                "_Щоб скасувати — /cancel_"
            ),
            parse_mode="Markdown",
        )
        return

    if data.startswith("approve_") or data.startswith("reject_"):
        if query.from_user.id not in ADMIN_IDS:
            await _query_answer(query, "❌ Тільки для адмінів!", show_alert=True)
            return

        action, sub_id_str = data.split("_", 1)
        sub_id = int(sub_id_str)
        sub = get_submission(sub_id)

        if not sub:
            await _query_answer(query, "❌ Заявку не знайдено.", show_alert=True)
            return
        if sub["status"] != "pending":
            await _query_answer(query, "⚠️ Вже оброблено.", show_alert=True)
            return

        new_status = "approved" if action == "approve" else "rejected"
        review_submission(sub_id, new_status, query.from_user.id)

        task = get_task(sub["task_id"])
        admin_tag = f"@{query.from_user.username}" if query.from_user.username else query.from_user.first_name

        if action == "approve":
            add_xp(sub["user_id"], task["xp_reward"])
            result_icon = "✅ Схвалено"
            user_msg = (
                f"🎉 *Завдання підтверджено!*\n\n"
                f"✅ «{task['title']}» — зараховано!\n"
                f"💎 +{task['xp_reward']} XP нараховано!\n\n"
                f"Переглянь профіль: /xp"
            )
        else:
            result_icon = "❌ Відхилено"
            user_msg = (
                f"❌ *Завдання не прийнято*\n\n"
                f"«{task['title']}» — відхилено.\n"
                f"Спробуй ще раз! /tasks"
            )

        try:
            await ctx.bot.send_message(sub["user_id"], _normalize_text(user_msg), parse_mode="Markdown")
        except Exception:
            pass

        suffix = f"\n\n{result_icon} адміном {admin_tag}"
        try:
            if query.message.caption:
                await _edit_message_caption(query, 
                    caption=query.message.caption + suffix,
                    parse_mode="Markdown",
                    reply_markup=None,
                )
            else:
                await _edit_message_text(query, 
                    text=query.message.text + suffix,
                    parse_mode="Markdown",
                    reply_markup=None,
                )
        except Exception:
            pass


async def _process_proof(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    task_id = ctx.user_data.get("submitting_task_id")
    if not task_id:
        return

    user = update.effective_user
    task = get_task(task_id)

    if not task:
        await _reply(update, "❌ Завдання не знайдено. /tasks")
        ctx.user_data.pop("submitting_task_id", None)
        return

    proof_text = update.message.text or update.message.caption or ""
    proof_file_id = None

    if update.message.photo:
        proof_file_id = update.message.photo[-1].file_id
    elif update.message.document:
        proof_file_id = update.message.document.file_id

    if not proof_text and not proof_file_id:
        await _reply(update, "❌ Надішли текст або зображення.")
        return

    sub_id = add_submission(user.id, task_id, proof_text, proof_file_id)
    ctx.user_data.pop("submitting_task_id", None)

    await _reply(
        update,
        (
            f"✅ *Здано на перевірку!*\n\n"
            f"«{task['title']}» — адмін перевірить найближчим часом. ⏳"
        ),
        parse_mode="Markdown",
    )

    user_tag = f"@{user.username}" if user.username else user.first_name
    admin_text = (
        f"🔔 *Нова заявка #{sub_id}*\n\n"
        f"👤 Від: {user_tag} (ID: `{user.id}`)\n"
        f"📌 Завдання: *{task['title']}*\n"
        f"💎 XP: *{task['xp_reward']}*"
    )
    if proof_text:
        admin_text += f"\n💬 Текст:\n{proof_text[:300]}"

    markup = InlineKeyboardMarkup(
        [[
            _btn("✅ Схвалити", callback_data=f"approve_{sub_id}"),
            _btn("❌ Відхилити", callback_data=f"reject_{sub_id}"),
        ]]
    )

    for admin_id in ADMIN_IDS:
        try:
            if proof_file_id and update.message.photo:
                await ctx.bot.send_photo(
                    admin_id,
                    photo=proof_file_id,
                    caption=_normalize_text(admin_text),
                    reply_markup=markup,
                    parse_mode="Markdown",
                )
            else:
                await ctx.bot.send_message(
                    admin_id,
                    _normalize_text(admin_text),
                    reply_markup=markup,
                    parse_mode="Markdown",
                )
        except Exception as exc:
            logger.error("Не вдалося надіслати адміну %s: %s", admin_id, exc)


@rate_limit_user
async def handle_text_input(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    wizard = _wizard(ctx)

    if user and user.id in ADMIN_IDS and wizard:
        chat_id = update.effective_chat.id
        text = (update.message.text or "").strip()

        if wizard["type"] == "add_task":
            if wizard["step"] == "title":
                if not text:
                    await _wizard_prompt(ctx, chat_id, "❌ Назва не може бути порожньою. Введи назву:")
                    return
                wizard["payload"]["title"] = text
                wizard["step"] = "description"
                await _wizard_prompt(ctx, chat_id, "🧾 Введи *опис* завдання:")
                return

            if wizard["step"] == "description":
                wizard["payload"]["description"] = text
                wizard["step"] = "xp"
                await _wizard_prompt(ctx, chat_id, "💎 Введи *XP* (ціле число > 0):")
                return

            if wizard["step"] == "xp":
                try:
                    xp = int(text)
                    if xp <= 0:
                        raise ValueError
                except ValueError:
                    await _wizard_prompt(ctx, chat_id, "❌ XP має бути цілим числом > 0. Спробуй ще раз:")
                    return

                task_id = add_task(
                    wizard["payload"]["title"],
                    wizard["payload"].get("description", ""),
                    xp,
                )
                await _cleanup_wizard_prompts(ctx, chat_id)
                _clear_wizard(ctx)
                await _reply(
                    update,
                    (
                        "✅ *Завдання додано*\n\n"
                        f"ID: `{task_id}`\n"
                        f"Назва: {wizard['payload']['title']}\n"
                        f"Опис: {wizard['payload'].get('description', '-')}\n"
                        f"XP: {xp}"
                    ),
                    parse_mode="Markdown",
                )
                return

        if wizard["type"] == "give_xp":
            if wizard["step"] == "user_id":
                try:
                    target_uid = int(text)
                except ValueError:
                    await _wizard_prompt(ctx, chat_id, "❌ User ID має бути числом. Спробуй ще раз:")
                    return

                target_user = get_user_summary(target_uid)
                if not target_user:
                    await _wizard_prompt(ctx, chat_id, "❌ Користувача не знайдено. Введи інший user_id:")
                    return

                wizard["payload"]["user_id"] = target_uid
                wizard["step"] = "amount"
                await _wizard_prompt(ctx, chat_id, "🎁 Введи кількість XP (може бути від'ємна):")
                return

            if wizard["step"] == "amount":
                try:
                    amount = int(text)
                    if amount == 0:
                        raise ValueError
                except ValueError:
                    await _wizard_prompt(ctx, chat_id, "❌ XP має бути числом і не 0. Спробуй ще раз:")
                    return

                target_uid = wizard["payload"]["user_id"]
                if amount >= 0:
                    add_xp(target_uid, amount)
                    result_text = f"✅ Нараховано +{amount} XP -> `{target_uid}`"
                else:
                    admin_subtract_xp(target_uid, -amount)
                    result_text = f"✅ Знято {amount} XP -> `{target_uid}` (spendable_xp не нижче 0)"
                await _cleanup_wizard_prompts(ctx, chat_id)
                _clear_wizard(ctx)
                await _reply(update, result_text, parse_mode="Markdown")
                return

        if wizard["type"] == "add_product":
            if wizard["step"] == "name":
                if not text:
                    await _wizard_prompt(ctx, chat_id, "❌ Назва не може бути порожньою. Введи назву:")
                    return
                wizard["payload"]["name"] = text
                wizard["step"] = "description"
                await _wizard_prompt(ctx, chat_id, "📄 Введи *опис* товару:")
                return

            if wizard["step"] == "description":
                wizard["payload"]["description"] = text
                wizard["step"] = "price"
                await _wizard_prompt(ctx, chat_id, "💰 Введи *ціну* в XP (ціле число > 0):")
                return

            if wizard["step"] == "price":
                try:
                    price = int(text)
                    if price <= 0:
                        raise ValueError
                except ValueError:
                    await _wizard_prompt(ctx, chat_id, "❌ Ціна має бути цілим числом > 0. Спробуй ще раз:")
                    return

                product_id = add_product(
                    wizard["payload"]["name"],
                    wizard["payload"].get("description", ""),
                    price,
                )
                await _cleanup_wizard_prompts(ctx, chat_id)
                _clear_wizard(ctx)
                await _reply(
                    update,
                    (
                        "✅ *Товар додано*\n\n"
                        f"ID: `{product_id}`\n"
                        f"Назва: {wizard['payload']['name']}\n"
                        f"Опис: {wizard['payload'].get('description', '-')}\n"
                        f"Ціна: {price} XP"
                    ),
                    parse_mode="Markdown",
                )
                return

        if wizard["type"] == "edit_product":
            product_id = wizard["payload"]["product_id"]
            product = get_product(product_id)

            if wizard["step"] == "name":
                new_name = text if text != "." else (product["name"] if product else "")
                wizard["payload"]["new_name"] = new_name
                wizard["step"] = "description"
                cur_desc = product["description"] if product else "-"
                await _wizard_prompt(ctx, chat_id, f"📄 Введи новий *опис* (або «.» щоб залишити: {cur_desc}):")
                return

            if wizard["step"] == "description":
                cur_desc = product["description"] if product else ""
                new_desc = text if text != "." else cur_desc
                wizard["payload"]["new_description"] = new_desc
                wizard["step"] = "price"
                cur_price = product["price"] if product else 0
                await _wizard_prompt(ctx, chat_id, f"💰 Введи нову *ціну* XP (або «.» щоб залишити: {cur_price}):")
                return

            if wizard["step"] == "price":
                cur_price = product["price"] if product else 0
                if text == ".":
                    new_price = cur_price
                else:
                    try:
                        new_price = int(text)
                        if new_price <= 0:
                            raise ValueError
                    except ValueError:
                        await _wizard_prompt(ctx, chat_id, "❌ Ціна має бути цілим числом > 0 або «.». Спробуй ще раз:")
                        return

                update_product(
                    product_id,
                    name=wizard["payload"]["new_name"],
                    description=wizard["payload"]["new_description"],
                    price=new_price,
                )
                await _cleanup_wizard_prompts(ctx, chat_id)
                _clear_wizard(ctx)
                await _reply(
                    update,
                    (
                        f"✅ *Товар #{product_id} оновлено*\n\n"
                        f"Назва: {wizard['payload']['new_name']}\n"
                        f"Опис: {wizard['payload']['new_description']}\n"
                        f"Ціна: {new_price} XP"
                    ),
                    parse_mode="Markdown",
                )
                return

        if wizard["type"] == "edit_text":
            setting_key = wizard["payload"]["key"]
            if not text:
                await _wizard_prompt(ctx, chat_id, "❌ Текст не може бути порожнім. Спробуй ще раз:")
                return

            set_setting(setting_key, text)
            await _cleanup_wizard_prompts(ctx, chat_id)
            _clear_wizard(ctx)
            label = EDITABLE_TEXTS[setting_key]["label"]
            await _reply(
                update,
                f"✅ Оновлено: *{label}*.\nВикористай /bot_infoedit для інших змін.",
                parse_mode="Markdown",
            )
            return

    await _process_proof(update, ctx)


@rate_limit_user
async def handle_proof_media(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await _process_proof(update, ctx)


def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("addproduct", cmd_addproduct))
    app.add_handler(CommandHandler("delproduct", cmd_delproduct))
    app.add_handler(CommandHandler("editproduct", cmd_editproduct))


    app.add_handler(CommandHandler("shop", cmd_shop))

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("tasks", cmd_tasks))
    app.add_handler(CommandHandler("xp", cmd_xp))
    app.add_handler(CommandHandler("leaderboard", cmd_leaderboard))
    app.add_handler(CommandHandler("cancel", cmd_cancel))
    app.add_handler(CommandHandler("admin", cmd_admin))
    app.add_handler(CommandHandler("bot_infoedit", cmd_bot_infoedit))
    app.add_handler(CommandHandler("help_admin", cmd_help_admin))

    app.add_handler(CommandHandler("addtask", cmd_addtask))
    app.add_handler(CommandHandler("deltask", cmd_deltask))
    app.add_handler(CommandHandler("givexp", cmd_givexp))
    app.add_handler(CommandHandler("stats", cmd_stats))

    app.add_handler(CallbackQueryHandler(shop_callback_handler, pattern="shop_buy_.*"))
    app.add_handler(CallbackQueryHandler(on_button))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_input))
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL, handle_proof_media))

    logger.info("🤖 Бот запущено!")
    app.run_polling()


if __name__ == "__main__":
    main()



