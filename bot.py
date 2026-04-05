import logging
import sqlite3
import time
import asyncio
from collections import defaultdict, deque
from functools import wraps
from datetime import datetime, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, ChatMember
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
    JobQueue,
)

from config import ADMIN_IDS, BOT_TOKEN, TELEGRAM_CHANNEL_ID
from messages import get_message
from analytics import log_event, log_admin_action, log_error
from supervision import update_supervision_summary
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
    get_tasks_by_difficulty,
    get_tasks_filtered,
    get_user,
    get_user_rank,
    get_user_summary,
    get_user_language,
    set_user_language,
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
    add_to_inventory,
    get_inventory,
    get_departments,
    get_department,
    mark_verified,
    mark_unverified,
    get_users_needing_recheck,
    add_idea,
    get_unreviewed_ideas,
    mark_idea_reviewed,
    mark_idea_status,
    get_idea,
    delete_idea,
    get_user_departments,
    add_user_department,
    remove_user_department,
    has_user_department,
    set_user_role,
    get_user_role,
    set_user_global_role,
    get_user_global_role,
    set_user_dept_role,
    get_user_dept_role,
    get_user_all_dept_roles,
    get_dept_supervisors,
    is_supervisor_of_dept,
    get_users_in_department,
    DB_PATH,
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
ADMIN_IDEAS_PAGE_SIZE = 8
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
            "📦 /inventory — мій інвентар\n"
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


async def _notify_admins_new_idea(bot, idea_dict):
    """Notify admins/supervisors about new idea
    
    idea_dict keys: id, user_id, text, is_anonymous, username, department_id
    """
    # Format notification text based on anonymity
    if idea_dict['is_anonymous']:
        text = f"💡 *Анонімна ідея*:\n\n{idea_dict['text']}"
    else:
        dept_name = ""
        if idea_dict['department_id']:
            dept = get_department(idea_dict['department_id'])
            if dept:
                dept_name = f" ({dept['emoji']} {dept['name']})"
        text = f"💡 *Нова ідея від {idea_dict['username']}{dept_name}*:\n\n{idea_dict['text']}"
    
    # Notify all admins
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, _normalize_text(text), parse_mode="Markdown")
        except Exception as e:
            logger.warning(f"Failed to notify admin {admin_id} about idea: {e}")
    
    # If idea has department, also notify supervisors of that dept
    if idea_dict['department_id']:
        # For now, supervisors are also admins or users with supervisor role
        # Future: could check supervisor_depts_json when fully implemented
        pass


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
            user = update.effective_user
            lang = get_user_language(user.id)
            await _reply(update, get_message("admin_only", lang))
            return
        return await func(update, ctx)
    return wrapper


def admin_with_dept_check(func):
    """Decorator to require admin status AND department selection.
    Ensures admin is logged in and has a department assigned."""
    @wraps(func)
    async def wrapper(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not _is_admin(update):
            user = update.effective_user
            lang = get_user_language(user.id)
            await _reply(update, get_message("admin_only", lang))
            return
        
        user = update.effective_user
        db_user = get_user(user.id)
        
        user_depts = get_user_departments(user.id)
        if not db_user or not user_depts:
            await _reply(update,
                "❌ Адмін повинен мати обраний відділ. Напиши /start",
                parse_mode="Markdown")
            return
        
        # Store department context for use in the handler
        ctx.user_data["admin_dept_id"] = user_depts[0]
        
        return await func(update, ctx)
    
    return wrapper


# ========== STARTUP FLOW DECORATORS & FUNCTIONS ==========

def requires_dept_and_verified(func):
    """Decorator to require user to have department selected and be verified.
    Redirects to /start if not."""
    @wraps(func)
    async def wrapper(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if not user:
            return
        
        db_user = get_user(user.id)
        if not db_user:
            lang = get_user_language(user.id) if user.id else "uk"
            await _reply(update, get_message("user_not_found", lang))
            return
        
        # Check if user has department selected
        user_depts = get_user_departments(user.id)
        if not user_depts:
            await _reply(update, 
                "❌ Спочатку обери свій департамент. Напиши /start",
                parse_mode="Markdown")
            return
        
        # Check if user is verified (but don't block - just warn)
        if not db_user["is_verified"]:
            # Show friendly reminder but don't block
            reminder_text = (
                "ℹ️ Помітили, що ти не підписаний на наш канал!\n\n"
                "📱 Підпишись на @aturinfo, щоб не пропустити важливе.\n\n"
                "Але можеш продовжити роботити 😊"
            )
            await _reply(update, reminder_text)
        
        return await func(update, ctx)
    
    return wrapper


async def check_channel_subscription(bot, user_id: int, channel_id: int) -> bool:
    """Check if user is subscribed to channel. Returns True if subscribed."""
    try:
        # Add 5-second timeout to prevent API calls from hanging
        async with asyncio.timeout(5):
            member = await bot.get_chat_member(channel_id, user_id)
            is_subscribed = member.status in ["member", "administrator", "creator"]
            logger.info(f"🔍 Статус користувача {user_id} в каналі {channel_id}: {member.status} → підписаний={is_subscribed}")
            return is_subscribed
    except asyncio.TimeoutError:
        logger.warning(f"⏱️ Timeout перевірки підписки для {user_id} на канал {channel_id}")
        # Assume subscription is OK if API times out (fail-open, assume verified)
        return True
    except Exception as e:
        logger.warning(f"❌ Помилка перевірки підписки для {user_id}: {e}")
        return False


async def process_language_selection(update: Update, ctx: ContextTypes.DEFAULT_TYPE, lang: str):
    """Handle language selection and move to verification."""
    user = update.effective_user
    set_user_language(user.id, lang)
    
    await _reply(update,
        get_message("lang_selected", lang),
        parse_mode="Markdown")
    
    # Move to verification
    await process_subscription_verification(update, ctx)


async def process_subscription_verification(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Check if user is subscribed to channel, and move to department selection if yes."""
    user = update.effective_user
    lang = get_user_language(user.id)
    
    logger.info(f"🔍 Перевіряю підписку для користувача {user.id}...")
    is_subscribed = await check_channel_subscription(ctx.bot, user.id, TELEGRAM_CHANNEL_ID)
    logger.info(f"📊 Результат перевірки: підписаний={is_subscribed}")
    
    if is_subscribed:
        logger.info(f"✅ Користувач {user.id} підписаний - відправляю dept selection")
        mark_verified(user.id)
        await _reply(update,
            get_message("verify_subscribed", lang),
            parse_mode="Markdown")
        await show_department_selection(update, ctx)
        logger.info(f"✅ Меню вибору відділу відправлено для {user.id}")
    else:
        logger.info(f"❌ Користувач {user.id} не підписаний - показую запит")
        # Show subscription request
        await _reply(update,
            get_message("verify_not_subscribed", lang, first_name=user.first_name or "friend"),
            reply_markup=InlineKeyboardMarkup([[
                _btn(get_message("verify_btn", lang), callback_data="verify_retry")
            ]]),
            parse_mode="Markdown")


async def show_department_selection(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Display department selection with multi-select checkboxes."""
    user = update.effective_user
    lang = get_user_language(user.id)
    departments = get_departments()
    
    # Get currently selected departments
    current_depts = get_user_departments(user.id) or []
    
    # Store in context for this session
    if "selected_depts" not in ctx.user_data:
        ctx.user_data["selected_depts"] = current_depts.copy()
    
    selected = ctx.user_data["selected_depts"]
    
    rows = []
    for dept in departments:
        is_selected = dept['id'] in selected
        check = "✓" if is_selected else "☐"
        btn_text = f"{check} {dept['emoji']} {dept['name']}"
        rows.append([_btn(btn_text, callback_data=f"dept_toggle_{dept['id']}")])
    
    # Add Done button
    rows.append([_btn(get_message("dept_btn_done", lang), callback_data="dept_done")])
    
    back_text = "⬅ Back" if lang == "en" else "⬅ Înapoi" if lang == "ro" else "⬅ Назад"
    rows.append([_btn(back_text, callback_data="lang_select")])
    
    await _reply(update,
        get_message("dept_multi_select", lang),
        reply_markup=InlineKeyboardMarkup(rows),
        parse_mode="Markdown")


async def show_language_selection(update: Update):
    """Display language selection buttons."""
    markup = InlineKeyboardMarkup([
        [
            _btn(get_message("lang_en_btn", "en"), callback_data="lang_en"),
            _btn(get_message("lang_ro_btn", "en"), callback_data="lang_ro"),
            _btn(get_message("lang_uk_btn", "en"), callback_data="lang_uk"),
        ]
    ])
    
    await _reply(update,
        get_message("lang_select", "uk"),
        reply_markup=markup,
        parse_mode="Markdown")


# ========== STARTUP CALLBACKS ==========

async def handle_language_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle language selection button press."""
    query = update.callback_query
    await _query_answer(query)
    
    if query.data == "lang_select":
        await show_language_selection(update)
        return
    
    lang_map = {
        "lang_en": "en",
        "lang_ro": "ro",
        "lang_uk": "uk",
    }
    
    lang = lang_map.get(query.data)
    if lang:
        await process_language_selection(update, ctx, lang)


async def handle_change_language(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle language change button from main menu."""
    query = update.callback_query
    await _query_answer(query)
    
    user_id = query.from_user.id
    logger.info(f"🌐 Користувач {user_id} натиснув кнопку зміни мови")
    
    await _edit_message_text(query,
        get_message("lang_select", "uk"),
        reply_markup=InlineKeyboardMarkup([
            [
                _btn(get_message("lang_en_btn", "en"), callback_data="lang_en"),
                _btn(get_message("lang_ro_btn", "en"), callback_data="lang_ro"),
                _btn(get_message("lang_uk_btn", "en"), callback_data="lang_uk"),
            ]
        ]),
        parse_mode="Markdown")


async def handle_verify_retry(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle 'Я вже підписаний' button - retry verification."""
    query = update.callback_query
    await _query_answer(query)
    
    await _edit_message_text(query,
        "⏳ *Перевіряю підписку...*",
        parse_mode="Markdown")
    
    await process_subscription_verification(update, ctx)


def _render_manage_depts(user_id: int, lang: str) -> tuple[str, InlineKeyboardMarkup]:
    """Render department management UI."""
    user_depts = get_user_departments(user_id) or []
    if not user_depts:
        return ("No departments", InlineKeyboardMarkup([[_btn(get_message("back_btn", lang), callback_data="go_back")]]))
    depts = get_departments()
    rows = []
    for d in depts:
        if d['id'] in user_depts:
            rows.append([_btn(f"{d['emoji']} {d['name']}", callback_data="noop"), _btn("❌", callback_data=f"dept_leave_{d['id']}")])
    avail = [d for d in depts if d['id'] not in user_depts]
    if avail:
        rows.append([_btn(get_message("dept_add_more_btn", lang), callback_data="dept_add_mode")])
    rows.append([_btn(get_message("back_btn", lang), callback_data="go_back")])
    return get_message("dept_manage_prompt", lang), InlineKeyboardMarkup(rows)


async def handle_manage_depts(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle manage depts button."""
    query = update.callback_query
    await _query_answer(query)
    uid = query.from_user.id
    lang = get_user_language(uid)
    text, mk = _render_manage_depts(uid, lang)
    await _edit_message_text(query, text, reply_markup=mk, parse_mode="Markdown")


async def handle_leave_dept(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle leaving a department."""
    query = update.callback_query
    await _query_answer(query)
    uid = query.from_user.id
    lang = get_user_language(uid)
    try:
        did = int(query.data.split("_")[2])
    except (IndexError, ValueError):
        await _query_answer(query, "Error parsing department", show_alert=True)
        return
    udpts = get_user_departments(uid) or []
    if len(udpts) <= 1:
        await _query_answer(query, "❌ Keep at least 1 dept!", show_alert=True)
        return
    remove_user_department(uid, did)
    text, mk = _render_manage_depts(uid, lang)
    await _edit_message_text(query, text, reply_markup=mk, parse_mode="Markdown")


async def handle_add_more_depts(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle adding more departments."""
    query = update.callback_query
    await _query_answer(query)
    uid = query.from_user.id
    lang = get_user_language(uid)
    ctx.user_data["add_mode"] = True
    ctx.user_data["selected_depts"] = get_user_departments(uid) or []
    dpts = get_departments()
    rows = []
    for d in dpts:
        if d['id'] not in ctx.user_data["selected_depts"]:
            rows.append([_btn(f"☐ {d['emoji']} {d['name']}", callback_data=f"dept_toggle_{d['id']}")])
    rows.append([_btn(get_message("dept_btn_done", lang), callback_data="dept_add_done")])
    rows.append([_btn(get_message("back_btn", lang), callback_data="manage_depts")])
    await _edit_message_text(query, get_message("dept_add_more_prompt", lang), reply_markup=InlineKeyboardMarkup(rows), parse_mode="Markdown")


async def handle_department_selection(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle multi-select department selection."""
    query = update.callback_query
    await _query_answer(query)
    
    data = query.data
    user_id = query.from_user.id
    lang = get_user_language(user_id)
    
    # Initialize selected_depts in context if not present
    if "selected_depts" not in ctx.user_data:
        ctx.user_data["selected_depts"] = get_user_departments(user_id) or []
    
    selected = ctx.user_data["selected_depts"]
    
    # Handle toggle
    if data.startswith("dept_toggle_"):
        try:
            dept_id = int(data.split("_")[2])
        except (IndexError, ValueError):
            await _query_answer(query, "❌ Помилка вибору. Спробуй ще раз.", show_alert=True)
            return
        
        if dept_id in selected:
            selected.remove(dept_id)
        else:
            selected.append(dept_id)
        
        # Refresh the display
        departments = get_departments()
        rows = []
        for dept in departments:
            is_selected = dept['id'] in selected
            check = "✓" if is_selected else "☐"
            btn_text = f"{check} {dept['emoji']} {dept['name']}"
            rows.append([_btn(btn_text, callback_data=f"dept_toggle_{dept['id']}")])
        
        # Add Done button
        rows.append([_btn(get_message("dept_btn_done", lang), callback_data="dept_done")])
        
        back_text = "⬅ Back" if lang == "en" else "⬅ Înapoi" if lang == "ro" else "⬅ Назад"
        rows.append([_btn(back_text, callback_data="lang_select")])
        
        await _edit_message_text(query,
            get_message("dept_multi_select", lang),
            reply_markup=InlineKeyboardMarkup(rows),
            parse_mode="Markdown")
        return
    
    # Handle Done button
    if data == "dept_done" or data == "dept_add_done":
        if not selected:
            await _query_answer(query, "⚠️ Виберай хоча б один департамент!", show_alert=True)
            return
        
        # Save all selected departments
        # First clear existing ones
        current_depts = get_user_departments(user_id) or []
        for dept_id in current_depts:
            if dept_id not in selected:
                remove_user_department(user_id, dept_id)
        
        # Add new ones
        for dept_id in selected:
            if dept_id not in current_depts:
                add_user_department(user_id, dept_id)
        
        # 📊 Log user registration event
        log_event('user_registered', user_id=user_id, data={
            'language': lang,
            'departments': selected,
            'timestamp': datetime.utcnow().isoformat()
        })
        
        # Format dept list for message
        departments = get_departments()
        dept_list = "\n".join([
            f"  {d['emoji']} {d['name']}"
            for d in departments
            if d['id'] in selected
        ])
        
        welcome_msg = get_message("dept_multi_done", lang, depts=dept_list)
        
        await _edit_message_text(query,
            welcome_msg,
            parse_mode="Markdown")
        
        # Clean up context
        ctx.user_data.pop("selected_depts", None)
        return


@rate_limit_user
async def cmd_shop(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Shop - placeholder for now"""
    user = update.effective_user
    register_user(user)
    lang = get_user_language(user.id)
    
    push_nav(ctx, "menu")
    markup = InlineKeyboardMarkup([
        [_btn(get_message("back_btn", lang), callback_data="go_back")]
    ])
    
    await _reply(update,
        get_message("shop_placeholder", lang),
        reply_markup=markup,
        parse_mode="Markdown")


@rate_limit_user
async def cmd_inventory(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Inventory - placeholder for now"""
    user = update.effective_user
    register_user(user)
    lang = get_user_language(user.id)
    
    push_nav(ctx, "menu")
    markup = InlineKeyboardMarkup([
        [_btn(get_message("back_btn", lang), callback_data="go_back")]
    ])
    
    await _reply(update,
        get_message("inventory_placeholder", lang),
        reply_markup=markup,
        parse_mode="Markdown")


@rate_limit_user
async def cmd_achievements(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Achievements - placeholder"""
    user = update.effective_user
    register_user(user)
    lang = get_user_language(user.id)
    
    push_nav(ctx, "menu")
    markup = InlineKeyboardMarkup([
        [_btn(get_message("back_btn", lang), callback_data="go_back")]
    ])
    
    await _reply(update,
        get_message("achievements_placeholder", lang),
        reply_markup=markup,
        parse_mode="Markdown")


@rate_limit_user
async def cmd_idea(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Start idea submission flow"""
    user = update.effective_user
    register_user(user)
    lang = get_user_language(user.id)
    
    push_nav(ctx, "menu")
    ctx.user_data["submitting_idea"] = True
    
    markup = InlineKeyboardMarkup([
        [_btn(get_message("back_btn", lang), callback_data="go_back")]
    ])
    
    await _reply(update,
        get_message("idea_prompt", lang),
        reply_markup=markup,
        parse_mode="Markdown")


async def handle_idea_submission(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle idea text input — save draft and ask for anonymity choice"""
    if not ctx.user_data.get("submitting_idea"):
        return
    
    user = update.effective_user
    lang = get_user_language(user.id)
    text = (update.message.text or "").strip()
    
    if not text:
        await _reply(update, get_message("idea_empty", lang))
        return
    
    # Store idea draft and get user's primary department
    user_depts = get_user_departments(user.id)
    primary_dept = user_depts[0] if user_depts else None
    
    ctx.user_data["idea_draft"] = {
        "text": text,
        "department_id": primary_dept,
        "username": user.username or user.first_name or f"User{user.id}"
    }
    ctx.user_data.pop("submitting_idea", None)
    
    push_nav(ctx, "idea")
    # Ask for anonymity choice
    markup = InlineKeyboardMarkup([
        [
            _btn(get_message("idea_btn_named", lang), callback_data="idea_named"),
            _btn(get_message("idea_btn_anon", lang), callback_data="idea_anon"),
        ],
        [_btn(get_message("back_btn", lang), callback_data="go_back")],
    ])
    
    await _reply(update,
        get_message("idea_anonymity_ask", lang),
        reply_markup=markup,
        parse_mode="Markdown")


async def handle_idea_anonymity_choice(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle anonymity choice (named or anonymous)"""
    query = update.callback_query
    await _query_answer(query)
    
    user_id = query.from_user.id
    lang = get_user_language(user_id)
    
    # Check if idea draft exists
    if "idea_draft" not in ctx.user_data:
        await _query_answer(query, "❌ Сесія експіровала. Спробуй /idea ще раз.", show_alert=True)
        return
    
    draft = ctx.user_data["idea_draft"]
    is_anonymous = query.data == "idea_anon"
    
    # Save idea to DB
    idea_id = add_idea(
        user_id=user_id,
        text=draft["text"],
        is_anonymous=is_anonymous,
        department_id=draft["department_id"],
        username=draft["username"]
    )
    
    # 📊 Log idea submission event
    log_event('idea_submitted', user_id=user_id, data={
        'idea_id': idea_id,
        'anonymous': is_anonymous,
        'department_id': draft["department_id"],
        'text_preview': draft["text"][:100]
    })
    
    # Confirmation message
    await _edit_message_text(query,
        get_message("idea_submitted", lang),
        parse_mode="Markdown")
    
    # Notify admins/supervisors
    await _notify_admins_new_idea(ctx.bot, {
        "id": idea_id,
        "user_id": user_id,
        "text": draft["text"],
        "is_anonymous": is_anonymous,
        "username": draft["username"],
        "department_id": draft["department_id"]
    })
    
    # Cleanup
    ctx.user_data.pop("idea_draft", None)
    
    logger.info(f"💡 Ідея #{idea_id} від {user_id} ({draft['username']}): anonymous={is_anonymous}")



async def handle_shop_buy(query, user_id, product_id):
    product = get_product(product_id)
    if not product or not product['is_active']:
        await query.answer("❌ Товар недоступний", show_alert=True)
        return
    db_user = get_user(user_id)
    if db_user['spendable_xp'] < product['price']:
        await query.answer(
            f"❌ Недостатньо XP!\n"
            f"Потрібно: {product['price']} XP\n"
            f"У тебе: {db_user['spendable_xp']} XP",
            show_alert=True,
        )
        return
    success = spend_xp(user_id, product['price'])
    if success:
        add_to_inventory(user_id, product['id'], product['name'], product['price'])
        
        # 📊 Log XP spending event
        log_event('xp_spent', user_id=user_id, data={
            'amount': product['price'],
            'product_id': product['id'],
            'product_name': product['name'][:50]
        })
        
        await query.answer(f"✅ Куплено: {product['name']}!", show_alert=True)
        await query.message.reply_text(
            f"📦 *Покупка успішна!*\n\n"
            f"🎁 {product['name']}\n"
            f"💸 Списано: {product['price']} XP\n\n"
            f"Переглянь свої покупки: /inventory",
            parse_mode="Markdown",
        )
    else:
        await query.answer("❌ Помилка покупки", show_alert=True)


async def shop_callback_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    user = update.effective_user
    if data.startswith("shop_buy_"):
        product_id = int(data.split("_")[-1])
        await handle_shop_buy(query, user.id, product_id)


@admin_only
@rate_limit_user
async def cmd_addproduct(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    lang = get_user_language(user.id)
    try:
        price = int(ctx.args[0])
        name = ctx.args[1]
        description = " ".join(ctx.args[2:])
        if not name or price <= 0:
            raise ValueError
    except (IndexError, ValueError):
        await _reply(update, get_message("format_addproduct", lang))
        return
    product_id = add_product(name, description, price)
    await _reply(update, get_message("product_added", lang, product_id=product_id, name=name, price=price))


@admin_only
@rate_limit_user
async def cmd_delproduct(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    lang = get_user_language(user.id)
    try:
        product_id = int(ctx.args[0])
        delete_product(product_id)
        await _reply(update, get_message("product_deleted", lang, product_id=product_id))
    except (IndexError, ValueError):
        await _reply(update, get_message("format_addproduct", lang))


@admin_only
@rate_limit_user
async def cmd_editproduct(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    lang = get_user_language(user.id)
    try:
        product_id = int(ctx.args[0])
        price = int(ctx.args[1])
        name = ctx.args[2]
        description = " ".join(ctx.args[3:])
        update_product(product_id, name=name, description=description, price=price)
        await _reply(update, get_message("product_updated", lang, product_id=product_id, name=name, price=price))
    except (IndexError, ValueError):
        await _reply(update, get_message("format_editproduct", lang))


def _admin_menu_markup(lang: str = "uk", dept_id: int | None = None) -> InlineKeyboardMarkup:
    """Build admin menu. If dept_id provided, shows dept-specific options."""
    dept_info = ""
    if dept_id:
        dept = get_department(dept_id)
        dept_info = f"\n📍 Відділ: {dept['emoji']} {dept['name']}"
    
    return InlineKeyboardMarkup(
        [
            [_btn(get_message("admin_add_task_btn", lang), callback_data=f"a:add:{dept_id or 'g'}")],
            [_btn(get_message("admin_delete_task_btn", lang), callback_data=f"a:dellist:0:{f'd{dept_id}' if dept_id else 'g'}")],
            [_btn(get_message("admin_users_btn", lang), callback_data="a:users:0")],
            [_btn(get_message("admin_ideas_btn", lang), callback_data=f"a:ideas:0:{f'd{dept_id}' if dept_id else 'g'}")],
            [_btn(get_message("admin_xp_btn", lang), callback_data=f"a:xp:{dept_id or 'g'}")],
            [_btn(get_message("admin_stats_btn", lang), callback_data=f"a:stats:{dept_id or 'g'}")],
            [_btn(get_message("admin_shop_btn", lang), callback_data="a:shop_list")],
            [_btn(get_message("admin_edit_info_btn", lang), callback_data="be:menu")],
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


def _bot_infoedit_markup(lang: str = "uk") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [_btn(get_message("admin_edit_text_btn", lang), callback_data="be:edit:welcome_text")],
            [_btn(get_message("admin_edit_help_btn", lang), callback_data="be:edit:help_text")],
            [_btn(get_message("admin_preview_btn", lang), callback_data="be:preview")],
            [_btn(get_message("admin_botfather_info", lang), callback_data="be:limits")],
            [_btn(get_message("admin_back_menu", lang), callback_data="a:menu")],
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


# ========== NAVIGATION STACK HELPERS ==========
def push_nav(ctx: ContextTypes.DEFAULT_TYPE, screen_name: str):
    """Push current screen to navigation history"""
    if "nav_stack" not in ctx.user_data:
        ctx.user_data["nav_stack"] = []
    ctx.user_data["nav_stack"].append(screen_name)
    logger.debug(f"Navigation stack: {ctx.user_data['nav_stack']}")


def pop_nav(ctx: ContextTypes.DEFAULT_TYPE) -> str | None:
    """Pop last screen from navigation history"""
    if "nav_stack" not in ctx.user_data or not ctx.user_data["nav_stack"]:
        return None
    screen = ctx.user_data["nav_stack"].pop()
    logger.debug(f"Navigation stack (after pop): {ctx.user_data['nav_stack']}")
    return screen


async def go_back(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Navigate back to previous screen or menu"""
    prev_screen = pop_nav(ctx)
    
    if prev_screen is None:
        # No history, go to menu
        await cmd_menu(update, ctx)
        return
    
    # Map screen names to command functions
    screen_map = {
        "menu": cmd_menu,
        "tasks": cmd_tasks,
        "shop": cmd_shop,
        "inventory": cmd_inventory,
        "achievements": cmd_achievements,
        "about": cmd_about,
        "help": cmd_help,
        "info": cmd_info,
        "settings": cmd_settings,
        "leaderboard": cmd_leaderboard,
        "idea": cmd_idea,
        "idea_anon": lambda u, c: handle_idea_submission(u, c),  # Go back to step 1
    }
    
    if prev_screen in screen_map:
        try:
            await screen_map[prev_screen](update, ctx)
        except Exception as e:
            logger.error(f"Error going back to {prev_screen}: {e}")
            await cmd_menu(update, ctx)
    else:
        logger.warning(f"Unknown screen in navigation: {prev_screen}")
        await cmd_menu(update, ctx)


@rate_limit_user
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Startup flow: fully registered → welcome | has language → verify | new → select language"""
    user = update.effective_user
    register_user(user)
    
    lang = get_user_language(user.id)
    depts = get_user_departments(user.id) or []
    
    logger.info(f"👤 /start від {user.id}: depts={depts}, lang={lang}")
    
    # 🔄 ALWAYS check current subscription status (even for fully registered users)
    logger.info(f"🔍 Перевіряю поточний статус підписки для {user.id}...")
    is_subscribed = await check_channel_subscription(ctx.bot, user.id, TELEGRAM_CHANNEL_ID)
    db_user = get_user(user.id)
    is_verified_in_db = db_user['is_verified'] if db_user else 0
    
    # Sync verification status with actual subscription
    if is_subscribed and not is_verified_in_db:
        logger.info(f"✅ Користувач {user.id} підписаний, але позначений як невверифікований - виправляю")
        mark_verified(user.id)
    elif not is_subscribed and is_verified_in_db:
        logger.info(f"❌ Користувач {user.id} не підписаний, але позначений як верифікований - виправляю")
        mark_unverified(user.id)
    
    # 1️⃣ User is fully registered - remind them to use /menu
    if depts:
        msg = "uk" if lang == "uk" else "ro" if lang == "ro" else "en"
        reminders = {
            "uk": "✅ Ви вже зареєстровані!\n\nНапишіть /menu аби переглянути команди.",
            "en": "✅ You are already registered!\n\nType /menu to see commands.",
            "ro": "✅ Sunteți deja înregistrat!\n\nScrieti /menu pentru a vedea comenzile."
        }
        await _reply(update, reminders[msg])
        logger.info(f"✅ Користувач {user.id} вже зареєстрований - нагадано про /menu")
        return
    
    # 2️⃣ User has language but no departments - go to verification
    if lang and lang != "default":
        logger.info(f"🔄 Користувач {user.id} має мову ({lang}) - переходимо до перевірки")
        await process_subscription_verification(update, ctx)
        return
    
    # 3️⃣ New user - ask for language
    logger.info(f"🆕 Новий користувач {user.id} - питаємо мову")
    await show_language_selection(update)



@rate_limit_user
async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Show help/documentation."""
    user = update.effective_user
    register_user(user)
    
    lang = get_user_language(user.id)
    push_nav(ctx, "menu")
    
    markup = InlineKeyboardMarkup([
        [_btn(get_message("support_btn", lang), callback_data="support_write")],
        [_btn(get_message("back_btn", lang), callback_data="go_back")]
    ])
    
    help_text = f"{get_message('help_header', lang)}\n\n{get_message('help_content', lang)}"
    await _reply(update, help_text, reply_markup=markup, parse_mode="Markdown")


@rate_limit_user
async def cmd_about(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Show information about the bot."""
    user = update.effective_user
    lang = get_user_language(user.id)
    
    about_text = f"{get_message('about_header', lang)}\n\n{get_message('about_content', lang)}"
    
    push_nav(ctx, "menu")
    markup = InlineKeyboardMarkup([
        [_btn(get_message("back_btn", lang), callback_data="go_back")]
    ])
    
    await _reply(update, about_text, reply_markup=markup, parse_mode="Markdown")


@rate_limit_user
async def cmd_info(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Show user's profile information."""
    user = update.effective_user
    register_user(user)
    
    push_nav(ctx, "info")
    
    # 🔄 Update verification status before showing profile
    is_subscribed = await check_channel_subscription(ctx.bot, user.id, TELEGRAM_CHANNEL_ID)
    db_user = get_user(user.id)
    is_verified_in_db = db_user['is_verified'] if db_user else 0
    
    if is_subscribed and not is_verified_in_db:
        mark_verified(user.id)
    elif not is_subscribed and is_verified_in_db:
        mark_unverified(user.id)
    
    # Get fresh data after potential verification update
    db_user = get_user(user.id)
    lang = get_user_language(user.id)
    depts = get_user_departments(user.id) or []
    
    # Get user's departments
    dept_names = []
    if depts:
        all_depts = get_departments()
        dept_names = [d['name'] for d in all_depts if d['id'] in depts]
    
    # Registration date (without time)
    joined_date = db_user['joined_at'][:10] if db_user['joined_at'] else "N/A"
    
    # Format department list
    dept_str = "\n".join([f"  • {name}" for name in dept_names]) if dept_names else get_message("info_none_selected", lang)
    
    verified_status = get_message("info_verified_yes", lang) if db_user['is_verified'] else get_message("info_verified_no", lang)
    
    text = (
        f"{get_message('info_header', lang)}\n\n"
        f"{get_message('info_id', lang)}: `{user.id}`\n"
        f"{get_message('info_name', lang)}: {user.first_name or 'N/A'}\n"
        f"{get_message('info_registered', lang)}: {joined_date}\n"
        f"{get_message('info_verified', lang)}: {verified_status}\n\n"
        f"{get_message('info_xp_section', lang)}\n"
        f"• {get_message('info_xp_current', lang)}: {db_user['xp']}\n"
        f"• {get_message('info_xp_total', lang)}: {db_user['total_xp']}\n"
        f"• {get_message('info_xp_spent', lang)}: {db_user['total_xp'] - db_user['spendable_xp']}\n\n"
        f"{get_message('info_departments', lang)}\n{dept_str}"
    )
    
    markup = InlineKeyboardMarkup([[_btn(get_message("back_btn", lang), callback_data="go_back")]])
    
    await _reply(update, text, reply_markup=markup, parse_mode="Markdown")


@rate_limit_user
async def cmd_settings(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Show settings menu where user can change department."""
    user = update.effective_user
    register_user(user)
    
    lang = get_user_language(user.id)
    
    push_nav(ctx, "menu")
    # Show settings menu with options
    markup = InlineKeyboardMarkup([
        [_btn(get_message("settings_dept_btn", lang), callback_data="settings_depts")],
        [_btn(get_message("settings_lang_btn", lang), callback_data="lang_select")],
        [_btn(get_message("back_btn", lang), callback_data="go_back")],
    ])
    
    settings_text = f"{get_message('settings_header', lang)}\n\n{get_message('settings_prompt', lang)}"
    
    await _reply(update, settings_text, reply_markup=markup, parse_mode="Markdown")


@rate_limit_user
async def cmd_leaderboard(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Show leaderboard options: global or by department."""
    user = update.effective_user
    register_user(user)
    
    lang = get_user_language(user.id)
    push_nav(ctx, "menu")
    depts = get_user_departments(user.id) or []
    departments = get_departments()
    
    # Build keyboard with department options + global option
    rows = []
    rows.append([_btn(get_message("leaderboard_global_btn", lang), callback_data="lb:global")])
    
    if depts and departments:
        for dept in departments:
            if dept['id'] in depts:
                dept_label = get_message("leaderboard_department", lang, dept=f"{dept['emoji']} {dept['name']}")
                rows.append([_btn(dept_label, callback_data=f"lb:dept_{dept['id']}")])
    
    rows.append([_btn(get_message("back_btn", lang), callback_data="go_back")])
    
    markup = InlineKeyboardMarkup(rows)
    header = f"{get_message('leaderboard_header', lang)}\n{get_message('leaderboard_prompt', lang)}"
    
    await _reply(update, header, reply_markup=markup, parse_mode="Markdown")


@rate_limit_user
async def cmd_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Show main menu for registered users."""
    user = update.effective_user
    register_user(user)
    
    lang = get_user_language(user.id)
    depts = get_user_departments(user.id)
    
    if not depts:
        await _reply(update, get_message("dept_required", lang))
        return
    
    text = get_message("menu_prompt", lang)
    
    # Add admin option if user is admin
    if user.id in ADMIN_IDS:
        admin_text = "🛠 /admin — адмін-панель" if lang == "uk" else "🛠 /admin — admin panel" if lang == "en" else "🛠 /admin — panou admin"
        text += f"\n{admin_text}"
    
    await _reply(update, text, parse_mode="Markdown")


@admin_only
@rate_limit_user
async def cmd_admin(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Admin panel."""
    user = update.effective_user
    register_user(user)
    
    db_user = get_user(user.id)
    
    if db_user["is_banned"]:
        lang = get_user_language(user.id)
        await _reply(update, get_message("banned", lang))
        return
    
    lang = get_user_language(user.id)
    _clear_wizard(ctx)
    await _reply(update,
        get_message("admin_panel_header", lang),
        reply_markup=_admin_menu_markup(lang),
        parse_mode="Markdown")


@rate_limit_user
async def cmd_tasks(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Show task categories (Easy/Medium/Hard) for user to select."""
    user = update.effective_user
    register_user(user)
    
    lang = get_user_language(user.id)
    db_user = get_user(user.id)
    user_depts = get_user_departments(user.id)
    if not user_depts:
        await _reply(update, get_message("dept_required", lang))
        return
    
    push_nav(ctx, "menu")
    # Show category menu
    markup = InlineKeyboardMarkup([
        [_btn(get_message("tasks_easy_btn", lang), callback_data="tasks_easy")],
        [_btn(get_message("tasks_medium_btn", lang), callback_data="tasks_medium")],
        [_btn(get_message("tasks_hard_btn", lang), callback_data="tasks_hard")],
        [_btn(get_message("back_btn", lang), callback_data="go_back")],
    ])
    
    await _reply(update,
        get_message("tasks_select_difficulty", lang),
        reply_markup=markup,
        parse_mode="Markdown")


async def handle_tasks_category(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle task category selection and display filtered tasks."""
    query = update.callback_query
    await _query_answer(query)
    
    user = query.from_user
    data = query.data
    
    # Extract difficulty level
    difficulty_map = {
        "tasks_easy": "easy",
        "tasks_medium": "medium",
        "tasks_hard": "hard",
    }
    
    difficulty = difficulty_map.get(data)
    if not difficulty:
        return
    
    user_depts = get_user_departments(user.id)
    if not user_depts:
        await _query_answer(query, "❌ Обери департамент через /start", show_alert=True)
        return
    
    # Get filtered tasks for primary department
    user_dept_id = user_depts[0]
    tasks = get_tasks_filtered(difficulty, user_dept_id)
    
    if not tasks:
        await _edit_message_text(query,
            f"😕 На жаль, завдань рівня «{difficulty}» немає.\n\n"
            "Спробуй інший рівень складності!",
            reply_markup=InlineKeyboardMarkup([
                [_btn("📗 Легкі", callback_data="tasks_easy")],
                [_btn("📙 Середні", callback_data="tasks_medium")],
                [_btn("📕 Важкі", callback_data="tasks_hard")],
            ]),
            parse_mode="Markdown")
        return
    
    # Display tasks
    cat_names = {"easy": "Легкі", "medium": "Середні", "hard": "Важкі"}
    await _edit_message_text(query,
        f"📋 *{cat_names[difficulty]} завдання*\n\n"
        f"Нижче показані завдання для твого департаменту.",
        parse_mode="Markdown")
    
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
        
        await _reply(update, text, 
                    reply_markup=InlineKeyboardMarkup([[btn]]),
                    parse_mode="Markdown")



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
async def cmd_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    lang = get_user_language(user.id)
    had_submission = bool(ctx.user_data.pop("submitting_task_id", None))
    had_wizard = bool(ctx.user_data.pop("admin_wizard", None))

    if had_submission or had_wizard:
        await _reply(update, get_message("cancel_success", lang))
    else:
        await _reply(update, get_message("cancel_no_action", lang))


@admin_only
@rate_limit_user
async def cmd_bot_infoedit(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    lang = get_user_language(user.id)
    _clear_wizard(ctx)
    await _reply(update, get_message("bot_infoedit", lang), reply_markup=_bot_infoedit_markup(lang), parse_mode="Markdown")


@admin_only
@rate_limit_user
async def cmd_help_admin(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await _reply(
        update,
        (
            "🛠 *Admin Help*\n\n"
            "`/admin` — відкрити адмін-меню (потребує обраного відділу).\n"
            "`/bot_infoedit` — змінити тексти /start і /help.\n"
            "`/help_admin` — ця довідка.\n\n"
            "*Важливо:*\n"
            "Адміністратори повинні мати обраний відділ для доступу до адмін-панелі.\n"
            "Напиши /start щоб обрати свій відділ.\n\n"
            "*Legacy команди:*\n"
            "`/addtask <XP> <назва> | <опис>` — додати задачу.\n"
            "`/deltask <task_id>` — деактивувати задачу.\n"
            "`/givexp <user_id> <amount>` — нарахувати/зняти XP.\n"
            "`/stats` — загальна статистика.\n"
            "`/cancel` — скасувати активний wizard.\n\n"
            "*В адмін-меню також є:*\n"
            "• Керування користувачами (перегляд, ban/unban)\n"
            "• Покрокове додавання задач\n"
            "• Покрокове нарахування XP\n"
            "• Статистика по відділам\n"
            "• Управління магазином товарів"
        ),
        parse_mode="Markdown",
    )


@admin_only
@rate_limit_user
async def cmd_addtask(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    lang = get_user_language(user.id)
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
        format_text = {
            "en": "❌ Format: /addtask <XP> <name> | <description>\nExample: /addtask 50 Write a review | Write a review about the bot",
            "ro": "❌ Format: /addtask <XP> <nume> | <descriere>\nExemplu: /addtask 50 Scrie o recenzie | Scrie o recenzie despre bot",
            "uk": "❌ Формат: /addtask <XP> <назва> | <опис>\nПриклад: /addtask 50 Написати відгук | Напиши відгук про бот",
        }.get(lang, "❌ Format: /addtask <XP> <name> | <description>")
        await _reply(update, format_text)
        return

    task_id = add_task(title, description, xp)
    await _reply(update, get_message("task_added", lang, task_id=task_id, title=title, xp=xp))


@admin_only
@rate_limit_user
async def cmd_deltask(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    lang = get_user_language(user.id)
    try:
        task_id = int(ctx.args[0])
        delete_task(task_id)
        await _reply(update, get_message("task_deleted", lang, task_id=task_id))
    except (IndexError, ValueError):
        await _reply(update, get_message("format_deltask", lang))


@admin_only
@rate_limit_user
async def cmd_givexp(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    lang = get_user_language(user.id)
    try:
        uid = int(ctx.args[0])
        amount = int(ctx.args[1])
        if amount >= 0:
            add_xp(uid, amount)
            await _reply(update, get_message("xp_given", lang, amount=amount, user_id=uid))
        else:
            admin_subtract_xp(uid, -amount)
            await _reply(update, get_message("xp_removed", lang, amount=-amount, user_id=uid))
    except (IndexError, ValueError):
        await _reply(update, get_message("format_givexp", lang))


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


def _render_users_filter_menu() -> tuple[str, InlineKeyboardMarkup]:
    """Show menu to choose: all users or users by department"""
    lines = [
        "👥 *Вибір фільтру користувачів*",
        "",
        "Що бачити?",
    ]
    
    departments = get_departments()
    rows = []
    
    # All users button
    rows.append([_btn("📊 Всі користувачі", callback_data="a:users:0:all")])
    
    # Separator
    rows.append([_btn("📍 За департаментами:", callback_data="noop")])
    
    # Department buttons
    for dept in departments:
        rows.append([_btn(f"{dept['emoji']} {dept['name']}", callback_data=f"a:users:0:d{dept['id']}")])
    
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
        nav.append(_btn("◀ Prev", callback_data=f"a:users:{page - 1}:all"))
    if page < total_pages - 1:
        nav.append(_btn("Next ▶", callback_data=f"a:users:{page + 1}:all"))
    if nav:
        rows.append(nav)
    rows.append([_btn("⬅ Назад", callback_data="a:users:")])

    return "\n".join(lines), InlineKeyboardMarkup(rows)


def _select_user_dept_for_role(target_user_id: int, page: int, back_callback: str = "a:users:") -> tuple[str, InlineKeyboardMarkup]:
    """Show department selection for editing user's department roles
    
    Args:
        target_user_id: User being edited
        page: Current page (unused, for consistency)
        back_callback: Callback to return to (default: users filter menu)
    """
    user = get_user_summary(target_user_id)
    user_depts = get_user_departments(target_user_id)
    
    lines = [
        f"👤 *Редагування ролей {_display_name(user)}*",
        "",
        "Выберіть департамент для редагування ролі:",
    ]
    
    rows = []
    if user_depts:
        for dept_id in user_depts:
            dept = get_department(dept_id)
            dept_role = get_user_dept_role(target_user_id, dept_id)
            role_emoji = {"supervisor": "📋", "coordinator": "⭐", "helper": "🌱", "member": "👤"}.get(dept_role, "👤")
            rows.append([_btn(f"{dept['emoji']} {dept['name']} {role_emoji}", callback_data=f"a:ud:{target_user_id}:{page}:d{dept_id}")])
    else:
        lines.append("_Користувач не належить до жодного департаменту._")
    
    rows.append([_btn("⬅ Назад", callback_data=back_callback)])
    
    return "\n".join(lines), InlineKeyboardMarkup(rows)


def _render_user_detail(target_user_id: int, page: int, admin_user_id: int | None = None, dept_id: int | None = None) -> tuple[str, InlineKeyboardMarkup] | tuple[None, None]:
    """Render user detail card with department roles
    
    Args:
        target_user_id: User being viewed
        page: Page number (for navigation back)
        admin_user_id: User viewing (to prevent self-modifications)
        dept_id: If specified, show only roles for this department and allow editing
    """
    user = get_user_summary(target_user_id)
    if not user:
        return None, None

    status = "banned" if user["is_banned"] else "active"
    global_role = get_user_global_role(target_user_id) or "user"
    
    # Format global role display
    global_role_emoji = {"admin": "👑", "it_admin": "🔧", "user": "👤"}.get(global_role, "❓")
    global_role_text = {
        "admin": "Адміністратор",
        "it_admin": "IT-супериор",
        "user": "Користувач"
    }.get(global_role, "Невідомо")
    
    lines = [
        "👤 *Картка користувача*",
        f"ID: `{user['user_id']}`",
        f"Username: {_display_name(user)}",
        f"Name: {user['first_name'] or '-'}",
        f"Joined: {user['joined_at'] or '-'}",
        f"🏆 Загальний XP: {user['total_xp']}",
        f"💰 Доступний XP: {user['spendable_xp']}",
        f"Status: *{status}*",
        f"{global_role_emoji} Глобальна роль: *{global_role_text}*",
        "",
    ]
    
    # Show department roles
    dept_roles = get_user_all_dept_roles(target_user_id)
    if dept_roles:
        lines.append("*Ролі в департаментах:*")
        for d_id in sorted(dept_roles.keys()):
            d_role = dept_roles[d_id]
            dept = get_department(d_id)
            role_emoji = {"supervisor": "📋", "coordinator": "⭐", "helper": "🌱", "member": "👤"}.get(d_role, "❓")
            role_text = {
                "supervisor": "Супервайзер",
                "coordinator": "Координатор",
                "helper": "Хелпер",
                "member": "Учасник"
            }.get(d_role, "Невідомо")
            lines.append(f"  {dept['emoji']} {dept['name']}: {role_emoji} {role_text}")
    else:
        lines.append("_Немає ролей в департаментах._")

    rows = []
    
    # Ban/Unban button
    if user["is_banned"]:
        action_btn = _btn("✅ Unban", callback_data=f"a:unban:{user['user_id']}:{page}")
    else:
        action_btn = _btn("🚫 Ban", callback_data=f"a:ban:{user['user_id']}:{page}")
    rows.append([action_btn])
    
    # If viewing specific department, show role buttons for that department
    if dept_id is not None:
        current_dept_role = get_user_dept_role(target_user_id, dept_id)
        dept = get_department(dept_id)
        
        lines.append(f"\n*Роль у {dept['emoji']} {dept['name']}:*")
        
        # Role buttons for this department (only if viewing a different user)
        if admin_user_id is None or target_user_id != admin_user_id:
            dept_role_buttons = []
            role_options = ["supervisor", "coordinator", "helper", "member"]
            for opt_role in role_options:
                if current_dept_role != opt_role:
                    role_emoji = {"supervisor": "📋", "coordinator": "⭐", "helper": "🌱", "member": "👤"}[opt_role]
                    role_text = {
                        "supervisor": "Супервайзер",
                        "coordinator": "Координатор",
                        "helper": "Хелпер",
                        "member": "Учасник"
                    }[opt_role]
                    dept_role_buttons.append(_btn(f"{role_emoji} {role_text}", callback_data=f"a:udrole:{target_user_id}:{dept_id}:{opt_role}:{page}"))
            
            if dept_role_buttons:
                rows.append(dept_role_buttons)
    
    # Back button - return to users filter menu
    rows.append([_btn("⬅ Назад", callback_data="a:users:")])

    markup = InlineKeyboardMarkup(rows)
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


def _render_user_page_by_dept(dept_id: int, page: int) -> tuple[str, InlineKeyboardMarkup]:
    """Render user page filtered by department."""
    # Get users in this department
    dept_users = get_users_in_department(dept_id)
    
    total = len(dept_users)
    total_pages = max(1, (total + ADMIN_USERS_PAGE_SIZE - 1) // ADMIN_USERS_PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    
    start = page * ADMIN_USERS_PAGE_SIZE
    chunk = dept_users[start : start + ADMIN_USERS_PAGE_SIZE]
    
    dept = get_department(dept_id)
    dept_name = f"{dept['emoji']} {dept['name']}" if dept else "Невідомий відділ"
    
    lines = [f"👥 *Користувачі {dept_name}* (сторінка {page + 1}/{total_pages})", ""]
    rows = []

    if not chunk:
        lines.append("Немає користувачів у цьому відділі.")
    else:
        for user in chunk:
            ban_mark = "🚫" if user["is_banned"] else ""
            lines.append(
                f"`{user['user_id']}` | {_display_name(user)} | 🏆 {user['total_xp']} XP | 💰 {user['spendable_xp']} XP {ban_mark}"
            )
            rows.append([_btn(f"Деталі {user['user_id']}", callback_data=f"a:ud:{user['user_id']}:{page}:d{dept_id}")])

    nav = []
    if page > 0:
        nav.append(_btn("◀ Prev", callback_data=f"a:users:{page - 1}:d{dept_id}"))
    if page < total_pages - 1:
        nav.append(_btn("Next ▶", callback_data=f"a:users:{page + 1}:d{dept_id}"))
    if nav:
        rows.append(nav)
    rows.append([_btn("⬅ Назад", callback_data="a:users:")])

    return "\n".join(lines), InlineKeyboardMarkup(rows)



def _render_task_page_by_dept(dept_id: int, page: int) -> tuple[str, InlineKeyboardMarkup]:
    """Render task page filtered by department."""
    # Get all tasks then filter by department
    all_tasks = get_tasks()
    dept_tasks = [t for t in all_tasks if t["department_id"] == dept_id]
    
    total_pages = max(1, (len(dept_tasks) + ADMIN_TASKS_PAGE_SIZE - 1) // ADMIN_TASKS_PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    start = page * ADMIN_TASKS_PAGE_SIZE
    chunk = dept_tasks[start : start + ADMIN_TASKS_PAGE_SIZE]

    dept = get_department(dept_id)
    dept_name = f"{dept['emoji']} {dept['name']}" if dept else "Невідомий відділ"
    
    lines = [f"🗑 *Видалення завдань ({dept_name})*", "Натисни на завдання для деактивації.", ""]
    rows = []

    for task in chunk:
        lines.append(f"#{task['id']} — {task['title']} ({task['xp_reward']} XP)")
        rows.append(
            [
                _btn(
                    f"Видалити #{task['id']}",
                    callback_data=f"a:del:{task['id']}:{page}:d{dept_id}",
                )
            ]
        )

    nav = []
    if page > 0:
        nav.append(_btn("◀ Prev", callback_data=f"a:dellist:{page - 1}:d{dept_id}"))
    if page < total_pages - 1:
        nav.append(_btn("Next ▶", callback_data=f"a:dellist:{page + 1}:d{dept_id}"))
    if nav:
        rows.append(nav)
    rows.append([_btn("⬅ В меню", callback_data="a:menu")])

    return "\n".join(lines), InlineKeyboardMarkup(rows)


def _render_ideas_page(page: int, user_id: int, role: str) -> tuple[str, InlineKeyboardMarkup]:
    """Render paginated list of ideas for admin review."""
    from datetime import datetime
    
    # Get unreviewed ideas filtered by role
    all_ideas = get_unreviewed_ideas(role=role, user_id=user_id)
    
    total = len(all_ideas)
    total_pages = max(1, (total + ADMIN_IDEAS_PAGE_SIZE - 1) // ADMIN_IDEAS_PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    
    start = page * ADMIN_IDEAS_PAGE_SIZE
    chunk = all_ideas[start : start + ADMIN_IDEAS_PAGE_SIZE]
    
    lines = [f"💡 *Нові ідеї* (сторінка {page + 1}/{total_pages})", ""]
    rows = []
    
    if not chunk:
        lines.append("Немає нових ідей.")
    else:
        for idea in chunk:
            # Format idea preview
            text_preview = idea["text"][:50].replace("\n", " ")
            if len(idea["text"]) > 50:
                text_preview += "..."
            
            # Author info
            if idea["is_anonymous"]:
                author = "🕵️ Анонім"
            else:
                author = f"👤 {idea['username']}"
            
            # Department emoji if available
            dept_emoji = ""
            if idea["department_id"]:
                dept = get_department(idea["department_id"])
                if dept:
                    dept_emoji = f" {dept['emoji']}"
            
            # Format the idea entry
            lines.append(f"*#{idea['id']}* {dept_emoji}")
            lines.append(f"  {author}")
            lines.append(f"  _{text_preview}_")
            lines.append("")
            
            # Buttons for this idea
            rows.append([
                _btn(f"✅ Розглянуто", callback_data=f"a:idea_mark:{idea['id']}:{page}"),
                _btn(f"🗑 Видалити", callback_data=f"a:idea_del:{idea['id']}:{page}"),
            ])
    
    # Navigation
    nav = []
    if page > 0:
        nav.append(_btn("◀ Prev", callback_data=f"a:ideas:{page - 1}"))
    if page < total_pages - 1:
        nav.append(_btn("Next ▶", callback_data=f"a:ideas:{page + 1}"))
    if nav:
        rows.append(nav)
    
    rows.append([_btn("⬅ В меню", callback_data="a:menu")])
    
    return "\n".join(lines), InlineKeyboardMarkup(rows)


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
    user_id = query.from_user.id
    
    logger.debug(f"Admin callback handler for user {user_id}: {data}")
    
    # Extract department context from callback data (format: "a:action:page:d<dept_id>" or "a:action:d<dept_id>")
    dept_id = None
    parts = data.split(":")
    for part in parts:
        if part.startswith("d") and part[1:].isdigit():
            dept_id = int(part[1:])
            break

    if data == "a:menu":
        user = query.from_user
        lang = get_user_language(user.id)
        _clear_wizard(ctx)
        # Use stored dept_id from context or extracted from callback
        if not dept_id and "admin_dept_id" in ctx.user_data:
            dept_id = ctx.user_data["admin_dept_id"]
        await _edit_message_text(query, get_message("admin_panel_header", lang), reply_markup=_admin_menu_markup(lang, dept_id), parse_mode="Markdown")
        return

    if data.startswith("a:add:"):
        dept_filter = data.split(":", 2)[2]
        dept_id = int(dept_filter[1:]) if dept_filter.startswith("d") else None
        await _start_admin_wizard(update, ctx, f"add_task:{dept_id or ''}")
        await _query_answer(query, "Майстер додавання запущено")
        return

    if data.startswith("a:dellist:"):
        page_str = data.split(":")[2] if len(data.split(":")) > 2 else "0"
        dept_filter = data.split(":")[3] if len(data.split(":")) > 3 else None
        page = int(page_str)
        dept_id = int(dept_filter[1:]) if dept_filter and dept_filter.startswith("d") else None
        
        if dept_id:
            text, markup = _render_task_page_by_dept(dept_id, page)
        else:
            text, markup = _render_task_page(page)
        await _edit_message_text(query, text=text, reply_markup=markup, parse_mode="Markdown")
        return

    if data.startswith("a:del:"):
        parts = data.split(":")
        task_id = int(parts[2])
        page = int(parts[3]) if len(parts) > 3 else 0
        dept_filter = parts[4] if len(parts) > 4 else None
        dept_id = int(dept_filter[1:]) if dept_filter and dept_filter.startswith("d") else None
        
        delete_task(task_id)
        
        if dept_id:
            text, markup = _render_task_page_by_dept(dept_id, page)
        else:
            text, markup = _render_task_page(page)
        
        await _edit_message_text(query, text=f"✅ Завдання #{task_id} деактивовано.\n\n{text}", reply_markup=markup, parse_mode="Markdown")
        return

    if data.startswith("a:users:"):
        logger.debug(f"Handling a:users: callback for user {user_id}")
        parts = data.split(":")
        page = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
        dept_filter = parts[3] if len(parts) > 3 and parts[3] else None
        
        # Handle special case: show filter menu
        if dept_filter is None:
            text, markup = _render_users_filter_menu()
            await _edit_message_text(query, text=text, reply_markup=markup, parse_mode="Markdown")
            logger.debug(f"Users filter menu shown for user {user_id}")
            return
        
        # Parse department filter
        if dept_filter == "all":
            text, markup = _render_user_page(page)
        elif dept_filter.startswith("d") and dept_filter[1:].isdigit():
            dept_id = int(dept_filter[1:])
            text, markup = _render_user_page_by_dept(dept_id, page)
        else:
            # Invalid filter, show menu again
            text, markup = _render_users_filter_menu()
        
        await _edit_message_text(query, text=text, reply_markup=markup, parse_mode="Markdown")
        logger.debug(f"User page rendered for user {user_id}")
        return

    if data.startswith("a:ud:"):
        parts = data.split(":")
        user_id = int(parts[2])
        page = int(parts[3])
        dept_filter = parts[4] if len(parts) > 4 else None
        dept_id = int(dept_filter[1:]) if dept_filter and dept_filter.startswith("d") else None
        
        # If no department specified, show department selection
        if dept_id is None:
            user_depts = get_user_departments(user_id)
            if not user_depts:
                # No departments for this user
                text, markup = _render_user_detail(user_id, page, query.from_user.id, None)
            elif len(user_depts) == 1:
                # Only one department, show its role directly
                text, markup = _render_user_detail(user_id, page, query.from_user.id, user_depts[0])
            else:
                # Multiple departments, show selection
                text, markup = _select_user_dept_for_role(user_id, page, back_callback="a:users:")
        else:
            # Department specified, show user detail for that department
            text, markup = _render_user_detail(user_id, page, query.from_user.id, dept_id)
        
        if not text:
            await _query_answer(query, "Користувача не знайдено", show_alert=True)
            return
        await _edit_message_text(query, text=text, reply_markup=markup, parse_mode="Markdown")
        return

    if data.startswith("a:ban:"):
        parts = data.split(":")
        user_id = int(parts[2])
        page = int(parts[3])
        dept_filter = parts[4] if len(parts) > 4 else None
        dept_id = int(dept_filter[1:]) if dept_filter and dept_filter.startswith("d") else None
        
        if user_id == query.from_user.id:
            await _query_answer(query, "Не можна забанити самого себе.", show_alert=True)
            return
        ok = ban_user(user_id)
        if not ok:
            await _query_answer(query, "Користувача не знайдено", show_alert=True)
            return
        
        # 📊 Log admin ban action
        log_admin_action('admin_action', admin_id=query.from_user.id, target_user_id=user_id,
                        action_data={'action': 'ban_user'})
        
        text, markup = _render_user_detail(user_id, page, query.from_user.id, dept_id)
        await _edit_message_text(query, text=f"🚫 Користувача забанено.\n\n{text}", reply_markup=markup, parse_mode="Markdown")
        return

    if data.startswith("a:unban:"):
        parts = data.split(":")
        user_id = int(parts[2])
        page = int(parts[3])
        dept_filter = parts[4] if len(parts) > 4 else None
        dept_id = int(dept_filter[1:]) if dept_filter and dept_filter.startswith("d") else None
        
        ok = unban_user(user_id)
        if not ok:
            await _query_answer(query, "Користувача не знайдено", show_alert=True)
            return
        
        # 📊 Log admin unban action
        log_admin_action('admin_action', admin_id=query.from_user.id, target_user_id=user_id,
                        action_data={'action': 'unban_user'})
        
        text, markup = _render_user_detail(user_id, page, query.from_user.id, dept_id)
        await _edit_message_text(query, text=f"✅ Бан знято.\n\n{text}", reply_markup=markup, parse_mode="Markdown")
        return

    if data.startswith("a:udrole:"):
        # Department role change: a:udrole:user_id:dept_id:new_role:page
        parts = data.split(":")
        target_user_id = int(parts[2])
        dept_id = int(parts[3])
        new_dept_role = parts[4]
        page = int(parts[5]) if len(parts) > 5 else 0
        
        # Validate department role
        if new_dept_role not in ["supervisor", "coordinator", "helper", "member"]:
            await _query_answer(query, "❌ Невідома роль", show_alert=True)
            return
        
        # Set the department role
        set_user_dept_role(target_user_id, dept_id, new_dept_role)
        
        # Refresh user detail
        text, markup = _render_user_detail(target_user_id, page, query.from_user.id, dept_id)
        dept = get_department(dept_id)
        role_emoji = {"supervisor": "📋", "coordinator": "⭐", "helper": "🌱", "member": "👤"}[new_dept_role]
        role_display = {
            "supervisor": "Супервайзер",
            "coordinator": "Координатор",
            "helper": "Хелпер",
            "member": "Учасник"
        }[new_dept_role]
        await _edit_message_text(query, text=f"✅ {role_emoji} Роль змінена на: *{role_display}* у {dept['emoji']} {dept['name']}\n\n{text}", 
                                reply_markup=markup, parse_mode="Markdown")
        logger.debug(f"User {target_user_id} role changed to {new_dept_role} in dept {dept_id}")
        return

    if data.startswith("a:urole:"):
        # Global role change: a:urole:user_id:new_role:page
        parts = data.split(":")
        target_user_id = int(parts[2])
        new_global_role = parts[3]
        page = int(parts[4]) if len(parts) > 4 else 0
        
        # Validate global role (only admin can set it_admin)
        if new_global_role not in ["user", "admin", "it_admin"]:
            await _query_answer(query, "❌ Невідома роль", show_alert=True)
            return
        
        # Only IT-admins can assign IT-admin role
        admin_global_role = get_user_global_role(query.from_user.id)
        if new_global_role == "it_admin" and admin_global_role != "it_admin":
            await _query_answer(query, "❌ Тільки IT-супериор може назначити IT-супериора", show_alert=True)
            return
        
        # Set the global role
        set_user_global_role(target_user_id, new_global_role)
        
        # 📊 Log admin role change action
        log_admin_action('admin_action', admin_id=query.from_user.id, target_user_id=target_user_id,
                        action_data={'action': 'set_global_role', 'role': new_global_role})
        
        # Refresh user detail (display roles for first department if any)
        user_depts = get_user_departments(target_user_id)
        dept_id = user_depts[0] if user_depts else None
        text, markup = _render_user_detail(target_user_id, page, query.from_user.id, dept_id)
        
        role_emoji = {"admin": "👑", "it_admin": "🔧", "user": "👤"}[new_global_role]
        role_display = {
            "admin": "Адміністратор",
            "it_admin": "IT-супериор",
            "user": "Користувач"
        }[new_global_role]
        await _edit_message_text(query, text=f"✅ {role_emoji} Глобальна роль змінена на: *{role_display}*\n\n{text}", 
                                reply_markup=markup, parse_mode="Markdown")
        logger.debug(f"User {target_user_id} global role changed to {new_global_role}")
        return

    if data.startswith("a:ideas:"):
        logger.debug(f"Handling a:ideas: callback for user {user_id}")
        parts = data.split(":")
        page = int(parts[2]) if len(parts) > 2 else 0
        dept_filter = parts[3] if len(parts) > 3 else None
        
        role = get_user_role(user_id) or "user"
        
        text, markup = _render_ideas_page(page, user_id, role)
        await _edit_message_text(query, text=text, reply_markup=markup, parse_mode="Markdown")
        logger.debug(f"Ideas page rendered for user {user_id} with role {role}")
        return

    if data.startswith("a:idea_mark:"):
        parts = data.split(":")
        idea_id = int(parts[2])
        page = int(parts[3]) if len(parts) > 3 else 0
        
        mark_idea_status(idea_id, "reviewed")
        
        user_id = query.from_user.id
        role = get_user_role(user_id) or "user"
        
        text, markup = _render_ideas_page(page, user_id, role)
        await _edit_message_text(query, text=f"✅ Ідея #{idea_id} позначена як розглянута.\n\n{text}", reply_markup=markup, parse_mode="Markdown")
        return

    if data.startswith("a:idea_del:"):
        parts = data.split(":")
        idea_id = int(parts[2])
        page = int(parts[3]) if len(parts) > 3 else 0
        
        # Delete idea from database
        delete_ok = delete_idea(idea_id)
        
        if not delete_ok:
            await _query_answer(query, "Ідея не знайдена", show_alert=True)
            return
        
        user_id = query.from_user.id
        role = get_user_role(user_id) or "user"
        
        text, markup = _render_ideas_page(page, user_id, role)
        await _edit_message_text(query, text=f"🗑 Ідея #{idea_id} видалена.\n\n{text}", reply_markup=markup, parse_mode="Markdown")
        return

    if data.startswith("a:stats:"):
        dept_filter = data.split(":")[2] if len(data.split(":")) > 2 else None
        dept_id = int(dept_filter[1:]) if dept_filter and dept_filter.startswith("d") else None
        
        users, tasks, pending, approved = get_stats()
        dept_label = ""
        if dept_id:
            dept = get_department(dept_id)
            dept_label = f" ({dept['emoji']} {dept['name']})"
        
        await _edit_message_text(query, 
            text=(
                f"📊 *Статистика{dept_label}*\n\n"
                f"👥 Користувачів: {users}\n"
                f"📋 Активних завдань: {tasks}\n"
                f"⏳ На перевірці: {pending}\n"
                f"✅ Схвалено: {approved}"
            ),
            reply_markup=InlineKeyboardMarkup([[_btn("⬅ В меню", callback_data="a:menu")]]),
            parse_mode="Markdown",
        )
        return

    if data.startswith("a:xp:"):
        logger.debug(f"Handling a:xp: callback for user {user_id}")
        dept_filter = data.split(":")[2] if len(data.split(":")) > 2 else None
        dept_id = int(dept_filter[1:]) if dept_filter and dept_filter.startswith("d") else None
        
        await _start_admin_wizard(update, ctx, f"give_xp:{dept_id or ''}")
        await _query_answer(query, "Майстер нарахування XP запущено")
        logger.debug(f"XP wizard started for user {user_id}")
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
        user = query.from_user
        lang = get_user_language(user.id)
        _clear_wizard(ctx)
        await _edit_message_text(query, 
            text=get_message("bot_infoedit", lang),
            reply_markup=_bot_infoedit_markup(lang),
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
        user = query.from_user
        lang = get_user_language(user.id)
        welcome_preview = _get_text_setting("welcome_text", first_name="Ім'я")
        help_preview = _get_text_setting("help_text")
        text = (
            "*Поточні тексти*\n\n"
            "*/start:*\n"
            f"{welcome_preview}\n\n"
            "*/help:*\n"
            f"{help_preview}"
        )
        await _edit_message_text(query, text=text, reply_markup=_bot_infoedit_markup(lang), parse_mode="Markdown")
        return

    if data == "be:limits":
        user = query.from_user
        lang = get_user_language(user.id)
        text = get_message("admin_botfather_limits", lang)
        await _edit_message_text(query, text=text, reply_markup=_bot_infoedit_markup(lang), parse_mode="Markdown")
        return


@rate_limit_user
async def on_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await _query_answer(query)
    data = query.data

    if data == "noop":
        return

    # Handle support message writing
    if data == "support_write":
        user = query.from_user
        lang = get_user_language(user.id)
        
        logger.info(f"📧 Support button clicked by {user.id}, setting waiting_for_support=True")
        
        # Set flag to catch next message as support message
        ctx.user_data["waiting_for_support"] = True
        ctx.user_data["support_lang"] = lang
        
        text = get_message("support_prompt", lang)
        logger.info(f"📧 Sending support prompt to {user.id}")
        await _reply(update, text, parse_mode="Markdown")
        return

    # Handle leaderboard selection
    if data.startswith("lb:"):
        user_id = query.from_user.id
        lb_type = data[3:]  # "global" or "dept_X"
        lang = get_user_language(user_id)
        
        medals = ["🥇", "🥈", "🥉"]
        
        if lb_type == "global":
            # Global leaderboard
            top = get_leaderboard()
            logger.info(f"📊 Global leaderboard requested. Got {len(top) if top else 0} users")
            title = "🏆 Таблиця лідерів (кумулятивний XP)"
        else:
            # Department leaderboard
            dept_id = int(lb_type.split("_")[1])
            users_in_dept = get_users_in_department(dept_id)
            
            # Sort by total_xp
            top = sorted(users_in_dept, key=lambda u: u.get('total_xp', 0), reverse=True)[:10]
            logger.info(f"📊 Department {dept_id} leaderboard requested. Got {len(top) if top else 0} users")
            
            dept = get_department(dept_id)
            dept_name = dept['name'] if dept else "Unknown"
            title = f"📊 {dept_name}"
        
        if not top:
            await _query_answer(query, "🏆 Таблиця порожня", show_alert=True)
            return
        
        lines = [title]
        for i, user in enumerate(top):
            icon = medals[i] if i < 3 else f"{i + 1}."
            # For both global and dept leaderboards, access row data using bracket notation
            try:
                xp_val = user['total_xp']
            except (KeyError, TypeError):
                xp_val = 0
            lines.append(f"{icon} {_display_name(user)} — {xp_val} XP")
        
        # Add back button
        back_markup = InlineKeyboardMarkup([[_btn(get_message("back_btn", lang), callback_data="go_back")]])
        await _edit_message_text(query, "\n".join(lines), reply_markup=back_markup)
        return
    
    # Handle settings menu
    if data == "settings_depts":
        user_id = query.from_user.id
        lang = get_user_language(user_id)
        
        # Initialize context for department selection
        ctx.user_data["selected_depts"] = get_user_departments(user_id) or []
        
        # Show department selection
        departments = get_departments()
        selected = ctx.user_data["selected_depts"]
        
        rows = []
        for dept in departments:
            is_selected = dept['id'] in selected
            check = "✓" if is_selected else "☐"
            btn_text = f"{check} {dept['emoji']} {dept['name']}"
            rows.append([_btn(btn_text, callback_data=f"dept_toggle_{dept['id']}")])
        
        # Add Done button
        rows.append([_btn(get_message("dept_btn_done", lang), callback_data="dept_done")])
        
        rows.append([_btn(get_message("back_btn", lang), callback_data="settings_depts_cancel")])
        
        dept_change_prompt = get_message("dept_multi_select", lang)
        await _edit_message_text(query,
            dept_change_prompt,
            reply_markup=InlineKeyboardMarkup(rows),
            parse_mode="Markdown")
        return
    
    if data == "settings_depts_cancel":
        await cmd_settings(update, ctx)
        return
    
    # Unified back button handler
    if data == "go_back":
        # Clean up any pending operation state
        ctx.user_data.pop("submitting_idea", None)
        ctx.user_data.pop("idea_draft", None)
        ctx.user_data.pop("submitting_task_id", None)
        
        await go_back(update, ctx)
        return

    # Handle change departments button (legacy, from menu)
    if data == "change_depts":
        user_id = query.from_user.id
        lang = get_user_language(user_id)
        
        # Initialize context for department selection
        ctx.user_data["selected_depts"] = get_user_departments(user_id) or []
        
        # Show department selection again
        departments = get_departments()
        selected = ctx.user_data["selected_depts"]
        
        rows = []
        for dept in departments:
            is_selected = dept['id'] in selected
            check = "✓" if is_selected else "☐"
            btn_text = f"{check} {dept['emoji']} {dept['name']}"
            rows.append([_btn(btn_text, callback_data=f"dept_toggle_{dept['id']}")])
        
        # Add Done button
        rows.append([_btn(get_message("dept_btn_done", lang), callback_data="dept_done")])
        
        back_text = "⬅ Back" if lang == "en" else "⬅ Înapoi" if lang == "ro" else "⬅ Назад"
        rows.append([_btn(back_text, callback_data="lang_select")])
        
        await _edit_message_text(query,
            get_message("dept_multi_select", lang),
            reply_markup=InlineKeyboardMarkup(rows),
            parse_mode="Markdown")
        return

    # Admin panel callbacks - check permissions
    if data.startswith("a:") or data.startswith("be:"):
        user_id = query.from_user.id
        if user_id not in ADMIN_IDS:
            await _query_answer(query, "❌ Тільки для адмінів!", show_alert=True)
            logger.warning(f"Unauthorized admin callback attempt from user {user_id}: {data}")
            return
        logger.debug(f"Admin callback from {user_id}: {data}")
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
        
        lang = get_user_language(user.id)
        push_nav(ctx, "tasks")
        markup = InlineKeyboardMarkup([
            [_btn(get_message("cancel_btn", lang), callback_data="go_back")]
        ])

        await query.message.reply_text(
            get_message("task_submit_prompt", lang, title=task['title']),
            reply_markup=markup,
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
        task_dict = dict(task) if task else {}  # Convert Row to dict for .get() access
        admin_tag = f"@{query.from_user.username}" if query.from_user.username else query.from_user.first_name

        if action == "approve":
            add_xp(sub["user_id"], task["xp_reward"])
            
            # 📊 Log task approval and XP award events
            log_event('task_approved', user_id=sub["user_id"], admin_id=query.from_user.id, data={
                'submission_id': sub_id,
                'task_id': sub["task_id"],
                'task_title': task_dict.get('title', '')[:50],
                'xp_awarded': task["xp_reward"]
            })
            log_event('xp_awarded', user_id=sub["user_id"], data={
                'amount': task["xp_reward"],
                'source': 'task_approval',
                'task_id': sub["task_id"]
            })
            
            result_icon = "✅ Схвалено"
            user_msg = (
                f"🎉 *Завдання підтверджено!*\n\n"
                f"✅ «{task['title']}» — зараховано!\n"
                f"💎 +{task['xp_reward']} XP нараховано!\n\n"
                f"Переглянь профіль: /xp"
            )
        else:
            # 📊 Log task rejection event
            log_event('task_rejected', user_id=sub["user_id"], admin_id=query.from_user.id, data={
                'submission_id': sub_id,
                'task_id': sub["task_id"],
                'task_title': task_dict.get('title', '')[:50]
            })
            
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
        lang = get_user_language(user.id)
        await _reply(update, get_message("task_not_found", lang))
        ctx.user_data.pop("submitting_task_id", None)
        return

    proof_text = update.message.text or update.message.caption or ""
    proof_file_id = None

    if update.message.photo:
        proof_file_id = update.message.photo[-1].file_id
    elif update.message.document:
        proof_file_id = update.message.document.file_id

    if not proof_text and not proof_file_id:
        lang = get_user_language(user.id)
        await _reply(update, get_message("no_proof", lang))
        return

    sub_id = add_submission(user.id, task_id, proof_text, proof_file_id)
    ctx.user_data.pop("submitting_task_id", None)
    
    task_dict = dict(task) if task else {}  # Convert Row to dict for .get() access
    # 📊 Log task submission event
    log_event('task_submitted', user_id=user.id, data={
        'task_id': task_id,
        'submission_id': sub_id,
        'difficulty': task_dict.get('difficulty_level', 'unknown'),
        'title': task_dict.get('title', '')[:50]
    })

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
    """Handle text input for wizards and ideas."""
    user = update.effective_user
    
    logger.info(f"📝 Text input from {user.id}: waiting_for_support={ctx.user_data.get('waiting_for_support')}, submitting_idea={ctx.user_data.get('submitting_idea')}")
    
    # Check if user is submitting an idea
    if ctx.user_data.get("submitting_idea"):
        await handle_idea_submission(update, ctx)
        return
    
    # Check if user is writing support message
    if ctx.user_data.get("waiting_for_support"):
        message_text = (update.message.text or "").strip()
        logger.info(f"💬 Support message from {user.id}: {message_text[:50] if message_text else 'EMPTY'}")
        
        if not message_text:
            lang = ctx.user_data.get("support_lang", "en")
            await _reply(update, "❌ Повідомлення не може бути порожнім. Спробуй ще раз:")
            return
        
        lang = ctx.user_data.get("support_lang", "en")
        
        # Get user department info
        dept_name = "Unknown"
        try:
            dept_id = get_user_departments(user.id)
            if dept_id and len(dept_id) > 0:
                dept = get_department(dept_id[0])
                if dept:
                    dept_name = dept.get("name", "Unknown")
        except:
            pass
        
        # Format and send notification to admins
        notification = get_message("support_notification", "en").format(
            user_name=user.first_name or "User",
            user_id=user.id,
            department=dept_name,
            message=message_text
        )
        
        success_count = 0
        for admin_id in ADMIN_IDS:
            try:
                await ctx.bot.send_message(admin_id, notification, parse_mode="Markdown")
                success_count += 1
            except Exception as e:
                logger.error(f"Failed to send support message to admin {admin_id}: {e}")
        
        logger.info(f"✅ Support message from {user.id} sent to {success_count}/{len(ADMIN_IDS)} admins")
        
        # Confirm to user
        if success_count > 0:
            confirm_text = get_message("support_sent", lang)
            if not confirm_text:
                confirm_text = "✅ Ваше повідомлення надіслано розробнику. Дякуємо!"
        else:
            confirm_text = "❌ Помилка при відправці. Спробуй пізніше."
        
        await _reply(update, confirm_text)
        
        # Clear flag
        ctx.user_data["waiting_for_support"] = False
        return
    
    # Handle admin wizards
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


# ========== BACKGROUND JOBS ==========

async def verify_subscriptions_background_job(context: ContextTypes.DEFAULT_TYPE):
    """Weekly background job to check if verified users are still subscribed to channel."""
    logger.info("🔄 Running weekly subscription verification check...")
    
    users_to_check = get_users_needing_recheck()
    logger.info(f"Checking {len(users_to_check)} users for subscription status...")
    
    for user_id in users_to_check:
        try:
            is_subscribed = await check_channel_subscription(context.bot, user_id, TELEGRAM_CHANNEL_ID)
            if not is_subscribed:
                mark_unverified(user_id)
                logger.info(f"User {user_id} unsubscribed - marked as unverified")
        except Exception as e:
            logger.error(f"Error checking subscription for user {user_id}: {e}")
    
    logger.info("✅ Weekly subscription check completed!")


async def handle_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Handle all errors in command handlers"""
    logger.error(f"❌ ERROR: {context.error}")
    logger.error(f"Update: {update}")
    import traceback
    logger.error(traceback.format_exc())
    
    # Notify user if possible
    if update and hasattr(update, "message") and update.message:
        try:
            await update.message.reply_text(
                "❌ *Помилка!*\n\n"
                "Щось пішло не так. Спробуй ще раз або напиши /help для довідки.",
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Could not send error message to user: {e}")


def main():
    import sys
    import asyncio
    
    # Fix for Python 3.10+ on Windows - create event loop explicitly
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        if sys.platform == 'win32':
            loop = asyncio.ProactorEventLoop()
        else:
            loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    init_db()
    
    # 📊 Log bot startup
    from supervision import log_bot_startup
    users_count = count_users()
    depts_count = len(get_departments())
    pending_submissions = len([s for s in get_unreviewed_ideas() or []])  # Approximate
    log_bot_startup(users_count, depts_count, 0, 0)
    
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Add error handler to catch all errors
    app.add_error_handler(handle_error)
    
    # Product commands
    app.add_handler(CommandHandler("addproduct", cmd_addproduct))
    app.add_handler(CommandHandler("delproduct", cmd_delproduct))
    app.add_handler(CommandHandler("editproduct", cmd_editproduct))

    # Shop & Inventory
    app.add_handler(CommandHandler("shop", cmd_shop))
    app.add_handler(CommandHandler("inventory", cmd_inventory))

    # Main commands
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("menu", cmd_menu))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("about", cmd_about))
    app.add_handler(CommandHandler("info", cmd_info))
    app.add_handler(CommandHandler("settings", cmd_settings))
    app.add_handler(CommandHandler("tasks", cmd_tasks))
    app.add_handler(CommandHandler("xp", cmd_xp))
    app.add_handler(CommandHandler("leaderboard", cmd_leaderboard))
    app.add_handler(CommandHandler("cancel", cmd_cancel))
    
    # New commands
    app.add_handler(CommandHandler("idea", cmd_idea))
    app.add_handler(CommandHandler("achievements", cmd_achievements))
    
    # Admin commands
    app.add_handler(CommandHandler("admin", cmd_admin))
    app.add_handler(CommandHandler("bot_infoedit", cmd_bot_infoedit))
    app.add_handler(CommandHandler("help_admin", cmd_help_admin))

    app.add_handler(CommandHandler("addtask", cmd_addtask))
    app.add_handler(CommandHandler("deltask", cmd_deltask))
    app.add_handler(CommandHandler("givexp", cmd_givexp))
    app.add_handler(CommandHandler("stats", cmd_stats))

    # Startup flow callbacks
    app.add_handler(CallbackQueryHandler(handle_language_button, pattern="^lang_"))
    app.add_handler(CallbackQueryHandler(handle_change_language, pattern="^change_lang$"))
    app.add_handler(CallbackQueryHandler(handle_verify_retry, pattern="^verify_retry$"))
    app.add_handler(CallbackQueryHandler(handle_department_selection, pattern="^dept_"))
    app.add_handler(CallbackQueryHandler(handle_manage_depts, pattern="^manage_depts$"))
    app.add_handler(CallbackQueryHandler(handle_leave_dept, pattern="^dept_leave_"))
    app.add_handler(CallbackQueryHandler(handle_add_more_depts, pattern="^dept_add_mode$"))
    app.add_handler(CallbackQueryHandler(handle_tasks_category, pattern="^tasks_"))
    app.add_handler(CallbackQueryHandler(handle_idea_anonymity_choice, pattern="^idea_(named|anon)$"))
    
    # Shop & other callbacks
    app.add_handler(CallbackQueryHandler(shop_callback_handler, pattern="shop_buy_.*"))
    
    # Main buttons callback handler
    app.add_handler(CallbackQueryHandler(on_button))

    # Text and media handlers
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_input))
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL, handle_proof_media))

    # Add background job for weekly verification check
    job_queue = app.job_queue
    if job_queue:
        job_queue.run_repeating(verify_subscriptions_background_job, interval=3600*24*7, first=10)
        logger.info("✅ Background verification job scheduled")
    else:
        logger.warning("⚠️ Could not setup background job")

    logger.info("🤖 Бот запущено!")
    app.run_polling()



if __name__ == "__main__":
    main()



