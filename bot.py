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
        "label": "РџСЂРёРІС–С‚Р°РЅРЅСЏ /start",
        "default": (
            "рџ‘‹ РџСЂРёРІС–С‚, *{first_name}*!\n\n"
            "Р’РёРєРѕРЅСѓР№ Р·Р°РІРґР°РЅРЅСЏ -> РѕС‚СЂРёРјСѓР№ XP -> РїРѕС‚СЂР°РїР»СЏР№ Сѓ С‚РѕРї!\n\n"
            "рџ“‹ /tasks вЂ” СЃРїРёСЃРѕРє Р·Р°РІРґР°РЅСЊ\n"
            "в­ђ /xp вЂ” РјС–Р№ РїСЂРѕС„С–Р»СЊ\n"
            "рџЏ† /leaderboard вЂ” С‚Р°Р±Р»РёС†СЏ Р»С–РґРµСЂС–РІ\n"
            "вќ“ /help вЂ” СЏРє С†Рµ РїСЂР°С†СЋС”"
        ),
    },
    "help_text": {
        "label": "Р”РѕРІС–РґРєР° /help",
        "default": (
            "рџ“– *РЇРє С†Рµ РїСЂР°С†СЋС”:*\n\n"
            "1) РџРµСЂРµРіР»СЏРЅСЊ Р·Р°РІРґР°РЅРЅСЏ: /tasks\n"
            "2) Р’РёРєРѕРЅР°Р№ Р·Р°РІРґР°РЅРЅСЏ\n"
            "3) РќР°С‚РёСЃРЅРё В«рџ“¤ Р—РґР°С‚Рё Р·Р°РІРґР°РЅРЅСЏВ»\n"
            "4) РќР°РґС–С€Р»Рё РїС–РґС‚РІРµСЂРґР¶РµРЅРЅСЏ (СЃРєСЂС–РЅС€РѕС‚ Р°Р±Рѕ С‚РµРєСЃС‚)\n"
            "5) РђРґРјС–РЅ РїРµСЂРµРІС–СЂРёС‚СЊ С– РЅР°СЂР°С…СѓС” XP\n\n"
            "Р©РѕР± СЃРєР°СЃСѓРІР°С‚Рё Р·РґР°С‡Сѓ: /cancel"
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
    text = "Р—Р°Р±Р°РіР°С‚Рѕ Р·Р°РїРёС‚С–РІ. РЎРїСЂРѕР±СѓР№ С‰Рµ СЂР°Р· С‡РµСЂРµР· РєС–Р»СЊРєР° СЃРµРєСѓРЅРґ."

    if update.callback_query:
        try:
            await _query_answer(update.callback_query, text, show_alert=True)
        except Exception:
            pass
        return

    await _reply(update, text)


async def _send_ban_notice(update: Update) -> None:
    text = "Р”РѕСЃС‚СѓРї РґРѕ Р±РѕС‚Р° РѕР±РјРµР¶РµРЅРѕ. РќР°РїРёС€Рё Р°РґРјС–РЅСѓ."
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
            await _reply(update, "вќЊ РўС–Р»СЊРєРё РґР»СЏ Р°РґРјС–РЅС–РІ!")
            return
        return await func(update, ctx)

    return wrapper


def _admin_menu_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [_btn("вћ• Р”РѕРґР°С‚Рё Р·Р°РІРґР°РЅРЅСЏ", callback_data="a:add")],
            [_btn("рџ—‘ Р’РёРґР°Р»РёС‚Рё Р·Р°РІРґР°РЅРЅСЏ", callback_data="a:dellist:0")],
            [_btn("рџ‘Ґ РљРѕСЂРёСЃС‚СѓРІР°С‡С–", callback_data="a:users:0")],
            [_btn("рџЋЃ РќР°СЂР°С…СѓРІР°С‚Рё XP", callback_data="a:xp")],
            [_btn("рџ“Љ РЎС‚Р°С‚РёСЃС‚РёРєР°", callback_data="a:stats")],
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
            [_btn("вњЌпёЏ Р—РјС–РЅРёС‚Рё РїСЂРёРІС–С‚Р°РЅРЅСЏ /start", callback_data="be:edit:welcome_text")],
            [_btn("вњЌпёЏ Р—РјС–РЅРёС‚Рё РґРѕРІС–РґРєСѓ /help", callback_data="be:edit:help_text")],
            [_btn("рџ‘ЃпёЏ РџРµСЂРµРіР»СЏРЅСѓС‚Рё РїРѕС‚РѕС‡РЅС– С‚РµРєСЃС‚Рё", callback_data="be:preview")],
            [_btn("в„№пёЏ Р©Рѕ Р·РјС–РЅСЋС”С‚СЊСЃСЏ С‚С–Р»СЊРєРё С‡РµСЂРµР· BotFather", callback_data="be:limits")],
            [_btn("в¬… Р’ Р°РґРјС–РЅ-РјРµРЅСЋ", callback_data="a:menu")],
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
        await _reply(update, "рџ• РќР°СЂР°Р·С– Р·Р°РІРґР°РЅСЊ РЅРµРјР°С”. Р—Р°Р·РёСЂРЅРё РїС–Р·РЅС–С€Рµ!")
        return

    await _reply(update, "рџ“‹ *РЎРїРёСЃРѕРє Р·Р°РІРґР°РЅСЊ:*", parse_mode="Markdown")

    for task in tasks:
        done = has_approved(user.id, task["id"])
        pending = has_pending(user.id, task["id"])

        if done:
            badge = " вњ…"
        elif pending:
            badge = " вЏі"
        else:
            badge = ""

        text = (
            f"рџ“Њ *{task['title']}*{badge}\n"
            f"{task['description']}\n"
            f"рџ’Ћ РќР°РіРѕСЂРѕРґР°: *{task['xp_reward']} XP*"
        )

        if done:
            btn = _btn("вњ… Р’РёРєРѕРЅР°РЅРѕ", callback_data="noop")
        elif pending:
            btn = _btn("вЏі РќР° РїРµСЂРµРІС–СЂС†С–", callback_data="noop")
        else:
            btn = _btn("рџ“¤ Р—РґР°С‚Рё Р·Р°РІРґР°РЅРЅСЏ", callback_data=f"submit_{task['id']}")

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
            f"в­ђ *РџСЂРѕС„С–Р»СЊ {user.first_name}*\n\n"
            f"рџ’Ћ XP: *{db_user['xp']}*\n"
            f"рџЏ† РњС–СЃС†Рµ: *#{rank}* Р· {total}"
        ),
        parse_mode="Markdown",
    )


@rate_limit_user
async def cmd_leaderboard(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    top = get_leaderboard()

    if not top:
        await _reply(update, "рџ• РўР°Р±Р»РёС†СЏ РїРѕСЂРѕР¶РЅСЏ. Р‘СѓРґСЊ РїРµСЂС€РёРј!")
        return

    medals = ["рџҐ‡", "рџҐ€", "рџҐ‰"]
    lines = ["рџЏ† *РўР°Р±Р»РёС†СЏ Р»С–РґРµСЂС–РІ*\n"]
    for i, user in enumerate(top):
        icon = medals[i] if i < 3 else f"{i + 1}."
        lines.append(f"{icon} {_display_name(user)} вЂ” *{user['xp']} XP*")

    await _reply(update, "\n".join(lines), parse_mode="Markdown")


@rate_limit_user
async def cmd_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    had_submission = bool(ctx.user_data.pop("submitting_task_id", None))
    had_wizard = bool(ctx.user_data.pop("admin_wizard", None))

    if had_submission or had_wizard:
        await _reply(update, "вќЊ РџРѕС‚РѕС‡РЅСѓ РґС–СЋ СЃРєР°СЃРѕРІР°РЅРѕ.")
    else:
        await _reply(update, "РќРµРјР°С” Р°РєС‚РёРІРЅРѕС— РґС–С— РґР»СЏ СЃРєР°СЃСѓРІР°РЅРЅСЏ.")


@admin_only
@rate_limit_user
async def cmd_admin(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    _clear_wizard(ctx)
    await _reply(update, "рџ›  *РђРґРјС–РЅ-РїР°РЅРµР»СЊ*", reply_markup=_admin_menu_markup(), parse_mode="Markdown")


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
            "вќЊ Р¤РѕСЂРјР°С‚: /addtask <XP> <РЅР°Р·РІР°> | <РѕРїРёСЃ>\n"
            "РџСЂРёРєР»Р°Рґ: /addtask 50 РќР°РїРёСЃР°С‚Рё РІС–РґРіСѓРє | РќР°РїРёС€Рё РІС–РґРіСѓРє РїСЂРѕ Р±РѕС‚",
        )
        return

    task_id = add_task(title, description, xp)
    await _reply(update, f"вњ… Р—Р°РІРґР°РЅРЅСЏ #{task_id} РґРѕРґР°РЅРѕ!\nрџ“Њ {title}\nрџ’Ћ {xp} XP")


@admin_only
@rate_limit_user
async def cmd_deltask(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        task_id = int(ctx.args[0])
        delete_task(task_id)
        await _reply(update, f"вњ… Р—Р°РІРґР°РЅРЅСЏ #{task_id} РґРµР°РєС‚РёРІРѕРІР°РЅРѕ.")
    except (IndexError, ValueError):
        await _reply(update, "вќЊ Р¤РѕСЂРјР°С‚: /deltask <task_id>")


@admin_only
@rate_limit_user
async def cmd_givexp(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        uid = int(ctx.args[0])
        amount = int(ctx.args[1])
        add_xp(uid, amount)
        await _reply(update, f"вњ… РќР°СЂР°С…РѕРІР°РЅРѕ {amount} XP -> {uid}")
    except (IndexError, ValueError):
        await _reply(update, "вќЊ Р¤РѕСЂРјР°С‚: /givexp <user_id> <РєС–Р»СЊРєС–СЃС‚СЊ>")


@admin_only
@rate_limit_user
async def cmd_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    users, tasks, pending, approved = get_stats()
    await _reply(
        update,
        (
            "рџ“Љ *РЎС‚Р°С‚РёСЃС‚РёРєР°*\n\n"
            f"рџ‘Ґ РљРѕСЂРёСЃС‚СѓРІР°С‡С–РІ: {users}\n"
            f"рџ“‹ РђРєС‚РёРІРЅРёС… Р·Р°РІРґР°РЅСЊ: {tasks}\n"
            f"вЏі РќР° РїРµСЂРµРІС–СЂС†С–: {pending}\n"
            f"вњ… РЎС…РІР°Р»РµРЅРѕ: {approved}"
        ),
        parse_mode="Markdown",
    )


def _render_task_page(page: int) -> tuple[str, InlineKeyboardMarkup]:
    tasks = get_tasks()
    total_pages = max(1, (len(tasks) + ADMIN_TASKS_PAGE_SIZE - 1) // ADMIN_TASKS_PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    start = page * ADMIN_TASKS_PAGE_SIZE
    chunk = tasks[start : start + ADMIN_TASKS_PAGE_SIZE]

    lines = ["рџ—‘ *Р’РёРґР°Р»РµРЅРЅСЏ Р·Р°РІРґР°РЅСЊ*", "РќР°С‚РёСЃРЅРё РЅР° Р·Р°РІРґР°РЅРЅСЏ РґР»СЏ РґРµР°РєС‚РёРІР°С†С–С—.", ""]
    rows = []

    for task in chunk:
        lines.append(f"#{task['id']} вЂ” {task['title']} ({task['xp_reward']} XP)")
        rows.append(
            [
                _btn(
                    f"Р’РёРґР°Р»РёС‚Рё #{task['id']}",
                    callback_data=f"a:del:{task['id']}:{page}",
                )
            ]
        )

    nav = []
    if page > 0:
        nav.append(_btn("в—Ђ Prev", callback_data=f"a:dellist:{page - 1}"))
    if page < total_pages - 1:
        nav.append(_btn("Next в–¶", callback_data=f"a:dellist:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([_btn("в¬… Р’ РјРµРЅСЋ", callback_data="a:menu")])

    return "\n".join(lines), InlineKeyboardMarkup(rows)


def _render_user_page(page: int) -> tuple[str, InlineKeyboardMarkup]:
    total = count_users()
    total_pages = max(1, (total + ADMIN_USERS_PAGE_SIZE - 1) // ADMIN_USERS_PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))

    users = list_users(limit=ADMIN_USERS_PAGE_SIZE, offset=page * ADMIN_USERS_PAGE_SIZE)
    lines = [f"рџ‘Ґ *РљРѕСЂРёСЃС‚СѓРІР°С‡С–* (СЃС‚РѕСЂС–РЅРєР° {page + 1}/{total_pages})", ""]
    rows = []

    if not users:
        lines.append("РќРµРјР°С” РєРѕСЂРёСЃС‚СѓРІР°С‡С–РІ.")
    else:
        for user in users:
            ban_mark = "рџљ«" if user["is_banned"] else ""
            lines.append(f"`{user['user_id']}` | {_display_name(user)} | {user['xp']} XP {ban_mark}")
            rows.append([_btn(f"Р”РµС‚Р°Р»С– {user['user_id']}", callback_data=f"a:ud:{user['user_id']}:{page}")])

    nav = []
    if page > 0:
        nav.append(_btn("в—Ђ Prev", callback_data=f"a:users:{page - 1}"))
    if page < total_pages - 1:
        nav.append(_btn("Next в–¶", callback_data=f"a:users:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([_btn("в¬… Р’ РјРµРЅСЋ", callback_data="a:menu")])

    return "\n".join(lines), InlineKeyboardMarkup(rows)


def _render_user_detail(user_id: int, page: int) -> tuple[str, InlineKeyboardMarkup] | tuple[None, None]:
    user = get_user_summary(user_id)
    if not user:
        return None, None

    status = "banned" if user["is_banned"] else "active"
    lines = [
        "рџ‘¤ *РљР°СЂС‚РєР° РєРѕСЂРёСЃС‚СѓРІР°С‡Р°*",
        f"ID: `{user['user_id']}`",
        f"Username: {_display_name(user)}",
        f"Name: {user['first_name'] or '-'}",
        f"Joined: {user['joined_at'] or '-'}",
        f"XP: {user['xp']}",
        f"Status: *{status}*",
    ]

    if user["is_banned"]:
        action_btn = _btn("вњ… Unban", callback_data=f"a:unban:{user['user_id']}:{page}")
    else:
        action_btn = _btn("рџљ« Ban", callback_data=f"a:ban:{user['user_id']}:{page}")

    markup = InlineKeyboardMarkup(
        [[action_btn], [_btn("в¬… Р”Рѕ СЃРїРёСЃРєСѓ", callback_data=f"a:users:{page}")]]
    )
    return "\n".join(lines), markup


async def _start_admin_wizard(update: Update, ctx: ContextTypes.DEFAULT_TYPE, wizard_type: str):
    chat_id = update.effective_chat.id
    if wizard_type == "add_task":
        ctx.user_data["admin_wizard"] = {
            "type": "add_task",
            "step": "title",
            "payload": {},
            "bot_prompt_ids": [],
        }
        await _wizard_prompt(ctx, chat_id, "рџ“ќ Р’РІРµРґРё *РЅР°Р·РІСѓ* Р·Р°РІРґР°РЅРЅСЏ:")
        return

    if wizard_type == "give_xp":
        ctx.user_data["admin_wizard"] = {
            "type": "give_xp",
            "step": "user_id",
            "payload": {},
            "bot_prompt_ids": [],
        }
        await _wizard_prompt(ctx, chat_id, "рџЋЇ Р’РІРµРґРё *user_id* РєРѕСЂРёСЃС‚СѓРІР°С‡Р°:")
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
        await _edit_message_text(query, "рџ›  *РђРґРјС–РЅ-РїР°РЅРµР»СЊ*", reply_markup=_admin_menu_markup(), parse_mode="Markdown")
        return

    if data == "a:add":
        await _start_admin_wizard(update, ctx, "add_task")
        await _query_answer(query, "РњР°Р№СЃС‚РµСЂ РґРѕРґР°РІР°РЅРЅСЏ Р·Р°РїСѓС‰РµРЅРѕ")
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
        await _edit_message_text(query, text=f"вњ… Р—Р°РІРґР°РЅРЅСЏ #{task_id_str} РґРµР°РєС‚РёРІРѕРІР°РЅРѕ.\n\n{text}", reply_markup=markup, parse_mode="Markdown")
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
            await _query_answer(query, "РљРѕСЂРёСЃС‚СѓРІР°С‡Р° РЅРµ Р·РЅР°Р№РґРµРЅРѕ", show_alert=True)
            return
        await _edit_message_text(query, text=text, reply_markup=markup, parse_mode="Markdown")
        return

    if data.startswith("a:ban:"):
        _, _, user_id_str, page_str = data.split(":")
        if int(user_id_str) == query.from_user.id:
            await _query_answer(query, "РќРµ РјРѕР¶РЅР° Р·Р°Р±Р°РЅРёС‚Рё СЃР°РјРѕРіРѕ СЃРµР±Рµ.", show_alert=True)
            return
        ok = ban_user(int(user_id_str))
        if not ok:
            await _query_answer(query, "РљРѕСЂРёСЃС‚СѓРІР°С‡Р° РЅРµ Р·РЅР°Р№РґРµРЅРѕ", show_alert=True)
            return
        text, markup = _render_user_detail(int(user_id_str), int(page_str))
        await _edit_message_text(query, text=f"рџљ« РљРѕСЂРёСЃС‚СѓРІР°С‡Р° Р·Р°Р±Р°РЅРµРЅРѕ.\n\n{text}", reply_markup=markup, parse_mode="Markdown")
        return

    if data.startswith("a:unban:"):
        _, _, user_id_str, page_str = data.split(":")
        ok = unban_user(int(user_id_str))
        if not ok:
            await _query_answer(query, "РљРѕСЂРёСЃС‚СѓРІР°С‡Р° РЅРµ Р·РЅР°Р№РґРµРЅРѕ", show_alert=True)
            return
        text, markup = _render_user_detail(int(user_id_str), int(page_str))
        await _edit_message_text(query, text=f"вњ… Р‘Р°РЅ Р·РЅСЏС‚Рѕ.\n\n{text}", reply_markup=markup, parse_mode="Markdown")
        return

    if data == "a:stats":
        users, tasks, pending, approved = get_stats()
        await _edit_message_text(query, 
            text=(
                "рџ“Љ *РЎС‚Р°С‚РёСЃС‚РёРєР°*\n\n"
                f"рџ‘Ґ РљРѕСЂРёСЃС‚СѓРІР°С‡С–РІ: {users}\n"
                f"рџ“‹ РђРєС‚РёРІРЅРёС… Р·Р°РІРґР°РЅСЊ: {tasks}\n"
                f"вЏі РќР° РїРµСЂРµРІС–СЂС†С–: {pending}\n"
                f"вњ… РЎС…РІР°Р»РµРЅРѕ: {approved}"
            ),
            reply_markup=InlineKeyboardMarkup([[_btn("в¬… Р’ РјРµРЅСЋ", callback_data="a:menu")]]),
            parse_mode="Markdown",
        )
        return

    if data == "a:xp":
        await _start_admin_wizard(update, ctx, "give_xp")
        await _query_answer(query, "РњР°Р№СЃС‚РµСЂ РЅР°СЂР°С…СѓРІР°РЅРЅСЏ XP Р·Р°РїСѓС‰РµРЅРѕ")
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
            await _query_answer(query, "вњ… РўРё РІР¶Рµ РІРёРєРѕРЅР°РІ С†Рµ Р·Р°РІРґР°РЅРЅСЏ!", show_alert=True)
            return
        if has_pending(user.id, task_id):
            await _query_answer(query, "вЏі РўРІРѕСЏ РІС–РґРїРѕРІС–РґСЊ РІР¶Рµ РЅР° РїРµСЂРµРІС–СЂС†С–!", show_alert=True)
            return

        task = get_task(task_id)
        ctx.user_data["submitting_task_id"] = task_id

        await query.message.reply_text(
            (
                f"рџ“¤ *Р—РґР°С‡Р°: {task['title']}*\n\n"
                "РќР°РґС–С€Р»Рё РїС–РґС‚РІРµСЂРґР¶РµРЅРЅСЏ РІРёРєРѕРЅР°РЅРЅСЏ:\n"
                "вЂў рџ“ё РЎРєСЂС–РЅС€РѕС‚\n"
                "вЂў рџ“ќ РђР±Рѕ С‚РµРєСЃС‚РѕРІРёР№ РѕРїРёСЃ\n\n"
                "_Р©РѕР± СЃРєР°СЃСѓРІР°С‚Рё вЂ” /cancel_"
            ),
            parse_mode="Markdown",
        )
        return

    if data.startswith("approve_") or data.startswith("reject_"):
        if query.from_user.id not in ADMIN_IDS:
            await _query_answer(query, "вќЊ РўС–Р»СЊРєРё РґР»СЏ Р°РґРјС–РЅС–РІ!", show_alert=True)
            return

        action, sub_id_str = data.split("_", 1)
        sub_id = int(sub_id_str)
        sub = get_submission(sub_id)

        if not sub:
            await _query_answer(query, "вќЊ Р—Р°СЏРІРєСѓ РЅРµ Р·РЅР°Р№РґРµРЅРѕ.", show_alert=True)
            return
        if sub["status"] != "pending":
            await _query_answer(query, "вљ пёЏ Р’Р¶Рµ РѕР±СЂРѕР±Р»РµРЅРѕ.", show_alert=True)
            return

        new_status = "approved" if action == "approve" else "rejected"
        review_submission(sub_id, new_status, query.from_user.id)

        task = get_task(sub["task_id"])
        admin_tag = f"@{query.from_user.username}" if query.from_user.username else query.from_user.first_name

        if action == "approve":
            add_xp(sub["user_id"], task["xp_reward"])
            result_icon = "вњ… РЎС…РІР°Р»РµРЅРѕ"
            user_msg = (
                f"рџЋ‰ *Р—Р°РІРґР°РЅРЅСЏ РїС–РґС‚РІРµСЂРґР¶РµРЅРѕ!*\n\n"
                f"вњ… В«{task['title']}В» вЂ” Р·Р°СЂР°С…РѕРІР°РЅРѕ!\n"
                f"рџ’Ћ +{task['xp_reward']} XP РЅР°СЂР°С…РѕРІР°РЅРѕ!\n\n"
                f"РџРµСЂРµРіР»СЏРЅСЊ РїСЂРѕС„С–Р»СЊ: /xp"
            )
        else:
            result_icon = "вќЊ Р’С–РґС…РёР»РµРЅРѕ"
            user_msg = (
                f"вќЊ *Р—Р°РІРґР°РЅРЅСЏ РЅРµ РїСЂРёР№РЅСЏС‚Рѕ*\n\n"
                f"В«{task['title']}В» вЂ” РІС–РґС…РёР»РµРЅРѕ.\n"
                f"РЎРїСЂРѕР±СѓР№ С‰Рµ СЂР°Р·! /tasks"
            )

        try:
            await ctx.bot.send_message(sub["user_id"], _normalize_text(user_msg), parse_mode="Markdown")
        except Exception:
            pass

        suffix = f"\n\n{result_icon} Р°РґРјС–РЅРѕРј {admin_tag}"
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
        await _reply(update, "вќЊ Р—Р°РІРґР°РЅРЅСЏ РЅРµ Р·РЅР°Р№РґРµРЅРѕ. /tasks")
        ctx.user_data.pop("submitting_task_id", None)
        return

    proof_text = update.message.text or update.message.caption or ""
    proof_file_id = None

    if update.message.photo:
        proof_file_id = update.message.photo[-1].file_id
    elif update.message.document:
        proof_file_id = update.message.document.file_id

    if not proof_text and not proof_file_id:
        await _reply(update, "вќЊ РќР°РґС–С€Р»Рё С‚РµРєСЃС‚ Р°Р±Рѕ Р·РѕР±СЂР°Р¶РµРЅРЅСЏ.")
        return

    sub_id = add_submission(user.id, task_id, proof_text, proof_file_id)
    ctx.user_data.pop("submitting_task_id", None)

    await _reply(
        update,
        (
            f"вњ… *Р—РґР°РЅРѕ РЅР° РїРµСЂРµРІС–СЂРєСѓ!*\n\n"
            f"В«{task['title']}В» вЂ” Р°РґРјС–РЅ РїРµСЂРµРІС–СЂРёС‚СЊ РЅР°Р№Р±Р»РёР¶С‡РёРј С‡Р°СЃРѕРј. вЏі"
        ),
        parse_mode="Markdown",
    )

    user_tag = f"@{user.username}" if user.username else user.first_name
    admin_text = (
        f"рџ”” *РќРѕРІР° Р·Р°СЏРІРєР° #{sub_id}*\n\n"
        f"рџ‘¤ Р’С–Рґ: {user_tag} (ID: `{user.id}`)\n"
        f"рџ“Њ Р—Р°РІРґР°РЅРЅСЏ: *{task['title']}*\n"
        f"рџ’Ћ XP: *{task['xp_reward']}*"
    )
    if proof_text:
        admin_text += f"\nрџ’¬ РўРµРєСЃС‚:\n{proof_text[:300]}"

    markup = InlineKeyboardMarkup(
        [[
            _btn("вњ… РЎС…РІР°Р»РёС‚Рё", callback_data=f"approve_{sub_id}"),
            _btn("вќЊ Р’С–РґС…РёР»РёС‚Рё", callback_data=f"reject_{sub_id}"),
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
            logger.error("РќРµ РІРґР°Р»РѕСЃСЏ РЅР°РґС–СЃР»Р°С‚Рё Р°РґРјС–РЅСѓ %s: %s", admin_id, exc)


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
                    await _wizard_prompt(ctx, chat_id, "вќЊ РќР°Р·РІР° РЅРµ РјРѕР¶Рµ Р±СѓС‚Рё РїРѕСЂРѕР¶РЅСЊРѕСЋ. Р’РІРµРґРё РЅР°Р·РІСѓ:")
                    return
                wizard["payload"]["title"] = text
                wizard["step"] = "description"
                await _wizard_prompt(ctx, chat_id, "рџ§ѕ Р’РІРµРґРё *РѕРїРёСЃ* Р·Р°РІРґР°РЅРЅСЏ:")
                return

            if wizard["step"] == "description":
                wizard["payload"]["description"] = text
                wizard["step"] = "xp"
                await _wizard_prompt(ctx, chat_id, "рџ’Ћ Р’РІРµРґРё *XP* (С†С–Р»Рµ С‡РёСЃР»Рѕ > 0):")
                return

            if wizard["step"] == "xp":
                try:
                    xp = int(text)
                    if xp <= 0:
                        raise ValueError
                except ValueError:
                    await _wizard_prompt(ctx, chat_id, "вќЊ XP РјР°С” Р±СѓС‚Рё С†С–Р»РёРј С‡РёСЃР»РѕРј > 0. РЎРїСЂРѕР±СѓР№ С‰Рµ СЂР°Р·:")
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
                        "вњ… *Р—Р°РІРґР°РЅРЅСЏ РґРѕРґР°РЅРѕ*\n\n"
                        f"ID: `{task_id}`\n"
                        f"РќР°Р·РІР°: {wizard['payload']['title']}\n"
                        f"РћРїРёСЃ: {wizard['payload'].get('description', '-')}\n"
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
                    await _wizard_prompt(ctx, chat_id, "вќЊ User ID РјР°С” Р±СѓС‚Рё С‡РёСЃР»РѕРј. РЎРїСЂРѕР±СѓР№ С‰Рµ СЂР°Р·:")
                    return

                target_user = get_user_summary(target_uid)
                if not target_user:
                    await _wizard_prompt(ctx, chat_id, "вќЊ РљРѕСЂРёСЃС‚СѓРІР°С‡Р° РЅРµ Р·РЅР°Р№РґРµРЅРѕ. Р’РІРµРґРё С–РЅС€РёР№ user_id:")
                    return

                wizard["payload"]["user_id"] = target_uid
                wizard["step"] = "amount"
                await _wizard_prompt(ctx, chat_id, "рџЋЃ Р’РІРµРґРё РєС–Р»СЊРєС–СЃС‚СЊ XP (РјРѕР¶Рµ Р±СѓС‚Рё РІС–Рґ'С”РјРЅР°):")
                return

            if wizard["step"] == "amount":
                try:
                    amount = int(text)
                    if amount == 0:
                        raise ValueError
                except ValueError:
                    await _wizard_prompt(ctx, chat_id, "вќЊ XP РјР°С” Р±СѓС‚Рё С‡РёСЃР»РѕРј С– РЅРµ 0. РЎРїСЂРѕР±СѓР№ С‰Рµ СЂР°Р·:")
                    return

                target_uid = wizard["payload"]["user_id"]
                add_xp(target_uid, amount)
                await _cleanup_wizard_prompts(ctx, chat_id)
                _clear_wizard(ctx)
                await _reply(update, f"вњ… РќР°СЂР°С…РѕРІР°РЅРѕ {amount} XP -> `{target_uid}`", parse_mode="Markdown")
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

    app.add_handler(CallbackQueryHandler(on_button))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_input))
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL, handle_proof_media))

    logger.info("рџ¤– Р‘РѕС‚ Р·Р°РїСѓС‰РµРЅРѕ!")
    app.run_polling()


if __name__ == "__main__":
    main()



