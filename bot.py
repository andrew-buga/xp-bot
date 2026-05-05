import logging
import time
import asyncio
from collections import defaultdict, deque
from functools import wraps
from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, InputMediaPhoto
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from config import ADMIN_IDS, BOT_TOKEN, TELEGRAM_CHANNEL_ID
from messages import get_message, get_dept_name_translated
from analytics import log_event, log_admin_action
from database import (
    admin_subtract_xp,
    add_submission,
    add_submission_notification,
    add_task,
    add_xp,
    atomic_award_xp,
    ban_user,
    count_users,
    delete_task,
    get_leaderboard,
    get_stats,
    get_submission,
    get_task,
    get_tasks,
    get_tasks_filtered,
    get_user,
    get_user_rank,
    get_user_summary,
    get_user_language,
    set_user_language,
    update_user_username,
    get_setting,
    has_approved,
    has_pending,
    init_db,
    is_user_banned,
    list_users,
    list_all_users,
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
    get_departments,
    get_department,
    mark_verified,
    mark_unverified,
    get_users_needing_recheck,
    add_idea,
    get_unreviewed_ideas,
    mark_idea_status,
    delete_idea,
    get_user_departments,
    add_user_department,
    remove_user_department,
    get_user_role,
    set_user_global_role,
    get_user_global_role,
    set_user_dept_role,
    get_user_dept_role,
    get_user_all_dept_roles,
    get_users_in_department,
    get_dept_supervisors,
    get_pending_submissions,
    get_submission_notifications,
    get_approved_submissions,
    add_task_execution,
    update_task_execution_by_task,
    update_task,
    update_submission_comment,
    delete_submission_notifications,
    add_urgent_task,
    get_urgent_task,
    list_urgent_tasks_by_department,
    get_urgent_task_assignments,
    get_urgent_task_assignment,
    count_urgent_task_active_assignments,
    count_urgent_task_approved_assignments,
    add_urgent_task_assignment,
    get_urgent_assignment_by_id,
    update_urgent_assignment_submission,
    review_urgent_assignment,
    update_urgent_assignment_comment,
    update_urgent_task_status,
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


def _safe_text_preview(text: str | None, limit: int = 300) -> str:
    if not text:
        return ""
    text = text.replace("\n", " ").replace("\r", " ").strip()
    if len(text) <= limit:
        return text
    return text[:limit]


def _collect_user_context(user_id: int) -> dict:
    try:
        return {
            "user_id": user_id,
            "global_role": get_user_global_role(user_id) or "user",
            "departments": get_user_departments(user_id) or [],
            "language": get_user_language(user_id) or "uk",
        }
    except Exception:
        return {"user_id": user_id}


def _collect_message_action(update: Update) -> dict | None:
    msg = update.effective_message
    if not msg:
        return None

    text = msg.text or msg.caption or ""
    entities = msg.entities or []
    is_command = any(ent.type == "bot_command" and ent.offset == 0 for ent in entities)
    command = None
    if is_command and text:
        command = text.split()[0].split("@")[0]

    media_types = []
    if msg.photo:
        media_types.append("photo")
    if msg.document:
        media_types.append("document")
    if msg.video:
        media_types.append("video")
    if msg.audio:
        media_types.append("audio")
    if msg.voice:
        media_types.append("voice")
    if msg.video_note:
        media_types.append("video_note")
    if msg.sticker:
        media_types.append("sticker")

    return {
        "action_kind": "command" if is_command else "message",
        "command": command,
        "text_preview": _safe_text_preview(text),
        "has_media": bool(media_types),
        "media_types": media_types,
        "message_id": msg.message_id,
        "chat_id": msg.chat_id,
    }


def _collect_callback_action(update: Update) -> dict | None:
    query = update.callback_query
    if not query:
        return None

    msg = query.message
    return {
        "action_kind": "callback",
        "callback_data": query.data or "",
        "message_id": msg.message_id if msg else None,
        "chat_id": msg.chat_id if msg else None,
    }


async def log_user_message_update(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user:
        return

    action = _collect_message_action(update)
    if not action:
        return

    context = _collect_user_context(user.id)
    payload = {**context, **action}
    log_event("user_action", user_id=user.id, data=payload)


async def log_user_callback_update(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user:
        return

    action = _collect_callback_action(update)
    if not action:
        return

    context = _collect_user_context(user.id)
    payload = {**context, **action}
    log_event("user_action", user_id=user.id, data=payload)


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


async def _send_user_message(bot, update: Update | None, user_id: int, text: str, **kwargs):
    if update is not None:
        return await _reply(update, text, **kwargs)
    return await bot.send_message(chat_id=user_id, text=_normalize_text(text), **kwargs)


def _format_admin_submission_text(sub_id, user, task, proof_text):
    user_tag = f"@{user.username}" if user.username else user.first_name
    admin_text = (
        f"🔔 *Нова заявка #{sub_id}*\n\n"
        f"👤 Від: {user_tag} (ID: `{user.id}`)\n"
        f"📌 Завдання: *{task['title']}*\n"
        f"💎 XP: *{task['xp_reward']}*"
    )
    if proof_text:
        admin_text += f"\n💬 Текст:\n{proof_text[:300]}"
    return admin_text


async def _update_submission_notifications(ctx: ContextTypes.DEFAULT_TYPE, sub_id: int, updated_text: str):
    notifications = get_submission_notifications(sub_id)
    for note in notifications:
        try:
            if note["message_type"] == "photo":
                await ctx.bot.edit_message_caption(
                    chat_id=note["admin_id"],
                    message_id=note["message_id"],
                    caption=_normalize_text(updated_text),
                    parse_mode="Markdown",
                    reply_markup=None,
                )
            else:
                await ctx.bot.edit_message_text(
                    chat_id=note["admin_id"],
                    message_id=note["message_id"],
                    text=_normalize_text(updated_text),
                    parse_mode="Markdown",
                    reply_markup=None,
                )
        except Exception:
            pass
    delete_submission_notifications(sub_id)


async def _send_review_result(ctx: ContextTypes.DEFAULT_TYPE, pending: dict, comment_text: str | None):
    user_id = pending["user_id"]
    status = pending["status"]
    task_title = pending["task_title"]
    xp_reward = pending["xp_reward"]

    if status == "approved":
        user_msg = (
            f"🎉 *Завдання підтверджено!*\n\n"
            f"✅ «{task_title}» — зараховано!\n"
            f"💎 +{xp_reward} XP нараховано!\n\n"
            f"Переглянь профіль: /xp"
        )
    else:
        user_lang = get_user_language(user_id)
        user_msg = (
            f"❌ *Завдання не прийнято*\n\n"
            f"«{task_title}» — відхилено.\n"
            f"{get_message('error_submission_failed', user_lang)}"
        )

    if comment_text:
        user_msg += f"\n\n💬 Коментар: {comment_text}"

    try:
        await ctx.bot.send_message(user_id, _normalize_text(user_msg), parse_mode="Markdown")
    except Exception:
        pass


async def _process_media_group_job(context: ContextTypes.DEFAULT_TYPE):
    data = context.job.data if context.job else {}
    user_id = data.get("user_id")
    group_id = data.get("group_id")
    if not user_id or not group_id:
        return

    user_data = context.application.user_data.get(user_id)
    if not user_data:
        return

    media_groups = user_data.get("media_groups") or {}
    group = media_groups.pop(group_id, None)
    if not group:
        return

    user = group.get("user")
    if not user:
        return

    proof_text = group.get("text", "")
    proof_file_ids = group.get("file_ids", [])
    await _process_proof_payload(None, context, user, proof_text, proof_file_ids)


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
                translated_dept_name = get_dept_name_translated(idea_dict['department_id'], "uk")
                dept_name = f" ({dept['emoji']} {translated_dept_name})"
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
    text = get_message("error_rate_limit", "uk")

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
                get_message("tasks_no_dept", lang),
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
        dept_name = get_dept_name_translated(dept['id'], lang)
        btn_text = f"{check} {dept['emoji']} {dept_name}"
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
            dept_name = get_dept_name_translated(d['id'], lang)
            rows.append([_btn(f"{d['emoji']} {dept_name}", callback_data="noop"), _btn("❌", callback_data=f"dept_leave_{d['id']}")])
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
            await _query_answer(query, get_message("error_choice_failed", lang), show_alert=True)
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
            dept_name = get_dept_name_translated(dept['id'], lang)
            btn_text = f"{check} {dept['emoji']} {dept_name}"
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
            await _query_answer(query, get_message("dept_select_alert", lang), show_alert=True)
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
        await _query_answer(query, get_message("error_session_expired", lang), show_alert=True)
        return
    
    draft = ctx.user_data["idea_draft"]
    is_anonymous = query.data == "idea_anon"
    
    # Update user's username in case they changed it (without registering)
    update_user_username(user_id, query.from_user.username, query.from_user.first_name)
    
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
    return InlineKeyboardMarkup(
        [
            [_btn(get_message("admin_add_task_btn", lang), callback_data=f"a:add:{dept_id or 'g'}")],
            [_btn(get_message("admin_edit_task_btn", lang), callback_data="a:edit_dept")],
            [_btn(get_message("admin_delete_task_btn", lang), callback_data="a:del_dept")],
            [_btn("📋 Перегляд завдань", callback_data="a:review_tasks:0")],
            [_btn(get_message("admin_users_btn", lang), callback_data="a:users:0")],
            [_btn(get_message("admin_ideas_btn", lang), callback_data=f"a:ideas:0:{f'd{dept_id}' if dept_id else 'g'}")],
            [_btn(get_message("admin_push_btn", lang), callback_data="a:push")],
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
    # Pop twice: once to remove current screen, once to get the previous one
    pop_nav(ctx)  # Remove current screen from stack
    prev_screen = pop_nav(ctx)  # Get previous screen
    
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
                dept_name = get_dept_name_translated(dept['id'], lang)
                dept_label = get_message("leaderboard_department", lang, dept=f"{dept['emoji']} {dept_name}")
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

    if _get_supervised_departments(user.id):
        urgent_text = "🚨 /urgent — термінові завдання" if lang == "uk" else "🚨 /urgent — urgent tasks" if lang == "en" else "🚨 /urgent — urgente"
        text += f"\n{urgent_text}"
    
    await _reply(update, text, parse_mode="Markdown")


@admin_only
@rate_limit_user
async def cmd_admin(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Admin panel."""
    user = update.effective_user
    register_user(user)
    
    user_data = get_user(user.id)
    
    if user_data["is_banned"]:
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
    """Show task categories (Easy/Medium/Hard) for user to select.
    If user has multiple departments, show department selection first."""
    user = update.effective_user
    register_user(user)
    
    lang = get_user_language(user.id)
    user_depts = get_user_departments(user.id)
    if not user_depts:
        await _reply(update, get_message("dept_required", lang))
        return
    
    push_nav(ctx, "tasks")
    
    # If user has multiple departments, show department selection
    if len(user_depts) > 1:
        all_depts = get_departments()
        dept_buttons = []
        for dept in all_depts:
            if dept['id'] in user_depts:
                dept_name = get_dept_name_translated(dept['id'], lang)
                dept_buttons.append([_btn(f"{dept['emoji']} {dept_name}", callback_data=f"task_dept_select_{dept['id']}")])
        
        # Add back button
        dept_buttons.append([_btn(get_message("back_btn", lang), callback_data="go_back")])
        
        markup = InlineKeyboardMarkup(dept_buttons)
        await _reply(update,
            get_message("tasks_select_dept", lang),
            reply_markup=markup,
            parse_mode="Markdown")
        return
    
    # If user has only one department, skip to difficulty selection
    ctx.user_data["selected_task_dept"] = user_depts[0]
    
    # Show category menu
    markup = InlineKeyboardMarkup([
        [_btn(get_message("tasks_easy_btn", lang), callback_data="tasks_easy")],
        [_btn(get_message("tasks_medium_btn", lang), callback_data="tasks_medium")],
        [_btn(get_message("tasks_hard_btn", lang), callback_data="tasks_hard")],
        [_btn(get_message("tasks_urgent_btn", lang), callback_data="tasks_urgent")],
        [_btn(get_message("back_btn", lang), callback_data="go_back")],
    ])
    
    await _reply(update,
        get_message("tasks_select_difficulty", lang),
        reply_markup=markup,
        parse_mode="Markdown")


def _get_supervised_departments(user_id: int) -> list[int]:
    if user_id in ADMIN_IDS:
        return [d["id"] for d in get_departments()]
    roles = get_user_all_dept_roles(user_id)
    return sorted([dept_id for dept_id, role in roles.items() if role == "supervisor"])


@rate_limit_user
async def cmd_urgent(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    register_user(user)
    lang = get_user_language(user.id)

    supervised_depts = _get_supervised_departments(user.id)
    if not supervised_depts:
        await _reply(update, get_message("urgent_admin_only", lang))
        return

    ctx.user_data["urgent_depts"] = supervised_depts
    markup = InlineKeyboardMarkup([
        [_btn(get_message("urgent_admin_add_btn", lang), callback_data="u:add")],
        [_btn(get_message("urgent_admin_manage_btn", lang), callback_data="u:manage")],
        [_btn(get_message("back_btn", lang), callback_data="go_back")],
    ])

    await _reply(update, get_message("urgent_admin_header", lang), reply_markup=markup, parse_mode="Markdown")


async def handle_task_dept_select(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle department selection for tasks."""
    query = update.callback_query
    await _query_answer(query)
    
    user = query.from_user
    data = query.data
    
    # Extract department ID (format: "task_dept_select_{dept_id}")
    try:
        dept_id = int(data.split("_")[-1])
    except (ValueError, IndexError):
        return
    
    # Store selected department
    ctx.user_data["selected_task_dept"] = dept_id
    
    # Show difficulty selection
    lang = get_user_language(user.id)
    markup = InlineKeyboardMarkup([
        [_btn(get_message("tasks_easy_btn", lang), callback_data="tasks_easy")],
        [_btn(get_message("tasks_medium_btn", lang), callback_data="tasks_medium")],
        [_btn(get_message("tasks_hard_btn", lang), callback_data="tasks_hard")],
        [_btn(get_message("tasks_urgent_btn", lang), callback_data="tasks_urgent")],
        [_btn(get_message("back_btn", lang), callback_data="go_back")],
    ])
    
    await _edit_message_text(query,
        get_message("tasks_select_difficulty", lang),
        reply_markup=markup,
        parse_mode="Markdown")


async def handle_tasks_category(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle task category selection and initialize pagination."""
    query = update.callback_query
    await _query_answer(query)
    
    user = query.from_user
    data = query.data
    
    # Get user language preference
    lang = get_user_language(user.id)
    
    # Extract difficulty level
    difficulty_map = {
        "tasks_easy": "easy",
        "tasks_medium": "medium",
        "tasks_hard": "hard",
        "tasks_urgent": "urgent",
    }

    difficulty = difficulty_map.get(data)
    if not difficulty:
        return
    
    user_depts = get_user_departments(user.id)
    if not user_depts:
        await _query_answer(query, get_message("tasks_no_dept_alert", lang), show_alert=True)
        return
    
    # If user selected a specific department earlier, use it. Otherwise use primary.
    if "selected_task_dept" not in ctx.user_data:
        ctx.user_data["selected_task_dept"] = user_depts[0]
    
    # Reset pagination for this difficulty
    ctx.user_data[f"tasks_page_{difficulty}"] = 0

    if difficulty == "urgent":
        await display_urgent_tasks_page(update, ctx)
        return

    # Show paginated tasks
    await display_tasks_page(update, ctx, difficulty)


async def display_tasks_page(update: Update, ctx: ContextTypes.DEFAULT_TYPE, difficulty: str, edit_nav_only: bool = False):
    """Display paginated tasks. If edit_nav_only=True, only edit nav message (for pagination)."""
    TASKS_PER_PAGE = 3
    
    # Get user object from either update or callback_query
    if update.callback_query:
        user = update.callback_query.from_user
        query = update.callback_query
    else:
        user = update.effective_user
        query = None
    
    # Get user language preference
    lang = get_user_language(user.id)
    
    user_depts = get_user_departments(user.id)
    if not user_depts:
        if query:
            await _query_answer(query, "❌ Обери департамент", show_alert=True)
        return
    
    # Use selected department if available, otherwise use primary
    user_dept_id = ctx.user_data.get("selected_task_dept", user_depts[0])
    all_tasks = get_tasks_filtered(difficulty, user_dept_id)
    
    if not all_tasks:
        msg = get_message("tasks_none_for_difficulty", lang)
        markup = InlineKeyboardMarkup([
            [_btn("📗 Легкі", callback_data="tasks_easy")],
            [_btn("📙 Середні", callback_data="tasks_medium")],
            [_btn("📕 Важкі", callback_data="tasks_hard")],
        ])
        
        if query:
            await _edit_message_text(query, msg, reply_markup=markup, parse_mode="Markdown")
        else:
            await _reply(update, msg, reply_markup=markup, parse_mode="Markdown")
        return
    
    # Get current page
    current_page = ctx.user_data.get(f"tasks_page_{difficulty}", 0)
    total_pages = (len(all_tasks) + TASKS_PER_PAGE - 1) // TASKS_PER_PAGE
    
    # Validate page number
    if current_page >= total_pages:
        current_page = max(0, total_pages - 1)
        ctx.user_data[f"tasks_page_{difficulty}"] = current_page
    
    # If edit_nav_only=True, only update navigation message (for pagination)
    if edit_nav_only and query:
        if total_pages > 1:
            nav_buttons = []
            if current_page > 0:
                nav_buttons.append(_btn("◀ Попередня", callback_data=f"tasks_page_prev_{difficulty}"))
            if current_page < total_pages - 1:
                nav_buttons.append(_btn("Наступна ▶", callback_data=f"tasks_page_next_{difficulty}"))
            nav_buttons.append(_btn("Категорії", callback_data="go_back"))
            nav_text = f"⬇️ Навігація (сторінка {current_page + 1}/{total_pages}):"
            markup = InlineKeyboardMarkup([nav_buttons])
            await _edit_message_text(query, nav_text, reply_markup=markup)
        return
    
    # Get tasks for this page
    start_idx = current_page * TASKS_PER_PAGE
    end_idx = start_idx + TASKS_PER_PAGE
    page_tasks = all_tasks[start_idx:end_idx]
    
    # Build and send header
    cat_names_en = {"easy": "Easy", "medium": "Medium", "hard": "Hard"}
    cat_names_ro = {"easy": "Ușor", "medium": "Mediu", "hard": "Dificil"}
    cat_names_uk = {"easy": "Легкі", "medium": "Середні", "hard": "Важкі"}
    cat_names = {"en": cat_names_en, "ro": cat_names_ro, "uk": cat_names_uk}
    
    header = (
        f"📋 *{cat_names[lang][difficulty]} завдання*\n"
        f"Сторінка *{current_page + 1}* з *{total_pages}*\n"
        f"(Показано {len(page_tasks)} з {len(all_tasks)} завдань)"
    )
    await _reply(update, header, parse_mode="Markdown")
    
    # Display each task with button
    for task in page_tasks:
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
            btn = _btn(get_message("task_done_btn", lang), callback_data="noop")
        elif pending:
            btn = _btn(get_message("task_pending_btn", lang), callback_data="noop")
        else:
            btn = _btn(get_message("task_submit_btn", lang), callback_data=f"submit_{task['id']}")
        
        await _reply(update, text, 
                    reply_markup=InlineKeyboardMarkup([[btn]]),
                    parse_mode="Markdown")
    
    # Build and send navigation
    if total_pages > 1:
        nav_buttons = []
        
        if current_page > 0:
            nav_buttons.append(_btn(get_message("pagination_prev_btn", lang), callback_data=f"tasks_page_prev_{difficulty}"))
        
        if current_page < total_pages - 1:
            nav_buttons.append(_btn(get_message("pagination_next_btn", lang), callback_data=f"tasks_page_next_{difficulty}"))
        
        nav_buttons.append(_btn("Категорії", callback_data="go_back"))
        
        nav_text = f"⬇️ Навігація (сторінка {current_page + 1}/{total_pages}):"
        markup = InlineKeyboardMarkup([nav_buttons])
        await _reply(update, nav_text, reply_markup=markup)
    else:
        markup = InlineKeyboardMarkup([[_btn("Категорії", callback_data="go_back")]])
        await _reply(update, "⬇️", reply_markup=markup)


async def display_urgent_tasks_page(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Display urgent tasks for selected department."""
    if update.callback_query:
        user = update.callback_query.from_user
    else:
        user = update.effective_user

    lang = get_user_language(user.id)
    user_depts = get_user_departments(user.id)
    if not user_depts:
        await _reply(update, get_message("dept_required", lang))
        return

    user_dept_id = ctx.user_data.get("selected_task_dept", user_depts[0])
    urgent_tasks = list_urgent_tasks_by_department(user_dept_id)

    if not urgent_tasks:
        markup = InlineKeyboardMarkup([
            [_btn(get_message("tasks_easy_btn", lang), callback_data="tasks_easy")],
            [_btn(get_message("tasks_medium_btn", lang), callback_data="tasks_medium")],
            [_btn(get_message("tasks_hard_btn", lang), callback_data="tasks_hard")],
            [_btn(get_message("tasks_urgent_btn", lang), callback_data="tasks_urgent")],
            [_btn(get_message("back_btn", lang), callback_data="go_back")],
        ])
        await _reply(update, get_message("urgent_tasks_none", lang), reply_markup=markup, parse_mode="Markdown")
        return

    header = get_message("urgent_tasks_header", lang)
    await _reply(update, header, parse_mode="Markdown")

    for task in urgent_tasks:
        assignments = get_urgent_task_assignments(task["id"])
        active_assignments = [a for a in assignments if a.get("status") in ("reserved", "submitted", "approved")]
        active_count = len(active_assignments)
        remaining = max(task["required_slots"] - active_count, 0)

        assignee_names = [
            _display_name(a) for a in active_assignments if a.get("user_id")
        ]
        assignees_line = ", ".join(assignee_names) if assignee_names else "-"

        status_line = (
            get_message("urgent_task_in_progress", lang)
            if active_count >= task["required_slots"]
            else get_message("urgent_task_slots", lang, count=remaining)
        )

        deadline_line = ""
        if task.get("deadline_at"):
            deadline_line = f"\n⏰ {get_message('urgent_task_deadline', lang)}: {task['deadline_at']}"

        text = (
            f"🚨 *{task['title']}*\n"
            f"{task.get('description', '')}\n"
            f"💎 {task['xp_reward']} XP\n"
            f"👥 {get_message('urgent_task_assignees', lang)}: {assignees_line}\n"
            f"{status_line}"
            f"{deadline_line}"
        )

        assignment = get_urgent_task_assignment(task["id"], user.id)
        btn = None
        if assignment and assignment.get("status") in ("reserved", "submitted", "approved"):
            if assignment["status"] == "reserved":
                btn = _btn(get_message("urgent_task_submit_btn", lang), callback_data=f"urgent_submit_{task['id']}")
            elif assignment["status"] == "submitted":
                btn = _btn(get_message("urgent_task_submitted_btn", lang), callback_data="noop")
            else:
                btn = _btn(get_message("urgent_task_done_btn", lang), callback_data="noop")
        elif remaining > 0:
            btn = _btn(get_message("urgent_task_reserve_btn", lang), callback_data=f"urgent_reserve_{task['id']}")
        else:
            btn = _btn(get_message("urgent_task_in_progress_btn", lang), callback_data="noop")

        markup = InlineKeyboardMarkup([[btn]]) if btn else None
        await _reply(update, text, reply_markup=markup, parse_mode="Markdown")

    markup = InlineKeyboardMarkup([[_btn(get_message("back_btn", lang), callback_data="go_back")]])
    await _reply(update, "⬇️", reply_markup=markup)


async def handle_tasks_page_next(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle next page button for tasks - only update navigation message."""
    query = update.callback_query
    await _query_answer(query)
    
    # Extract difficulty from callback_data (e.g., "tasks_page_next_easy")
    difficulty = query.data.split("_")[-1]  # Gets 'easy', 'medium', or 'hard'
    
    # Increment page
    current_page = ctx.user_data.get(f"tasks_page_{difficulty}", 0)
    ctx.user_data[f"tasks_page_{difficulty}"] = current_page + 1
    
    # Only edit navigation message, don't send new task messages
    await display_tasks_page(update, ctx, difficulty, edit_nav_only=True)


async def handle_tasks_page_prev(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle previous page button for tasks - only update navigation message."""
    query = update.callback_query
    await _query_answer(query)
    
    # Extract difficulty from callback_data (e.g., "tasks_page_prev_easy")
    difficulty = query.data.split("_")[-1]
    
    # Decrement page
    current_page = ctx.user_data.get(f"tasks_page_{difficulty}", 0)
    ctx.user_data[f"tasks_page_{difficulty}"] = max(0, current_page - 1)
    
    # Only edit navigation message, don't send new task messages
    await display_tasks_page(update, ctx, difficulty, edit_nav_only=True)



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
    had_review = bool(ctx.user_data.pop("awaiting_review_comment", None))
    had_review = bool(ctx.user_data.pop("pending_review_result", None)) or had_review

    if had_submission or had_wizard or had_review:
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
    sent_count = await _notify_all_new_task(ctx.bot, title, description)
    log_event("task_push_sent", admin_id=user.id, data={
        "task_id": task_id,
        "department_id": None,
        "sent_count": sent_count,
    })
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

    lines = [get_message("admin_delete_tasks_header", "uk"), get_message("admin_delete_tasks_instruction", "uk"), ""]
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
    rows.append([_btn(get_message("admin_users_all_btn", "uk"), callback_data="a:users:0:all")])
    
    # Separator
    rows.append([_btn(get_message("admin_users_by_dept_label", "uk"), callback_data="noop")])
    
    # Department buttons
    for dept in departments:
        dept_name = get_dept_name_translated(dept['id'], "uk")
        rows.append([_btn(f"{dept['emoji']} {dept_name}", callback_data=f"a:users:0:d{dept['id']}")])
    
    rows.append([_btn(get_message("admin_menu_btn", "uk"), callback_data="a:menu")])
    
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
        "Обери департамент для редагування ролі:",
    ]
    
    rows = []
    if user_depts:
        for dept_id in user_depts:
            dept = get_department(dept_id)
            dept_role = get_user_dept_role(target_user_id, dept_id)
            role_emoji = {"supervisor": "📋", "coordinator": "⭐", "helper": "🌱", "member": "👤"}.get(dept_role, "👤")
            dept_name = get_dept_name_translated(dept_id, "uk")
            rows.append([_btn(f"{dept['emoji']} {dept_name} {role_emoji}", callback_data=f"a:ud:{target_user_id}:{page}:d{dept_id}")])
    else:
        lines.append(get_message("user_no_departments", "uk"))
    
    rows.append([_btn(get_message("back_btn", "uk"), callback_data=back_callback)])
    
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
        f"⭐ Актуальний XP: {user['xp']}",
        f"🏆 Загальний XP: {user['total_xp']}",
        f"💰 Доступний XP: {user['spendable_xp']}",
        f"Status: *{status}*",
        f"{global_role_emoji} Глобальна роль: *{global_role_text}*",
        "",
    ]
    
    # Show department roles
    dept_roles = get_user_all_dept_roles(target_user_id)
    if dept_roles:
        lines.append(get_message("user_dept_roles_header", "uk"))
        for d_id in sorted(dept_roles.keys()):
            d_role = dept_roles[d_id]
            dept = get_department(d_id)
            role_emoji = {"supervisor": "📋", "coordinator": "⭐", "helper": "🌱", "member": "👤"}.get(d_role, "❓")
            role_key = {"supervisor": "role_supervisor", "coordinator": "role_coordinator", "helper": "role_helper", "member": "role_member"}.get(d_role)
            role_text = get_message(role_key, "uk") if role_key else get_message("role_unknown", "uk")
            dept_name = get_dept_name_translated(d_id, "uk")
            lines.append(f"  {dept['emoji']} {dept_name}: {role_emoji} {role_text}")
    else:
        lines.append(get_message("user_no_dept_roles", "uk"))

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
        dept_name = get_dept_name_translated(dept_id, "uk")
        lines.append(f"\n*Роль у {dept['emoji']} {dept_name}:*")
        
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
                _btn("✏️ Ред.", callback_data=f"a:shop_edit:{p['id']}"),
                _btn(toggle_icon, callback_data=f"a:shop_toggle:{p['id']}"),
                _btn("🗑 Вид.", callback_data=f"a:shop_del:{p['id']}"),
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
    dept_name = f"{dept['emoji']} {get_dept_name_translated(dept_id, 'uk')}" if dept else "Невідомий відділ"
    
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
    dept_name = f"{dept['emoji']} {get_dept_name_translated(dept_id, 'uk')}" if dept else "Unknown Department"
    
    header = get_message("admin_delete_tasks_dept_header", "uk", dept_name=dept_name)
    lines = [header, get_message("admin_delete_tasks_instruction", "uk"), ""]
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


def _render_edit_delete_dept_menu(action: str) -> tuple[str, InlineKeyboardMarkup]:
    """
    Render department selection menu for edit/delete tasks.
    action: 'edit' or 'delete'
    """
    departments = get_departments()
    
    header = "🏢 *Вибір департаменту для редагування*" if action == "edit" else "🏢 *Вибір департаменту для видалення*"
    lines = [header, "", "Обери департамент або переглянь всі завдання:"]
    rows = []
    
    # Add button for all tasks
    callback = "a:edit_diff:0:" if action == "edit" else "a:del_diff:0:"
    rows.append([_btn("📋 Усі завдання", callback_data=callback)])
    
    # Add departments
    for dept in departments:
        try:
            emoji = dept["emoji"]
        except (KeyError, TypeError):
            emoji = "🏢"
        dept_id = dept["id"]
        dept_name = get_dept_name_translated(dept_id, "uk")
        dept_callback = f"a:edit_diff:0:d{dept_id}" if action == "edit" else f"a:del_diff:0:d{dept_id}"
        rows.append([_btn(f"{emoji} {dept_name}", callback_data=dept_callback)])
    
    rows.append([_btn("⬅ В меню", callback_data="a:menu")])
    
    return "\n".join(lines), InlineKeyboardMarkup(rows)


def _render_edit_delete_difficulty_menu(action: str, dept_filter: str | None) -> tuple[str, InlineKeyboardMarkup]:
    """
    Render difficulty selection menu for edit/delete tasks.
    action: 'edit' or 'delete'
    dept_filter: None for all depts, or 'd{dept_id}' for specific dept
    """
    header = "⚡ *Вибір складності для редагування*" if action == "edit" else "⚡ *Вибір складності для видалення*"
    lines = [header, "", "Обери рівень складності:"]
    rows = []
    
    difficulties = {
        "easy": ("Легкі завдання", "easy"),
        "medium": ("Середні завдання", "medium"),
        "hard": ("Важкі завдання", "hard"),
    }
    
    # Main difficulty buttons
    for diff_key, (diff_label, diff_value) in difficulties.items():
        dept_part = f":{dept_filter}" if dept_filter else ":"
        callback = f"a:edit_list:0{dept_part}:{diff_value}" if action == "edit" else f"a:dellist:0{dept_part}:{diff_value}"
        rows.append([_btn(f"{diff_label}", callback_data=callback)])
    
    # All difficulties button
    all_callback = f"a:edit_list:0{':' + dept_filter if dept_filter else ':'}" if action == "edit" else f"a:dellist:0{':' + dept_filter if dept_filter else ':'}"
    rows.append([_btn("📚 Усі завдання", callback_data=all_callback)])
    
    # Back button
    back_callback = "a:edit_dept" if action == "edit" else "a:del_dept"
    rows.append([_btn("⬅ Назад", callback_data=back_callback)])
    
    return "\n".join(lines), InlineKeyboardMarkup(rows)


def _render_filtered_task_page(
    page: int, 
    dept_filter: str | None = None, 
    difficulty: str | None = None,
    action: str = "delete"
) -> tuple[str, InlineKeyboardMarkup]:
    """
    Render task page filtered by department and/or difficulty.
    dept_filter: None for all depts, or 'd{dept_id}' for specific dept
    difficulty: 'easy', 'medium', 'hard', or None for all
    action: 'delete' or 'edit'
    """
    # Get all tasks
    all_tasks = get_tasks()
    
    # Filter by department
    if dept_filter and dept_filter.startswith("d"):
        dept_id = int(dept_filter[1:])
        filtered_tasks = [t for t in all_tasks if t["department_id"] == dept_id]
        dept = get_department(dept_id)
        dept_name = f"{dept['emoji']} {get_dept_name_translated(dept['id'], 'uk')}" if dept else "Unknown"
    else:
        filtered_tasks = all_tasks
        dept_name = "Усі департаменти"
    
    # Filter by difficulty
    if difficulty and difficulty in ("easy", "medium", "hard"):
        filtered_tasks = [t for t in filtered_tasks if t["difficulty_level"] == difficulty]
        diff_label = {"easy": "Легкі", "medium": "Середні", "hard": "Важкі"}.get(difficulty, "Невідомі")
    else:
        diff_label = "Усіх рівнів"
    
    # Pagination
    total_pages = max(1, (len(filtered_tasks) + ADMIN_TASKS_PAGE_SIZE - 1) // ADMIN_TASKS_PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    start = page * ADMIN_TASKS_PAGE_SIZE
    chunk = filtered_tasks[start : start + ADMIN_TASKS_PAGE_SIZE]
    
    # Build header
    action_label = "редагування" if action == "edit" else "видалення"
    header = f"📋 *Завдання для {action_label}*\n{dept_name} — {diff_label}"
    lines = [header, f"Сторінка {page + 1} з {total_pages}", ""]
    rows = []
    
    if not chunk:
        lines.append("Немає завдань за цими критеріями.")
    else:
        for task in chunk:
            lines.append(f"#{task['id']} — {task['title']} ({task['xp_reward']} XP)")
            
            # Build callback with proper format: action:id:page:dept_filter:difficulty
            if action == "edit":
                callback_data = f"a:edit:{task['id']}:{page}:{dept_filter or ''}:{difficulty or ''}"
            else:
                callback_data = f"a:del:{task['id']}:{page}:{dept_filter or ''}:{difficulty or ''}"
            
            action_label_short = "Редагувати" if action == "edit" else "Видалити"
            rows.append([_btn(f"{action_label_short} #{task['id']}", callback_data=callback_data)])
    
    # Navigation
    nav = []
    if page > 0:
        if action == "edit":
            nav_callback = f"a:edit_list:{page - 1}:{dept_filter or ''}:{difficulty or ''}"
        else:
            nav_callback = f"a:dellist:{page - 1}:{dept_filter or ''}:{difficulty or ''}"
        nav.append(_btn("◀ Prev", callback_data=nav_callback))
    if page < total_pages - 1:
        if action == "edit":
            nav_callback = f"a:edit_list:{page + 1}:{dept_filter or ''}:{difficulty or ''}"
        else:
            nav_callback = f"a:dellist:{page + 1}:{dept_filter or ''}:{difficulty or ''}"
        nav.append(_btn("Next ▶", callback_data=nav_callback))
    
    if nav:
        rows.append(nav)
    
    # Back button
    back_callback = f"a:edit_diff:0:{dept_filter or ''}" if action == "edit" else f"a:del_diff:0:{dept_filter or ''}"
    rows.append([_btn("⬅ Назад", callback_data=back_callback)])
    
    return "\n".join(lines), InlineKeyboardMarkup(rows)


def _render_ideas_page(page: int, user_id: int, role: str) -> tuple[str, InlineKeyboardMarkup]:
    """Render paginated list of ideas for admin review."""
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
                _btn("✅ Розглянуто", callback_data=f"a:idea_mark:{idea['id']}:{page}"),
                _btn("🗑 Видалити", callback_data=f"a:idea_del:{idea['id']}:{page}"),
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

def _render_urgent_manage_menu(dept_id: int) -> tuple[str, InlineKeyboardMarkup]:
    tasks = list_urgent_tasks_by_department(dept_id)
    dept = get_department(dept_id)
    dept_name = f"{dept['emoji']} {get_dept_name_translated(dept_id, 'uk')}" if dept else "Невідомий департамент"

    lines = [f"🚨 *Термінові завдання* — {dept_name}", ""]
    rows = []

    if not tasks:
        lines.append("Немає термінових завдань.")
    else:
        for task in tasks:
            lines.append(f"#{task['id']} — {task['title']} ({task['required_slots']} ос.)")
            rows.append([
                _btn("👥 Призначити", callback_data=f"u:assign:{task['id']}") ,
                _btn("🔁 Змінити", callback_data=f"u:replace:{task['id']}") ,
            ])

    rows.append([_btn("⬅ Назад", callback_data="u:back")])
    return "\n".join(lines), InlineKeyboardMarkup(rows)


async def _start_urgent_task_wizard(update: Update, ctx: ContextTypes.DEFAULT_TYPE, dept_id: int):
    chat_id = update.effective_chat.id
    ctx.user_data["admin_wizard"] = {
        "type": "urgent_task",
        "step": "title",
        "payload": {"department": dept_id},
        "bot_prompt_ids": [],
    }
    await _wizard_prompt(ctx, chat_id, "🚨 Введи *назву* термінового завдання:")

async def _start_edit_task_wizard(update: Update, ctx: ContextTypes.DEFAULT_TYPE, task_id: int, field: str, page: int, dept_filter: str | None, difficulty: str | None):
    """Start wizard for editing a specific task field."""
    chat_id = update.effective_chat.id
    
    task = get_task(task_id)
    if not task:
        await _reply(update, "❌ Завдання не знайдено")
        return
    
    ctx.user_data["edit_task_wizard"] = {
        "type": "edit_task",
        "field": field,
        "task_id": task_id,
        "page": page,
        "dept_filter": dept_filter,
        "difficulty": difficulty,
        "step": field,
        "bot_prompt_ids": [],
    }
    
    if field == "title":
        await _wizard_prompt(ctx, chat_id, f"✏️ Введи нову *назву*:\n\n_Поточна: {task['title']}_")
    elif field == "description":
        await _wizard_prompt(ctx, chat_id, f"✏️ Введи новий *опис*:\n\n_Поточний: {task['description']}_")
    elif field == "xp":
        await _wizard_prompt(ctx, chat_id, f"✏️ Введи новий *XP* (число > 0):\n\n_Поточний: {task['xp_reward']}_")
    elif field == "department":
        # Show buttons for department selection
        await _cleanup_wizard_prompts(ctx, chat_id)
        all_depts = get_departments()
        buttons = []
        for dept in all_depts:
            try:
                emoji = dept['emoji']
            except (KeyError, TypeError):
                emoji = "🏢"
            dept_name = get_dept_name_translated(dept['id'], "uk")
            buttons.append([_btn(f"{emoji} {dept_name}", callback_data=f"wizard_edit_department_{dept['id']}_{task_id}_{page}_{dept_filter or ''}_{difficulty or ''}")])
        buttons.append([_btn("⬅ Назад", callback_data=f"a:edit:{task_id}:{page}:{dept_filter or ''}:{difficulty or ''}")])
        
        markup = InlineKeyboardMarkup(buttons)
        msg = await ctx.bot.send_message(chat_id, "🏢 *Вибери новий департамент:*", reply_markup=markup, parse_mode="Markdown")
        ctx.user_data["edit_task_wizard"]["bot_prompt_ids"].append(msg.message_id)
    elif field == "difficulty":
        # Show buttons for difficulty
        await _cleanup_wizard_prompts(ctx, chat_id)
        markup = InlineKeyboardMarkup([
            [_btn("📗 Легкі", callback_data=f"wizard_edit_difficulty_easy_{task_id}_{page}_{dept_filter or ''}_{difficulty or ''}")],
            [_btn("📙 Середні", callback_data=f"wizard_edit_difficulty_medium_{task_id}_{page}_{dept_filter or ''}_{difficulty or ''}")],
            [_btn("📕 Важкі", callback_data=f"wizard_edit_difficulty_hard_{task_id}_{page}_{dept_filter or ''}_{difficulty or ''}")],
            [_btn("⬅ Назад", callback_data=f"a:edit:{task_id}:{page}:{dept_filter or ''}:{difficulty or ''}")],
        ])
        msg = await ctx.bot.send_message(chat_id, "⚡ *Вибери нову складність:*", reply_markup=markup, parse_mode="Markdown")
        ctx.user_data["edit_task_wizard"]["bot_prompt_ids"].append(msg.message_id)


async def _start_admin_wizard(update: Update, ctx: ContextTypes.DEFAULT_TYPE, wizard_type: str):
    chat_id = update.effective_chat.id
    lang = get_user_language(update.effective_user.id)
    if wizard_type.startswith("add_task"):
        ctx.user_data["admin_wizard"] = {
            "type": "add_task",
            "step": "department",
            "payload": {},
            "bot_prompt_ids": [],
        }
        # Show all departments (admin can add task to any department)
        all_depts = get_departments()
        
        if not all_depts:
            await _reply(update, "❌ Нема департаментів")
            return
        
        dept_buttons = []
        for dept in all_depts:
            dept_name = get_dept_name_translated(dept['id'], "uk")
            dept_buttons.append([_btn(f"{dept['emoji']} {dept_name}", callback_data=f"wizard_department_{dept['id']}")])
        
        markup = InlineKeyboardMarkup(dept_buttons)
        msg = await ctx.bot.send_message(chat_id, "🏢 *Крок 1: Вибери департамент:*", reply_markup=markup, parse_mode="Markdown")
        ctx.user_data["admin_wizard"]["bot_prompt_ids"].append(msg.message_id)
        return

    if wizard_type.startswith("give_xp"):
        ctx.user_data["admin_wizard"] = {
            "type": "give_xp",
            "step": "user_id",
            "payload": {},
            "bot_prompt_ids": [],
        }
        await _wizard_prompt(ctx, chat_id, "🎯 Введи *user_id* користувача:")
        return

    if wizard_type.startswith("add_product"):
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
        return

    if wizard_type == "push_broadcast":
        ctx.user_data["admin_wizard"] = {
            "type": "push_broadcast",
            "step": "target",
            "payload": {},
            "bot_prompt_ids": [],
        }

        departments = get_departments()
        rows = [
            [_btn(get_message("admin_push_target_all_btn", lang), callback_data="wizard_push_all")],
            [_btn(get_message("admin_push_target_user_btn", lang), callback_data="wizard_push_user")],
        ]

        for dept in departments:
            dept_name = get_dept_name_translated(dept["id"], lang)
            rows.append([_btn(f"{dept['emoji']} {dept_name}", callback_data=f"wizard_push_dept_{dept['id']}")])

        msg = await ctx.bot.send_message(
            chat_id=chat_id,
            text=_normalize_text(get_message("admin_push_select_target", lang)),
            reply_markup=InlineKeyboardMarkup(rows),
            parse_mode="Markdown",
        )
        ctx.user_data["admin_wizard"]["bot_prompt_ids"].append(msg.message_id)
        return


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

    if data == "a:push":
        await _start_admin_wizard(update, ctx, "push_broadcast")
        await _query_answer(query, "Пуш-розсилка")
        return

    if data.startswith("a:review_tasks:"):
        parts = data.split(":")
        page = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
        
        # Show filter menu for task review
        text = "📋 *Перегляд завдань*\n\nВибери які завдання переглянути:"
        buttons = [
            [_btn("⏳ Неперевірені завдання", callback_data="a:review_submissions:pending:0")],
            [_btn("✅ Перевірені завдання", callback_data="a:review_submissions:approved:0")],
            [_btn("⬅ Назад", callback_data="a:menu")],
        ]
        await _edit_message_text(query, text=text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")
        return

    if data.startswith("a:review_submissions:"):
        parts = data.split(":")
        status = parts[2] if len(parts) > 2 else "pending"
        page = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 0
        
        # Get submissions by status
        if status == "pending":
            subs = get_pending_submissions()
            title = "⏳ *Неперевірені завдання*"
        elif status == "approved":
            subs = get_approved_submissions()
            title = "✅ *Перевірені завдання*"
        else:
            subs = []
            title = "📋 *Завдання*"
        
        if not subs:
            await _edit_message_text(query, 
                f"{title}\n\n✅ Нема завдань.",
                reply_markup=InlineKeyboardMarkup([
                    [_btn("⬅ Назад", callback_data="a:review_tasks:0")]
                ]),
                parse_mode="Markdown")
            return
        
        # Paginate: 5 per page
        per_page = 5
        total_pages = (len(subs) + per_page - 1) // per_page
        page = max(0, min(page, total_pages - 1))
        
        start_idx = page * per_page
        end_idx = start_idx + per_page
        page_subs = subs[start_idx:end_idx]
        
        text = f"{title} [{page+1}/{total_pages}]\n\n"
        
        buttons = []
        for sub in page_subs:
            user_display = f"@{sub['username']}" if sub['username'] else (sub['first_name'] or f"User{sub['user_id']}")
            text += f"👤 {user_display} (ID: {sub['user_id']})\n"
            text += f"📌 Завдання: {sub['title']}\n"
            text += f"📅 {sub['submitted_at'][:10]}\n"
            
            # For pending, show approve/reject buttons; for approved, show timestamp
            if status == "pending":
                text += "─" * 30 + "\n"
                buttons.append([
                    _btn("✅", callback_data=f"approve_{sub['id']}"),
                    _btn("❌", callback_data=f"reject_{sub['id']}")
                ])
            else:
                reviewer_name = f" (@{sub['reviewer_username']})" if sub['reviewer_username'] else ""
                text += f"✅ Підтверджено{reviewer_name}\n"
                text += "─" * 30 + "\n"
        
        # Pagination buttons
        nav_buttons = []
        if page > 0:
            nav_buttons.append(_btn("◀ Prev", callback_data=f"a:review_submissions:{status}:{page - 1}"))
        if page < total_pages - 1:
            nav_buttons.append(_btn("Next ▶", callback_data=f"a:review_submissions:{status}:{page + 1}"))
        
        if nav_buttons:
            buttons.append(nav_buttons)
        
        buttons.append([_btn("⬅ Назад", callback_data="a:review_tasks:0")])
        
        await _edit_message_text(query, text=text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")
        return

    if data.startswith("a:pending:"):
        # Legacy redirect to new review_submissions handler
        parts = data.split(":")
        page = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
        query.data = f"a:review_submissions:pending:{page}"
        await _handle_admin_callback(update, ctx)
        return

    if data.startswith("a:add:"):
        dept_filter = data.split(":", 2)[2]
        dept_id = int(dept_filter[1:]) if dept_filter.startswith("d") else None
        await _start_admin_wizard(update, ctx, f"add_task:{dept_id or ''}")
        await _query_answer(query, "Майстер додавання запущено")
        return

    if data == "a:edit_dept":
        text, markup = _render_edit_delete_dept_menu("edit")
        await _edit_message_text(query, text=text, reply_markup=markup, parse_mode="Markdown")
        return

    if data == "a:del_dept":
        text, markup = _render_edit_delete_dept_menu("delete")
        await _edit_message_text(query, text=text, reply_markup=markup, parse_mode="Markdown")
        return

    if data.startswith("a:edit_diff:"):
        parts = data.split(":")
        page = int(parts[2]) if len(parts) > 2 else 0
        dept_filter = parts[3] if len(parts) > 3 else None
        text, markup = _render_edit_delete_difficulty_menu("edit", dept_filter)
        await _edit_message_text(query, text=text, reply_markup=markup, parse_mode="Markdown")
        return

    if data.startswith("a:del_diff:"):
        parts = data.split(":")
        page = int(parts[2]) if len(parts) > 2 else 0
        dept_filter = parts[3] if len(parts) > 3 else None
        text, markup = _render_edit_delete_difficulty_menu("delete", dept_filter)
        await _edit_message_text(query, text=text, reply_markup=markup, parse_mode="Markdown")
        return

    if data.startswith("a:edit_list:"):
        parts = data.split(":")
        page = int(parts[2]) if len(parts) > 2 else 0
        dept_filter = parts[3] if len(parts) > 3 and parts[3] else None
        difficulty = parts[4] if len(parts) > 4 and parts[4] else None
        text, markup = _render_filtered_task_page(page, dept_filter, difficulty, action="edit")
        await _edit_message_text(query, text=text, reply_markup=markup, parse_mode="Markdown")
        return

    if data.startswith("a:dellist:"):
        parts = data.split(":")
        page = int(parts[2]) if len(parts) > 2 else 0
        dept_filter = parts[3] if len(parts) > 3 and parts[3] else None
        difficulty = parts[4] if len(parts) > 4 and parts[4] else None
        text, markup = _render_filtered_task_page(page, dept_filter, difficulty, action="delete")
        await _edit_message_text(query, text=text, reply_markup=markup, parse_mode="Markdown")
        return

    if data.startswith("a:edit:"):
        parts = data.split(":")
        task_id = int(parts[2])
        page = int(parts[3]) if len(parts) > 3 else 0
        dept_filter = parts[4] if len(parts) > 4 else None
        difficulty = parts[5] if len(parts) > 5 else None
        
        task = get_task(task_id)
        if not task:
            await _query_answer(query, "Завдання не знайдено", show_alert=True)
            return
        
        # Get department name
        dept = get_department(task['department_id'])
        if dept:
            dept_name = get_dept_name_translated(task['department_id'], "uk")
        else:
            dept_name = "N/A"
        
        # Show edit menu
        text = (
            f"📝 *Завдання #{task_id}: {task['title']}*\n\n"
            f"🏢 Департамент: {dept_name}\n"
            f"💎 XP: {task['xp_reward']}\n"
            f"⚡ Складність: {task['difficulty_level']}\n"
            f"📄 Опис: {task['description'][:100]}{'...' if len(task['description']) > 100 else ''}\n\n"
            f"Що редагувати?"
        )
        buttons = [
            [_btn("🏢 Департамент", callback_data=f"a:edit_field:{task_id}:department:{page}:{dept_filter or ''}:{difficulty or ''}")],
            [_btn("📝 Назву", callback_data=f"a:edit_field:{task_id}:title:{page}:{dept_filter or ''}:{difficulty or ''}")],
            [_btn("📄 Опис", callback_data=f"a:edit_field:{task_id}:description:{page}:{dept_filter or ''}:{difficulty or ''}")],
            [_btn("💎 XP", callback_data=f"a:edit_field:{task_id}:xp:{page}:{dept_filter or ''}:{difficulty or ''}")],
            [_btn("⚡ Складність", callback_data=f"a:edit_field:{task_id}:difficulty:{page}:{dept_filter or ''}:{difficulty or ''}")],
            [_btn("⬅ Назад", callback_data=f"a:edit_list:{page}:{dept_filter or ''}:{difficulty or ''}")],
        ]
        await _edit_message_text(query, text=text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")
        return

    if data.startswith("a:edit_field:"):
        parts = data.split(":")
        task_id = int(parts[2])
        field = parts[3]  # title, description, xp, difficulty
        page = int(parts[4]) if len(parts) > 4 else 0
        dept_filter = parts[5] if len(parts) > 5 else None
        difficulty = parts[6] if len(parts) > 6 else None
        
        # Start edit wizard
        await _start_edit_task_wizard(update, ctx, task_id, field, page, dept_filter, difficulty)
        return

    if data.startswith("a:del:"):
        parts = data.split(":")
        task_id = int(parts[2])
        page = int(parts[3]) if len(parts) > 3 else 0
        dept_filter = parts[4] if len(parts) > 4 else None
        difficulty = parts[5] if len(parts) > 5 else None
        
        delete_task(task_id)
        
        # Render the task list again with same filters
        text, markup = _render_filtered_task_page(page, dept_filter, difficulty, action="delete")
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
        dept_name = get_dept_name_translated(dept_id, "uk")
        await _edit_message_text(query, text=f"✅ {role_emoji} Роль змінена на: *{role_display}* у {dept['emoji']} {dept_name}\n\n{text}", 
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
            dept_name = get_dept_name_translated(task["department_id"], 'uk')
            dept_label = f" ({dept['emoji']} {dept_name})"
        
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


async def handle_wizard_callbacks(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle wizard step callbacks (difficulty, department selection, etc)."""
    query = update.callback_query
    await _query_answer(query)
    data = query.data
    
    wizard = _wizard(ctx)
    if not wizard:
        return
    
    chat_id = update.effective_chat.id
    
    # Handle difficulty selection in add_task wizard
    if data.startswith("wizard_difficulty_"):
        if wizard["type"] != "add_task" or wizard["step"] != "difficulty":
            return
        
        difficulty = data.split("_")[-1]  # easy, medium, hard
        wizard["payload"]["difficulty"] = difficulty
        
        # Next: ask for title
        wizard["step"] = "title"
        await _cleanup_wizard_prompts(ctx, chat_id)
        await _wizard_prompt(ctx, chat_id, "📝 *Крок 3: Введи назву* завдання:")
        return
    
    # Handle department selection in add_task wizard
    if data.startswith("wizard_department_"):
        if wizard["type"] != "add_task" or wizard["step"] != "department":
            return
        
        try:
            dept_id = int(data.split("_")[-1])
        except (ValueError, IndexError):
            return
        
        wizard["payload"]["department"] = dept_id
        wizard["step"] = "difficulty"
        
        # Show difficulty selection
        await _cleanup_wizard_prompts(ctx, chat_id)
        markup = InlineKeyboardMarkup([
            [_btn("📗 Легкі", callback_data="wizard_difficulty_easy")],
            [_btn("📙 Середні", callback_data="wizard_difficulty_medium")],
            [_btn("📕 Важкі", callback_data="wizard_difficulty_hard")],
        ])
        msg = await ctx.bot.send_message(chat_id, "⚡ *Крок 2: Вибери складність:*", reply_markup=markup, parse_mode="Markdown")
        wizard["bot_prompt_ids"].append(msg.message_id)
        return

    # Handle target selection in push broadcast wizard
    if data.startswith("wizard_push_"):
        if wizard["type"] != "push_broadcast" or wizard["step"] != "target":
            return

        lang = get_user_language(query.from_user.id)

        if data == "wizard_push_all":
            wizard["payload"]["target"] = "all"
            wizard["step"] = "message"
            await _cleanup_wizard_prompts(ctx, chat_id)
            await _wizard_prompt(ctx, chat_id, get_message("admin_push_prompt_text", lang))
            return

        if data == "wizard_push_user":
            wizard["payload"]["target"] = "user"
            wizard["step"] = "user_id"
            await _cleanup_wizard_prompts(ctx, chat_id)
            await _wizard_prompt(ctx, chat_id, get_message("admin_push_prompt_user_id", lang))
            return

        if data.startswith("wizard_push_dept_"):
            try:
                dept_id = int(data.split("_")[-1])
            except (ValueError, IndexError):
                return

            wizard["payload"]["target"] = "dept"
            wizard["payload"]["dept_id"] = dept_id
            wizard["step"] = "message"
            await _cleanup_wizard_prompts(ctx, chat_id)
            await _wizard_prompt(ctx, chat_id, get_message("admin_push_prompt_text", lang))
            return
    
    # Handle difficulty selection for edit_task
    if data.startswith("wizard_edit_difficulty_"):
        parts = data.split("_")
        difficulty = parts[4]  # easy, medium, hard
        task_id = int(parts[5])
        _page = int(parts[6]) if len(parts) > 6 else 0
        _dept_filter = parts[7] if len(parts) > 7 else None
        _difficulty_filter = parts[8] if len(parts) > 8 else None
        
        update_task(task_id, difficulty_level=difficulty)
        
        await _cleanup_wizard_prompts(ctx, chat_id)
        _clear_wizard(ctx)

        await ctx.bot.send_message(
            chat_id=query.from_user.id,
            text=f"✅ Складність завдання #{task_id} оновлена на {difficulty}!",
            parse_mode="Markdown"
        )
        return

    if data.startswith("wizard_edit_department_"):
        parts = data.split("_")
        new_dept_id = int(parts[4])
        task_id = int(parts[5])
        _page = int(parts[6]) if len(parts) > 6 else 0
        _dept_filter = parts[7] if len(parts) > 7 else None
        _difficulty = parts[8] if len(parts) > 8 else None
        
        update_task(task_id, department_id=new_dept_id)
        
        await _cleanup_wizard_prompts(ctx, chat_id)
        _clear_wizard(ctx)
        
        # Get new department name
        dept = get_department(new_dept_id)
        if dept:
            dept_name = get_dept_name_translated(new_dept_id, "uk")
        else:
            dept_name = "N/A"
        
        await ctx.bot.send_message(
            chat_id=query.from_user.id,
            text=f"✅ Завдання #{task_id} переведено до департаменту \"{dept_name}\"!",
            parse_mode="Markdown"
        )
        return
    
    # Handle difficulty selection for edit_task
    if data.startswith("wizard_edit_difficulty_"):
        parts = data.split("_")
        difficulty = parts[4]  # easy, medium, hard
        task_id = int(parts[5])
        _page = int(parts[6]) if len(parts) > 6 else 0
        _dept_filter = parts[7] if len(parts) > 7 else None
        _difficulty_filter = parts[8] if len(parts) > 8 else None
        
        update_task(task_id, difficulty_level=difficulty)
        
        await _cleanup_wizard_prompts(ctx, chat_id)
        _clear_wizard(ctx)
        
        await ctx.bot.send_message(
            chat_id=query.from_user.id,
            text=f"✅ Складність завдання #{task_id} оновлена на {difficulty}!",
            parse_mode="Markdown"
        )
        return

    if data.startswith("wizard_edit_department_"):
        parts = data.split("_")
        new_dept_id = int(parts[4])
        task_id = int(parts[5])
        _page = int(parts[6]) if len(parts) > 6 else 0
        _dept_filter = parts[7] if len(parts) > 7 else None
        _difficulty = parts[8] if len(parts) > 8 else None
        
        update_task(task_id, department_id=new_dept_id)
        
        await _cleanup_wizard_prompts(ctx, chat_id)
        _clear_wizard(ctx)
        
        # Get new department name
        dept = get_department(new_dept_id)
        if dept:
            dept_name = get_dept_name_translated(new_dept_id, "uk")
        else:
            dept_name = "N/A"
        
        await ctx.bot.send_message(
            chat_id=query.from_user.id,
            text=f"✅ Завдання #{task_id} переведено до департаменту \"{dept_name}\"!",
            parse_mode="Markdown"
        )
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
            dept_name = get_dept_name_translated(dept['id'], 'uk') if dept else "Unknown"
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
            dept_name = get_dept_name_translated(dept['id'], lang)
            btn_text = f"{check} {dept['emoji']} {dept_name}"
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

    if data.startswith("u:"):
        user_id = query.from_user.id
        lang = get_user_language(user_id)
        supervised_depts = ctx.user_data.get("urgent_depts") or _get_supervised_departments(user_id)

        if data in ("u:add", "u:manage"):
            if not supervised_depts:
                await _query_answer(query, get_message("urgent_admin_only", lang), show_alert=True)
                return

            if len(supervised_depts) == 1:
                dept_id = supervised_depts[0]
                if data == "u:add":
                    await _start_urgent_task_wizard(update, ctx, dept_id)
                else:
                    text, markup = _render_urgent_manage_menu(dept_id)
                    await _edit_message_text(query, text=text, reply_markup=markup, parse_mode="Markdown")
                return

            # Show department selection
            rows = []
            for dept in get_departments():
                if dept["id"] in supervised_depts:
                    dept_name = get_dept_name_translated(dept["id"], lang)
                    rows.append([_btn(f"{dept['emoji']} {dept_name}", callback_data=f"u:dept:{data}:{dept['id']}")])
            rows.append([_btn(get_message("back_btn", lang), callback_data="u:back")])
            await _edit_message_text(
                query,
                get_message("urgent_admin_select_dept", lang),
                reply_markup=InlineKeyboardMarkup(rows),
                parse_mode="Markdown",
            )
            return

        if data == "u:back":
            await cmd_urgent(update, ctx)
            return

        if data.startswith("u:dept:"):
            parts = data.split(":")
            action = parts[2]
            dept_id = int(parts[3])
            if action == "u:add":
                await _start_urgent_task_wizard(update, ctx, dept_id)
                return
            if action == "u:manage":
                text, markup = _render_urgent_manage_menu(dept_id)
                await _edit_message_text(query, text=text, reply_markup=markup, parse_mode="Markdown")
                return

        if data.startswith("u:assign:"):
            task_id = int(data.split(":")[2])
            ctx.user_data["admin_wizard"] = {
                "type": "urgent_assign",
                "step": "user_id",
                "payload": {"task_id": task_id},
                "bot_prompt_ids": [],
            }
            await _query_answer(query)
            await _wizard_prompt(ctx, query.from_user.id, "👤 Введи user_id(и) через кому для призначення:")
            return

        if data.startswith("u:replace:"):
            task_id = int(data.split(":")[2])
            ctx.user_data["admin_wizard"] = {
                "type": "urgent_replace",
                "step": "replace",
                "payload": {"task_id": task_id},
                "bot_prompt_ids": [],
            }
            await _query_answer(query)
            await _wizard_prompt(ctx, query.from_user.id, "🔁 Введи старий user_id і новий user_id через пробіл:")
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
            dept_name = get_dept_name_translated(dept['id'], lang)
            btn_text = f"{check} {dept['emoji']} {dept_name}"
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
        
        # Log task execution when user starts submission
        add_task_execution(user.id, task_id, status="started")
        
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

    if data.startswith("urgent_reserve_"):
        task_id = int(data.split("_", 2)[2])
        user = query.from_user
        register_user(user)

        urgent_task = get_urgent_task(task_id)
        if not urgent_task or not urgent_task.get("is_active"):
            await _query_answer(query, "❌ Завдання не знайдено", show_alert=True)
            return

        user_depts = get_user_departments(user.id)
        if urgent_task["department_id"] not in user_depts:
            await _query_answer(query, "❌ Це завдання не з твого департаменту", show_alert=True)
            return

        existing = get_urgent_task_assignment(task_id, user.id)
        if existing and existing.get("status") in ("reserved", "submitted", "approved"):
            await _query_answer(query, "⚠️ Ти вже забронював це завдання", show_alert=True)
            return

        active_count = count_urgent_task_active_assignments(task_id)
        if active_count >= urgent_task["required_slots"]:
            await _query_answer(query, "⏳ Всі місця вже зайняті", show_alert=True)
            return

        add_urgent_task_assignment(task_id, user.id, assigned_by=None)
        active_count = count_urgent_task_active_assignments(task_id)
        if active_count >= urgent_task["required_slots"]:
            update_urgent_task_status(task_id, "in_progress")
        log_event("urgent_task_reserved", user_id=user.id, data={
            "urgent_task_id": task_id,
            "department_id": urgent_task["department_id"],
        })

        await _query_answer(query, "✅ Завдання заброньовано!", show_alert=True)
        await display_urgent_tasks_page(update, ctx)
        return

    if data.startswith("urgent_submit_"):
        task_id = int(data.split("_", 2)[2])
        user = query.from_user
        urgent_task = get_urgent_task(task_id)
        assignment = get_urgent_task_assignment(task_id, user.id)
        if not urgent_task or not assignment or assignment.get("status") != "reserved":
            await _query_answer(query, "❌ Нема активного бронювання", show_alert=True)
            return

        ctx.user_data["submitting_urgent_task_id"] = task_id
        lang = get_user_language(user.id)
        push_nav(ctx, "tasks")
        markup = InlineKeyboardMarkup([[_btn(get_message("cancel_btn", lang), callback_data="go_back")]])
        await query.message.reply_text(
            get_message("urgent_task_submit_prompt", lang, title=urgent_task["title"]),
            reply_markup=markup,
            parse_mode="Markdown",
        )
        return

    if data.startswith("urgent_approve_") or data.startswith("urgent_reject_"):
        action, assignment_id_str = data.split("_", 2)[1:3]
        assignment_id = int(assignment_id_str)
        assignment = get_urgent_assignment_by_id(assignment_id)
        if not assignment:
            await _query_answer(query, "❌ Заявку не знайдено.", show_alert=True)
            return

        dept_id = assignment["department_id"]
        is_admin = query.from_user.id in ADMIN_IDS
        is_supervisor = get_user_dept_role(query.from_user.id, dept_id) == "supervisor"
        if not is_admin and not is_supervisor:
            await _query_answer(query, "❌ Недостатньо прав.", show_alert=True)
            return

        if assignment.get("status") != "submitted":
            await _query_answer(query, "⚠️ Вже оброблено.", show_alert=True)
            return

        new_status = "approved" if action == "approve" else "rejected"
        review_urgent_assignment(assignment_id, new_status, query.from_user.id, review_comment=None)

        log_event("urgent_task_reviewed", user_id=assignment["user_id"], admin_id=query.from_user.id, data={
            "assignment_id": assignment_id,
            "urgent_task_id": assignment["urgent_task_id"],
            "status": new_status,
        })

        if new_status == "approved":
            xp_success = atomic_award_xp(
                user_id=assignment["user_id"],
                amount=assignment["xp_reward"],
                task_id=assignment["urgent_task_id"],
                dept_id=dept_id,
            )
            if not xp_success:
                await _query_answer(query, "❌ Помилка нарахування XP", show_alert=True)
                return

        approved_count = count_urgent_task_approved_assignments(assignment["urgent_task_id"])
        if approved_count >= assignment["required_slots"]:
            update_urgent_task_status(assignment["urgent_task_id"], "completed", is_active=0)

        ctx.user_data["pending_review_result"] = {
            "submission_id": assignment_id,
            "user_id": assignment["user_id"],
            "task_title": assignment["task_title"],
            "xp_reward": assignment["xp_reward"],
            "status": new_status,
            "is_urgent": True,
        }

        comment_markup = InlineKeyboardMarkup([
            [_btn("💬 Залишити коментар", callback_data=f"urgent_comment_yes_{assignment_id}")],
            [_btn("⏭ Без коментаря", callback_data=f"urgent_comment_no_{assignment_id}")],
        ])

        await ctx.bot.send_message(
            chat_id=query.from_user.id,
            text=_normalize_text("Хочеш додати коментар до результату?"),
            reply_markup=comment_markup,
        )
        return

    if data.startswith("urgent_comment_yes_") or data.startswith("urgent_comment_no_"):
        assignment_id = int(data.split("_")[-1])
        pending = ctx.user_data.get("pending_review_result")
        if not pending or pending.get("submission_id") != assignment_id:
            await _query_answer(query, "⚠️ Сесія коментаря завершена.", show_alert=True)
            return

        if data.startswith("urgent_comment_yes_"):
            ctx.user_data["awaiting_review_comment"] = pending
            ctx.user_data.pop("pending_review_result", None)
            await _query_answer(query)
            await ctx.bot.send_message(
                chat_id=query.from_user.id,
                text=_normalize_text("✍️ Напиши коментар для користувача:"),
            )
            return

        ctx.user_data.pop("pending_review_result", None)
        await _query_answer(query)
        log_event("urgent_review_comment_skipped", user_id=pending["user_id"], admin_id=query.from_user.id, data={
            "assignment_id": assignment_id,
            "task_title": pending["task_title"][:50],
        })
        await _send_review_result(ctx, pending, comment_text=None)
        return

    if data.startswith("approve_") or data.startswith("reject_"):
        if query.from_user.id not in ADMIN_IDS:
            await _query_answer(query, "❌ Тільки для адмінів!", show_alert=True)
            return

        action, sub_id_str = data.split("_", 1)
        sub_id = int(sub_id_str)
        sub = get_submission(sub_id)
        
        # Get admin's language
        lang = get_user_language(query.from_user.id)

        if not sub:
            await _query_answer(query, "❌ Заявку не знайдено.", show_alert=True)
            return
        if sub["status"] != "pending":
            await _query_answer(query, "⚠️ Вже оброблено.", show_alert=True)
            return

        new_status = "approved" if action == "approve" else "rejected"
        # Atomic update: returns False if already processed by another admin
        success = review_submission(sub_id, new_status, query.from_user.id)
        
        if not success:
            await _query_answer(query, "⚠️ Вже оброблено іншим адміном.", show_alert=True)
            return

        task = get_task(sub["task_id"])
        
        # Update task execution history  
        update_task_execution_by_task(
            sub["user_id"],
            sub["task_id"],
            status=new_status,
            submission_id=sub_id,
            result_notes=f"Reviewed by admin on {datetime.now().isoformat()}"
        )
        
        admin_tag = f"@{query.from_user.username}" if query.from_user.username else query.from_user.first_name

        if action == "approve":
            # 🔒 Use atomic XP award with verification
            xp_success = atomic_award_xp(
                user_id=sub["user_id"],
                amount=task["xp_reward"],
                task_id=sub["task_id"],
                dept_id=task.get("department_id")
            )
            
            if not xp_success:
                logger.error(f"❌ Failed to award XP for submission {sub_id}")
                await _query_answer(query, get_message("error_xp_calculation", lang), show_alert=True)
                return
            
            # 📊 Log task approval and XP award events
            log_event('task_approved', user_id=sub["user_id"], admin_id=query.from_user.id, data={
                'submission_id': sub_id,
                'task_id': sub["task_id"],
                'task_title': task.get('title', '')[:50] if task else '',
                'xp_awarded': task["xp_reward"]
            })
            log_event('xp_awarded', user_id=sub["user_id"], data={
                'amount': task["xp_reward"],
                'source': 'task_approval',
                'task_id': sub["task_id"]
            })
            
            result_icon = "✅ Схвалено"
        else:
            # 📊 Log task rejection event
            log_event('task_rejected', user_id=sub["user_id"], admin_id=query.from_user.id, data={
                'submission_id': sub_id,
                'task_id': sub["task_id"],
                'task_title': task.get('title', '')[:50] if task else ''
            })
            
            result_icon = "❌ Відхилено"

        submitter = get_user(sub["user_id"]) or query.from_user
        admin_text = _format_admin_submission_text(sub_id, submitter, task, sub.get("proof_text") or "")
        updated_admin_text = f"{admin_text}\n\n{result_icon} адміном {admin_tag}"
        await _update_submission_notifications(ctx, sub_id, updated_admin_text)

        ctx.user_data["pending_review_result"] = {
            "submission_id": sub_id,
            "user_id": sub["user_id"],
            "task_title": task["title"],
            "xp_reward": task["xp_reward"],
            "status": new_status,
        }

        comment_markup = InlineKeyboardMarkup([
            [_btn("💬 Залишити коментар", callback_data=f"review_comment_yes_{sub_id}")],
            [_btn("⏭ Без коментаря", callback_data=f"review_comment_no_{sub_id}")],
        ])

        await ctx.bot.send_message(
            chat_id=query.from_user.id,
            text=_normalize_text("Хочеш додати коментар до результату?"),
            reply_markup=comment_markup,
        )
        return

    if data.startswith("review_comment_yes_") or data.startswith("review_comment_no_"):
        if query.from_user.id not in ADMIN_IDS:
            await _query_answer(query, "❌ Тільки для адмінів!", show_alert=True)
            return

        sub_id = int(data.split("_")[-1])
        pending = ctx.user_data.get("pending_review_result")
        if not pending or pending.get("submission_id") != sub_id:
            await _query_answer(query, "⚠️ Сесія коментаря завершена.", show_alert=True)
            return

        if data.startswith("review_comment_yes_"):
            ctx.user_data["awaiting_review_comment"] = pending
            ctx.user_data.pop("pending_review_result", None)
            await _query_answer(query)
            await ctx.bot.send_message(
                chat_id=query.from_user.id,
                text=_normalize_text("✍️ Напиши коментар для користувача:"),
            )
            return

        # No comment chosen
        ctx.user_data.pop("pending_review_result", None)
        await _query_answer(query)
        log_event("review_comment_skipped", user_id=pending["user_id"], admin_id=query.from_user.id, data={
            "submission_id": pending["submission_id"],
            "task_title": pending["task_title"][:50],
        })
        await _send_review_result(ctx, pending, comment_text=None)
        return


async def _process_proof_payload(
    update: Update | None,
    ctx: ContextTypes.DEFAULT_TYPE,
    user,
    proof_text: str,
    proof_file_ids: list[str] | None,
):
    urgent_task_id = ctx.user_data.get("submitting_urgent_task_id")
    if urgent_task_id:
        urgent_task = get_urgent_task(urgent_task_id)
        assignment = get_urgent_task_assignment(urgent_task_id, user.id)
        if not urgent_task or not assignment or assignment.get("status") != "reserved":
            lang = get_user_language(user.id)
            await _send_user_message(ctx.bot, update, user.id, get_message("urgent_task_no_reservation", lang))
            ctx.user_data.pop("submitting_urgent_task_id", None)
            return

        proof_file_ids = proof_file_ids or []
        if not proof_text and not proof_file_ids:
            lang = get_user_language(user.id)
            await _send_user_message(ctx.bot, update, user.id, get_message("no_proof", lang))
            return

        update_urgent_assignment_submission(assignment["id"], proof_text, proof_file_ids)
        ctx.user_data.pop("submitting_urgent_task_id", None)

        log_event("urgent_task_submitted", user_id=user.id, data={
            "urgent_task_id": urgent_task_id,
            "assignment_id": assignment["id"],
        })

        await _send_user_message(
            ctx.bot,
            update,
            user.id,
            get_message("urgent_task_submitted", get_user_language(user.id), title=urgent_task["title"]),
            parse_mode="Markdown",
        )

        reviewers = set(ADMIN_IDS) | set(get_dept_supervisors(urgent_task["department_id"]))
        submitter_tag = f"@{user.username}" if user.username else user.first_name
        review_text = (
            f"🚨 *Термінове завдання на перевірку*\n\n"
            f"👤 Від: {submitter_tag} (ID: `{user.id}`)\n"
            f"📌 Завдання: *{urgent_task['title']}*\n"
            f"💎 XP: *{urgent_task['xp_reward']}*"
        )
        if proof_text:
            review_text += f"\n💬 Текст:\n{proof_text[:300]}"

        markup = InlineKeyboardMarkup(
            [[
                _btn("✅ Схвалити", callback_data=f"urgent_approve_{assignment['id']}"),
                _btn("❌ Відхилити", callback_data=f"urgent_reject_{assignment['id']}"),
            ]]
        )

        for reviewer_id in reviewers:
            try:
                if proof_file_ids and len(proof_file_ids) > 1:
                    media = [
                        InputMediaPhoto(
                            media=proof_file_ids[0],
                            caption=_normalize_text(review_text),
                            parse_mode="Markdown",
                        )
                    ]
                    media.extend([InputMediaPhoto(media=file_id) for file_id in proof_file_ids[1:]])
                    await ctx.bot.send_media_group(reviewer_id, media=media)
                    await ctx.bot.send_message(
                        reviewer_id,
                        _normalize_text(f"Оберіть дію для термінового #{assignment['id']}"),
                        reply_markup=markup,
                        parse_mode="Markdown",
                    )
                elif proof_file_ids:
                    await ctx.bot.send_photo(
                        reviewer_id,
                        photo=proof_file_ids[0],
                        caption=_normalize_text(review_text),
                        reply_markup=markup,
                        parse_mode="Markdown",
                    )
                else:
                    await ctx.bot.send_message(
                        reviewer_id,
                        _normalize_text(review_text),
                        reply_markup=markup,
                        parse_mode="Markdown",
                    )
            except Exception as exc:
                logger.error("Не вдалося надіслати супервізору %s: %s", reviewer_id, exc)
        return

    task_id = ctx.user_data.get("submitting_task_id")
    if not task_id:
        return

    task = get_task(task_id)

    if not task:
        lang = get_user_language(user.id)
        await _send_user_message(ctx.bot, update, user.id, get_message("task_not_found", lang))
        ctx.user_data.pop("submitting_task_id", None)
        return

    proof_file_ids = proof_file_ids or []
    if not proof_text and not proof_file_ids:
        lang = get_user_language(user.id)
        await _send_user_message(ctx.bot, update, user.id, get_message("no_proof", lang))
        return

    update_user_username(user.id, user.username, user.first_name)

    sub_id = add_submission(
        user.id,
        task_id,
        proof_text,
        proof_file_ids=proof_file_ids,
    )

    update_task_execution_by_task(
        user.id,
        task_id,
        status="submitted",
        submission_id=sub_id,
        result_notes=f"Proof submitted: {len(proof_text)} chars, files={len(proof_file_ids)}",
    )

    ctx.user_data.pop("submitting_task_id", None)

    log_event("task_submitted", user_id=user.id, data={
        "task_id": task_id,
        "submission_id": sub_id,
        "difficulty": task.get("difficulty_level", "unknown") if task else "unknown",
        "title": task.get("title", "")[:50] if task else "",
    })

    await _send_user_message(
        ctx.bot,
        update,
        user.id,
        f"✅ *Здано на перевірку!*\n\n«{task['title']}» — адмін перевірить найближчим часом. ⏳",
        parse_mode="Markdown",
    )

    admin_text = _format_admin_submission_text(sub_id, user, task, proof_text)
    markup = InlineKeyboardMarkup(
        [[
            _btn("✅ Схвалити", callback_data=f"approve_{sub_id}"),
            _btn("❌ Відхилити", callback_data=f"reject_{sub_id}"),
        ]]
    )

    for admin_id in ADMIN_IDS:
        try:
            if proof_file_ids and len(proof_file_ids) > 1:
                media = [
                    InputMediaPhoto(
                        media=proof_file_ids[0],
                        caption=_normalize_text(admin_text),
                        parse_mode="Markdown",
                    )
                ]
                media.extend([InputMediaPhoto(media=file_id) for file_id in proof_file_ids[1:]])
                await ctx.bot.send_media_group(admin_id, media=media)
                action_msg = await ctx.bot.send_message(
                    admin_id,
                    _normalize_text(f"Оберіть дію для заявки #{sub_id}"),
                    reply_markup=markup,
                    parse_mode="Markdown",
                )
                add_submission_notification(sub_id, admin_id, action_msg.message_id, "text")
            elif proof_file_ids and len(proof_file_ids) == 1:
                msg = await ctx.bot.send_photo(
                    admin_id,
                    photo=proof_file_ids[0],
                    caption=_normalize_text(admin_text),
                    reply_markup=markup,
                    parse_mode="Markdown",
                )
                add_submission_notification(sub_id, admin_id, msg.message_id, "photo")
            else:
                msg = await ctx.bot.send_message(
                    admin_id,
                    _normalize_text(admin_text),
                    reply_markup=markup,
                    parse_mode="Markdown",
                )
                add_submission_notification(sub_id, admin_id, msg.message_id, "text")
        except Exception as exc:
            logger.error("Не вдалося надіслати адміну %s: %s", admin_id, exc)


async def _process_proof(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    proof_text = update.message.text or update.message.caption or ""
    proof_file_ids: list[str] = []

    if update.message.photo:
        proof_file_ids = [update.message.photo[-1].file_id]
    elif update.message.document:
        proof_file_ids = [update.message.document.file_id]

    await _process_proof_payload(update, ctx, user, proof_text, proof_file_ids)


@rate_limit_user
async def handle_text_input(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle text input for wizards and ideas."""
    user = update.effective_user
    
    logger.info(f"📝 Text input from {user.id}: waiting_for_support={ctx.user_data.get('waiting_for_support')}, submitting_idea={ctx.user_data.get('submitting_idea')}, submitting_task_id={ctx.user_data.get('submitting_task_id')}")

    if ctx.user_data.get("awaiting_review_comment") and user and user.id in ADMIN_IDS:
        pending = ctx.user_data.pop("awaiting_review_comment", None)
        comment_text = (update.message.text or "").strip()
        if not comment_text:
            await _reply(update, "❌ Коментар не може бути порожнім.")
            ctx.user_data["awaiting_review_comment"] = pending
            return

        if pending.get("is_urgent"):
            update_urgent_assignment_comment(pending["submission_id"], comment_text)
            log_event("urgent_review_comment_added", user_id=pending["user_id"], admin_id=user.id, data={
                "assignment_id": pending["submission_id"],
                "task_title": pending["task_title"][:50],
            })
        else:
            update_submission_comment(pending["submission_id"], comment_text)
            log_event("review_comment_added", user_id=pending["user_id"], admin_id=user.id, data={
                "submission_id": pending["submission_id"],
                "task_title": pending["task_title"][:50],
            })
        await _send_review_result(ctx, pending, comment_text=comment_text)
        await _reply(update, "✅ Коментар надіслано користувачу.")
        return
    
    # Check if user is submitting task proof (text-based)
    if ctx.user_data.get("submitting_task_id"):
        await _process_proof(update, ctx)
        return
    
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
            await _reply(update, get_message("error_empty_message", lang))
            return
        
        lang = ctx.user_data.get("support_lang", "en")
        
        # Get user department info
        dept_name = "Unknown"
        try:
            dept_id = get_user_departments(user.id)
            if dept_id and len(dept_id) > 0:
                dept = get_department(dept_id[0])
                if dept:
                    dept_name = get_dept_name_translated(dept_id[0], 'uk')
        except Exception:
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
            confirm_text = get_message("error_send_failed", lang)
        
        await _reply(update, confirm_text)
        
        # Clear flag
        ctx.user_data["waiting_for_support"] = False
        return
    
    # Handle admin wizards
    wizard = _wizard(ctx)

    if user and user.id in ADMIN_IDS and wizard:
        chat_id = update.effective_chat.id
        text = (update.message.text or "").strip()
        lang = get_user_language(user.id)

        if wizard["type"] == "add_task":
            if wizard["step"] == "title":
                if not text:
                    await _wizard_prompt(ctx, chat_id, "❌ Назва не може бути порожньою. Введи назву:")
                    return
                wizard["payload"]["title"] = text
                wizard["step"] = "description"
                await _wizard_prompt(ctx, chat_id, "📝 *Крок 4: Введи опис* завдання:")
                return

            if wizard["step"] == "description":
                wizard["payload"]["description"] = text
                wizard["step"] = "xp"
                await _wizard_prompt(ctx, chat_id, "💎 *Крок 5: Введи XP* (ціле число > 0):")
                return

            if wizard["step"] == "xp":
                try:
                    xp = int(text)
                    if xp <= 0:
                        raise ValueError
                except ValueError:
                    await _wizard_prompt(ctx, chat_id, get_message("error_xp_must_be_number", lang))
                    return

                wizard["payload"]["xp"] = xp

                task_id = add_task(
                    wizard["payload"]["title"],
                    wizard["payload"].get("description", ""),
                    wizard["payload"]["xp"],
                    difficulty_level=wizard["payload"].get("difficulty", "easy"),
                    department_id=wizard["payload"].get("department"),
                )

                sent_count = 0
                if wizard["payload"].get("department"):
                    sent_count = await _notify_department_new_task(
                        ctx.bot,
                        wizard["payload"]["department"],
                        wizard["payload"]["title"],
                        wizard["payload"].get("description", ""),
                    )
                else:
                    sent_count = await _notify_all_new_task(
                        ctx.bot,
                        wizard["payload"]["title"],
                        wizard["payload"].get("description", ""),
                    )

                log_event("task_push_sent", admin_id=user.id, data={
                    "task_id": task_id,
                    "department_id": wizard["payload"].get("department"),
                    "sent_count": sent_count,
                })

                await _cleanup_wizard_prompts(ctx, chat_id)
                _clear_wizard(ctx)

                dept_text = ""
                if wizard["payload"].get("department"):
                    dept = get_department(wizard["payload"]["department"])
                    if dept:
                        dept_name = get_dept_name_translated(wizard["payload"]["department"], "uk")
                        dept_text = f"\n🏢 Департамент: {dept_name}"

                result_msg = (
                    "✅ *Завдання додано*\n\n"
                    f"ID: `{task_id}`\n"
                    f"Назва: {wizard['payload']['title']}\n"
                    f"Опис: {wizard['payload'].get('description', '-')}\n"
                    f"Складність: {wizard['payload'].get('difficulty', 'easy')}\n"
                    f"XP: {wizard['payload']['xp']}{dept_text}\n"
                    f"📢 Повідомлень надіслано: {sent_count}"
                )

                await _reply(update, result_msg, parse_mode="Markdown")
                return

        if wizard["type"] == "give_xp":
            if wizard["step"] == "user_id":
                try:
                    target_uid = int(text)
                except ValueError:
                    await _wizard_prompt(ctx, chat_id, get_message("error_user_id_must_be_number", lang))
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
                    await _wizard_prompt(ctx, chat_id, get_message("error_xp_cannot_be_zero", lang))
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

        if wizard["type"] == "push_broadcast":
            if wizard["step"] == "user_id":
                try:
                    target_uid = int(text)
                except ValueError:
                    await _wizard_prompt(ctx, chat_id, get_message("error_user_id_must_be_number", lang))
                    return

                target_user = get_user_summary(target_uid)
                if not target_user:
                    await _wizard_prompt(ctx, chat_id, "❌ Користувача не знайдено. Введи інший user_id:")
                    return

                wizard["payload"]["user_id"] = target_uid
                wizard["step"] = "message"
                await _wizard_prompt(ctx, chat_id, get_message("admin_push_prompt_text", "uk"))
                return

            if wizard["step"] == "message":
                if not text:
                    await _wizard_prompt(ctx, chat_id, "❌ Текст не може бути порожнім. Введи повідомлення:")
                    return

                target = wizard["payload"].get("target")
                dept_id = wizard["payload"].get("dept_id")
                target_uid = wizard["payload"].get("user_id")

                sent_count = await _send_admin_push(
                    ctx.bot,
                    target=target,
                    text=text,
                    dept_id=dept_id,
                    user_id=target_uid,
                )

                log_event("admin_push_sent", admin_id=user.id, data={
                    "target": target,
                    "department_id": dept_id,
                    "target_user_id": target_uid,
                    "sent_count": sent_count,
                })

                await _cleanup_wizard_prompts(ctx, chat_id)
                _clear_wizard(ctx)
                await _reply(update, get_message("admin_push_sent", lang, count=sent_count), parse_mode="Markdown")
                return

        if wizard["type"] == "urgent_task":
            if wizard["step"] == "title":
                if not text:
                    await _wizard_prompt(ctx, chat_id, "❌ Назва не може бути порожньою. Введи назву:")
                    return
                wizard["payload"]["title"] = text
                wizard["step"] = "description"
                await _wizard_prompt(ctx, chat_id, "📝 Введи *опис* термінового завдання:")
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
                    await _wizard_prompt(ctx, chat_id, get_message("error_xp_must_be_number", lang))
                    return
                wizard["payload"]["xp"] = xp
                wizard["step"] = "slots"
                await _wizard_prompt(ctx, chat_id, "👥 Введи кількість людей для цього завдання:")
                return

            if wizard["step"] == "slots":
                try:
                    slots = int(text)
                    if slots <= 0:
                        raise ValueError
                except ValueError:
                    await _wizard_prompt(ctx, chat_id, "❌ Кількість має бути числом > 0:")
                    return
                wizard["payload"]["slots"] = slots
                wizard["step"] = "deadline"
                await _wizard_prompt(ctx, chat_id, "⏰ Введи дедлайн (YYYY-MM-DD HH:MM) або '.' щоб пропустити:")
                return

            if wizard["step"] == "deadline":
                deadline_at = None if text.strip() == "." else text.strip()
                payload = wizard["payload"]

                urgent_id = add_urgent_task(
                    payload["title"],
                    payload.get("description", ""),
                    payload["xp"],
                    payload["department"],
                    payload["slots"],
                    deadline_at,
                    user.id,
                )

                sent_count = await _notify_department_new_urgent_task(
                    ctx.bot,
                    payload["department"],
                    payload["title"],
                    payload.get("description", ""),
                    payload["xp"],
                    payload["slots"],
                    deadline_at,
                )

                log_event("urgent_task_created", admin_id=user.id, data={
                    "urgent_task_id": urgent_id,
                    "department_id": payload["department"],
                    "slots": payload["slots"],
                    "deadline_at": deadline_at,
                    "sent_count": sent_count,
                })

                await _cleanup_wizard_prompts(ctx, chat_id)
                _clear_wizard(ctx)
                await _reply(update, get_message("urgent_admin_created", lang, task_id=urgent_id, count=sent_count), parse_mode="Markdown")
                return

        if wizard["type"] == "urgent_assign":
            if wizard["step"] == "user_id":
                task_id = wizard["payload"]["task_id"]
                urgent_task = get_urgent_task(task_id)
                if not urgent_task:
                    await _reply(update, "❌ Завдання не знайдено")
                    _clear_wizard(ctx)
                    return

                raw_ids = [item.strip() for item in text.split(",") if item.strip()]
                user_ids = []
                for item in raw_ids:
                    try:
                        user_ids.append(int(item))
                    except ValueError:
                        continue

                if not user_ids:
                    await _wizard_prompt(ctx, chat_id, "❌ Введи хоча б один коректний user_id:")
                    return

                active_count = count_urgent_task_active_assignments(task_id)
                slots_left = max(urgent_task["required_slots"] - active_count, 0)
                assigned_count = 0

                for target_uid in user_ids:
                    if slots_left <= 0:
                        break
                    if urgent_task["department_id"] not in get_user_departments(target_uid):
                        continue
                    existing = get_urgent_task_assignment(task_id, target_uid)
                    if existing and existing.get("status") in ("reserved", "submitted", "approved"):
                        continue
                    add_urgent_task_assignment(task_id, target_uid, assigned_by=user.id)
                    slots_left -= 1
                    assigned_count += 1
                    try:
                        await ctx.bot.send_message(
                            chat_id=target_uid,
                            text=_normalize_text(get_message("urgent_assigned_user", lang, title=urgent_task["title"]))
                        )
                    except Exception:
                        pass

                active_count = count_urgent_task_active_assignments(task_id)
                if active_count >= urgent_task["required_slots"]:
                    update_urgent_task_status(task_id, "in_progress")

                log_event("urgent_task_assigned", admin_id=user.id, data={
                    "urgent_task_id": task_id,
                    "assigned_count": assigned_count,
                })

                await _cleanup_wizard_prompts(ctx, chat_id)
                _clear_wizard(ctx)
                await _reply(update, get_message("urgent_admin_assigned", lang, count=assigned_count), parse_mode="Markdown")
                return

        if wizard["type"] == "urgent_replace":
            if wizard["step"] == "replace":
                task_id = wizard["payload"]["task_id"]
                urgent_task = get_urgent_task(task_id)
                if not urgent_task:
                    await _reply(update, "❌ Завдання не знайдено")
                    _clear_wizard(ctx)
                    return

                parts = text.split()
                if len(parts) != 2:
                    await _wizard_prompt(ctx, chat_id, "❌ Введи старий user_id і новий user_id через пробіл:")
                    return

                try:
                    old_uid = int(parts[0])
                    new_uid = int(parts[1])
                except ValueError:
                    await _wizard_prompt(ctx, chat_id, "❌ user_id має бути числом. Спробуй ще раз:")
                    return

                old_assignment = get_urgent_task_assignment(task_id, old_uid)
                if not old_assignment or old_assignment.get("status") not in ("reserved", "submitted"):
                    await _reply(update, "❌ Старий користувач не забронював це завдання")
                    _clear_wizard(ctx)
                    return

                if urgent_task["department_id"] not in get_user_departments(new_uid):
                    await _reply(update, "❌ Новий користувач не в цьому департаменті")
                    _clear_wizard(ctx)
                    return

                new_assignment = get_urgent_task_assignment(task_id, new_uid)
                if new_assignment and new_assignment.get("status") in ("reserved", "submitted", "approved"):
                    await _reply(update, "❌ Новий користувач вже забронював завдання")
                    _clear_wizard(ctx)
                    return

                review_urgent_assignment(old_assignment["id"], "rejected", user.id, review_comment="Reassigned")
                add_urgent_task_assignment(task_id, new_uid, assigned_by=user.id)

                active_count = count_urgent_task_active_assignments(task_id)
                if active_count >= urgent_task["required_slots"]:
                    update_urgent_task_status(task_id, "in_progress")

                try:
                    await ctx.bot.send_message(
                        chat_id=old_uid,
                        text=_normalize_text(get_message("urgent_reassigned_old", lang, title=urgent_task["title"]))
                    )
                except Exception:
                    pass
                try:
                    await ctx.bot.send_message(
                        chat_id=new_uid,
                        text=_normalize_text(get_message("urgent_reassigned_new", lang, title=urgent_task["title"]))
                    )
                except Exception:
                    pass

                log_event("urgent_task_reassigned", admin_id=user.id, data={
                    "urgent_task_id": task_id,
                    "old_user_id": old_uid,
                    "new_user_id": new_uid,
                })

                await _cleanup_wizard_prompts(ctx, chat_id)
                _clear_wizard(ctx)
                await _reply(update, get_message("urgent_admin_reassigned", lang), parse_mode="Markdown")
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
                    await _wizard_prompt(ctx, chat_id, get_message("error_price_must_be_number", lang))
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
                        await _wizard_prompt(ctx, chat_id, get_message("error_price_invalid_decimal", lang))
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
                await _wizard_prompt(ctx, chat_id, get_message("error_text_cannot_be_empty", lang))
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

    # Handle edit_task_wizard (separate from admin_wizard)
    edit_task_wizard = ctx.user_data.get("edit_task_wizard")
    if user and user.id in ADMIN_IDS and edit_task_wizard:
        chat_id = update.effective_chat.id
        text = (update.message.text or "").strip()
        lang = get_user_language(user.id)
        
        field = edit_task_wizard["field"]
        task_id = edit_task_wizard["task_id"]
        
        if field == "title":
            if not text:
                await _wizard_prompt(ctx, chat_id, "❌ Назва не може бути порожньою. Введи назву:")
                return
            update_task(task_id, title=text)
            await _cleanup_wizard_prompts(ctx, chat_id)
            ctx.user_data.pop("edit_task_wizard", None)
            _page = edit_task_wizard["page"]
            _dept_filter = edit_task_wizard.get("dept_filter")
            _difficulty = edit_task_wizard.get("difficulty")
            await _reply(update, "✅ Назву завдання оновлено!", parse_mode="Markdown")
            return
        
        elif field == "description":
            update_task(task_id, description=text)
            await _cleanup_wizard_prompts(ctx, chat_id)
            ctx.user_data.pop("edit_task_wizard", None)
            await _reply(update, "✅ Опис завдання оновлено!", parse_mode="Markdown")
            return
        
        elif field == "xp":
            try:
                xp = int(text)
                if xp <= 0:
                    raise ValueError
            except ValueError:
                await _wizard_prompt(ctx, chat_id, get_message("error_xp_must_be_number", lang))
                return
            update_task(task_id, xp_reward=xp)
            await _cleanup_wizard_prompts(ctx, chat_id)
            ctx.user_data.pop("edit_task_wizard", None)
            await _reply(update, "✅ XP завдання оновлено!", parse_mode="Markdown")
            return

    await _process_proof(update, ctx)


@rate_limit_user
async def handle_proof_media(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    if message and message.media_group_id and message.photo:
        group_id = message.media_group_id
        media_groups = ctx.user_data.setdefault("media_groups", {})
        group = media_groups.get(group_id)
        if not group:
            group = {
                "file_ids": [],
                "text": "",
                "job": None,
                "user": update.effective_user,
            }
            media_groups[group_id] = group

        if message.caption and not group["text"]:
            group["text"] = message.caption
        group["file_ids"].append(message.photo[-1].file_id)

        if group.get("job"):
            try:
                group["job"].schedule_removal()
            except Exception:
                pass

        if ctx.application.job_queue:
            group["job"] = ctx.application.job_queue.run_once(
                _process_media_group_job,
                when=1.0,
                data={"user_id": update.effective_user.id, "group_id": group_id},
            )
        return

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
            user_id = update.message.from_user.id
            lang = get_user_language(user_id)
            await update.message.reply_text(
                "❌ *Помилка!*\n\n" + get_message("error_generic", lang),
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Could not send error message to user: {e}")


async def _notify_department_new_task(bot, dept_id: int, task_title: str, task_desc: str):
    """Send notification to all users in a department about a new task."""
    try:
        users = get_users_in_department(dept_id)
        sent_count = 0
        failed_count = 0
        
        # Get department name
        dept = get_department(dept_id)
        if dept:
            dept_name = get_dept_name_translated(dept_id, "uk")
            emoji = dept['emoji']
        else:
            dept_name = f'Dept#{dept_id}'
            emoji = '📌'
        
        msg_text = (
            f"{emoji} *Нове завдання в {dept_name}!*\n\n"
            f"📌 *{task_title}*\n"
            f"{task_desc}\n\n"
            f"Перевір нове завдання в /tasks"
        )
        
        for user in users:
            try:
                await bot.send_message(
                    chat_id=user['user_id'],
                    text=msg_text,
                    parse_mode="Markdown"
                )
                sent_count += 1
            except Exception as e:
                logger.warning(f"Failed to notify user {user['user_id']}: {e}")
                failed_count += 1
        
        logger.info(f"📢 Notifications sent: {sent_count}/{len(users)} users in {dept_name}")
        return sent_count
    except Exception as e:
        logger.error(f"Error notifying department {dept_id}: {e}")
        return 0


async def _notify_all_new_task(bot, task_title: str, task_desc: str):
    """Send notification to all users about a new global task."""
    try:
        users = list_all_users()
        sent_count = 0
        failed_count = 0
        msg_text = (
            "📢 *Нове завдання для всіх!*\n\n"
            f"📌 *{task_title}*\n"
            f"{task_desc}\n\n"
            "Перевір нове завдання в /tasks"
        )

        for user in users:
            if user.get("is_banned"):
                continue
            try:
                await bot.send_message(
                    chat_id=user["user_id"],
                    text=msg_text,
                    parse_mode="Markdown",
                )
                sent_count += 1
            except Exception as e:
                logger.warning(f"Failed to notify user {user['user_id']}: {e}")
                failed_count += 1

        logger.info(f"📢 Global notifications sent: {sent_count}/{len(users)}")
        return sent_count
    except Exception as e:
        logger.error(f"Error notifying all users: {e}")
        return 0


async def _notify_department_new_urgent_task(
    bot,
    dept_id: int,
    task_title: str,
    task_desc: str,
    xp_reward: int,
    required_slots: int,
    deadline_at: str | None,
):
    try:
        users = get_users_in_department(dept_id)
        sent_count = 0
        dept = get_department(dept_id)
        dept_name = get_dept_name_translated(dept_id, "uk") if dept else f"Dept#{dept_id}"
        emoji = dept["emoji"] if dept else "🚨"
        deadline_line = f"\n⏰ Дедлайн: {deadline_at}" if deadline_at else ""

        msg_text = (
            f"{emoji} *Нове термінове завдання!*\n\n"
            f"📌 *{task_title}*\n"
            f"{task_desc}\n"
            f"💎 XP: *{xp_reward}*\n"
            f"👥 Потрібно людей: *{required_slots}*"
            f"{deadline_line}\n\n"
            f"Перевір /tasks → Термінові ( {dept_name} )"
        )

        for user in users:
            if user.get("is_banned"):
                continue
            try:
                await bot.send_message(
                    chat_id=user["user_id"],
                    text=msg_text,
                    parse_mode="Markdown",
                )
                sent_count += 1
            except Exception as e:
                logger.warning(f"Failed to notify user {user['user_id']}: {e}")

        logger.info(f"📢 Urgent notifications sent: {sent_count}/{len(users)} users in {dept_name}")
        return sent_count
    except Exception as e:
        logger.error(f"Error notifying department {dept_id} urgent task: {e}")
        return 0


async def _send_admin_push(bot, target: str, text: str, dept_id: int | None = None, user_id: int | None = None):
    recipients = []
    if target == "all":
        recipients = list_all_users()
    elif target == "dept" and dept_id:
        recipients = get_users_in_department(dept_id)
    elif target == "user" and user_id:
        user = get_user(user_id)
        recipients = [user] if user else []

    sent_count = 0
    for user in recipients:
        if not user or user.get("is_banned"):
            continue
        try:
            await bot.send_message(
                chat_id=user["user_id"],
                text=_normalize_text(text),
                parse_mode="Markdown",
            )
            sent_count += 1
        except Exception as exc:
            logger.warning(f"Failed to send push to {user.get('user_id')}: {exc}")

    return sent_count


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
    log_bot_startup(users_count, depts_count, 0, 0)
    
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Add error handler to catch all errors
    app.add_error_handler(handle_error)

    # Global user action logging (non-blocking)
    app.add_handler(MessageHandler(filters.ALL, log_user_message_update), group=-1, block=False)
    app.add_handler(CallbackQueryHandler(log_user_callback_update), group=-1, block=False)
    
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
    app.add_handler(CommandHandler("urgent", cmd_urgent))
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
    
    # Task pagination handlers (must be before general tasks_ handler)
    app.add_handler(CallbackQueryHandler(handle_tasks_page_next, pattern="^tasks_page_next_"))
    app.add_handler(CallbackQueryHandler(handle_tasks_page_prev, pattern="^tasks_page_prev_"))
    
    # Task department selection (when user has multiple departments)
    app.add_handler(CallbackQueryHandler(handle_task_dept_select, pattern="^task_dept_select_"))
    
    # Task category selection (easy/medium/hard)
    app.add_handler(CallbackQueryHandler(handle_tasks_category, pattern="^tasks_(easy|medium|hard|urgent)$"))
    
    app.add_handler(CallbackQueryHandler(handle_idea_anonymity_choice, pattern="^idea_(named|anon)$"))
    
    # Shop & other callbacks
    app.add_handler(CallbackQueryHandler(shop_callback_handler, pattern="shop_buy_.*"))
    
    # Wizard callbacks (must be before main button handler)
    app.add_handler(CallbackQueryHandler(handle_wizard_callbacks, pattern="^wizard_"))
    
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



