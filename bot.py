import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters,
)

from config import BOT_TOKEN, ADMIN_IDS
from database import (
    init_db, register_user, get_user, add_xp, get_leaderboard,
    get_user_rank, get_tasks, get_task, add_task, delete_task,
    add_submission, get_submission, review_submission,
    has_pending, has_approved, get_stats,
)

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    register_user(user)
    await update.message.reply_text(
        f"👋 Привіт, *{user.first_name}*!\n\n"
        "Виконуй завдання → отримуй XP → потрапляй у топ!\n\n"
        "📋 /tasks — список завдань\n"
        "⭐ /xp — мій профіль\n"
        "🏆 /leaderboard — таблиця лідерів\n"
        "❓ /help — як це працює",
        parse_mode="Markdown"
    )


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 *Як це працює:*\n\n"
        "1️⃣ Переглянь завдання: /tasks\n"
        "2️⃣ Виконай завдання\n"
        "3️⃣ Натисни *«📤 Здати»* під завданням\n"
        "4️⃣ Надішли підтвердження (скріншот або текст)\n"
        "5️⃣ Адмін перевірить і нарахує XP ✨\n\n"
        "Щоб скасувати здачу — /cancel",
        parse_mode="Markdown"
    )


async def cmd_tasks(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    register_user(user)
    tasks = get_tasks()

    if not tasks:
        await update.message.reply_text("😕 Наразі завдань немає. Зазирни пізніше!")
        return

    await update.message.reply_text("📋 *Список завдань:*", parse_mode="Markdown")

    for task in tasks:
        done    = has_approved(user.id, task["id"])
        pending = has_pending(user.id,  task["id"])

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
            btn = InlineKeyboardButton("✅ Виконано", callback_data="noop")
        elif pending:
            btn = InlineKeyboardButton("⏳ На перевірці", callback_data="noop")
        else:
            btn = InlineKeyboardButton("📤 Здати завдання", callback_data=f"submit_{task['id']}")

        markup = InlineKeyboardMarkup([[btn]])
        await update.message.reply_text(text, reply_markup=markup, parse_mode="Markdown")


async def cmd_xp(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    register_user(user)
    db_user = get_user(user.id)
    rank, total = get_user_rank(user.id)

    await update.message.reply_text(
        f"⭐ *Профіль {user.first_name}*\n\n"
        f"💎 XP: *{db_user['xp']}*\n"
        f"🏆 Місце: *#{rank}* з {total} учасників",
        parse_mode="Markdown"
    )


async def cmd_leaderboard(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    top = get_leaderboard()

    if not top:
        await update.message.reply_text("😕 Таблиця порожня. Будь першим!")
        return

    medals = ["🥇", "🥈", "🥉"]
    lines = ["🏆 *Таблиця лідерів*\n"]
    for i, u in enumerate(top):
        icon = medals[i] if i < 3 else f"{i + 1}."
        name = u["first_name"] or u["username"] or f"User{u['user_id']}"
        lines.append(f"{icon} {name} — *{u['xp']} XP*")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if ctx.user_data.pop("submitting_task_id", None):
        await update.message.reply_text("❌ Здачу скасовано.")
    else:
        await update.message.reply_text("Нічого активного немає.")


def admin_only(func):
    async def wrapper(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id not in ADMIN_IDS:
            await update.message.reply_text("❌ Тільки для адмінів!")
            return
        return await func(update, ctx)
    return wrapper


@admin_only
async def cmd_addtask(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    raw = " ".join(ctx.args)
    try:
        xp_str, rest = raw.split(" ", 1)
        xp = int(xp_str)
        title, _, description = rest.partition("|")
        title = title.strip()
        description = description.strip()
        if not title:
            raise ValueError
    except ValueError:
        await update.message.reply_text(
            "❌ Формат: /addtask <XP> <назва> | <опис>\n"
            "Приклад: /addtask 50 Написати відгук | Напиши відгук про наш канал"
        )
        return

    task_id = add_task(title, description, xp)
    await update.message.reply_text(
        f"✅ Завдання #{task_id} додано!\n"
        f"📌 {title}\n💎 {xp} XP"
    )


@admin_only
async def cmd_deltask(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        task_id = int(ctx.args[0])
        delete_task(task_id)
        await update.message.reply_text(f"✅ Завдання #{task_id} деактивовано.")
    except (IndexError, ValueError):
        await update.message.reply_text("❌ Формат: /deltask <task_id>")


@admin_only
async def cmd_givexp(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        uid = int(ctx.args[0])
        amount = int(ctx.args[1])
        add_xp(uid, amount)
        await update.message.reply_text(f"✅ Нараховано {amount} XP → {uid}")
    except (IndexError, ValueError):
        await update.message.reply_text("❌ Формат: /givexp <user_id> <кількість>")


@admin_only
async def cmd_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    users, tasks, pending, approved = get_stats()
    await update.message.reply_text(
        f"📊 *Статистика*\n\n"
        f"👥 Користувачів: {users}\n"
        f"📋 Активних завдань: {tasks}\n"
        f"⏳ На перевірці: {pending}\n"
        f"✅ Схвалено: {approved}",
        parse_mode="Markdown"
    )


async def on_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("submit_"):
        task_id = int(data.split("_", 1)[1])
        user = query.from_user
        register_user(user)

        if has_approved(user.id, task_id):
            await query.answer("✅ Ти вже виконав це завдання!", show_alert=True)
            return
        if has_pending(user.id, task_id):
            await query.answer("⏳ Твоя відповідь вже на перевірці!", show_alert=True)
            return

        task = get_task(task_id)
        ctx.user_data["submitting_task_id"] = task_id

        await query.message.reply_text(
            f"📤 *Здача: {task['title']}*\n\n"
            f"Надішли підтвердження виконання:\n"
            f"• 📸 Скріншот\n"
            f"• 📝 Або текстовий опис\n\n"
            f"_Щоб скасувати — /cancel_",
            parse_mode="Markdown"
        )

    elif data.startswith("approve_") or data.startswith("reject_"):
        if query.from_user.id not in ADMIN_IDS:
            await query.answer("❌ Тільки для адмінів!", show_alert=True)
            return

        action, sub_id_str = data.split("_", 1)
        sub_id = int(sub_id_str)
        sub = get_submission(sub_id)

        if not sub:
            await query.answer("❌ Заявку не знайдено.", show_alert=True)
            return
        if sub["status"] != "pending":
            await query.answer("⚠️ Вже оброблено.", show_alert=True)
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
            await ctx.bot.send_message(sub["user_id"], user_msg, parse_mode="Markdown")
        except Exception:
            pass

        suffix = f"\n\n{result_icon} адміном {admin_tag}"
        try:
            if query.message.caption:
                await query.edit_message_caption(
                    caption=query.message.caption + suffix,
                    parse_mode="Markdown",
                    reply_markup=None
                )
            else:
                await query.edit_message_text(
                    text=query.message.text + suffix,
                    parse_mode="Markdown",
                    reply_markup=None
                )
        except Exception:
            pass


async def handle_proof(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    task_id = ctx.user_data.get("submitting_task_id")
    if not task_id:
        return

    user = update.effective_user
    task = get_task(task_id)

    if not task:
        await update.message.reply_text("❌ Завдання не знайдено. /tasks")
        ctx.user_data.pop("submitting_task_id", None)
        return

    proof_text = update.message.text or update.message.caption or ""
    proof_file_id = None

    if update.message.photo:
        proof_file_id = update.message.photo[-1].file_id
    elif update.message.document:
        proof_file_id = update.message.document.file_id

    if not proof_text and not proof_file_id:
        await update.message.reply_text("❌ Надішли текст або зображення.")
        return

    sub_id = add_submission(user.id, task_id, proof_text, proof_file_id)
    ctx.user_data.pop("submitting_task_id", None)

    await update.message.reply_text(
        f"✅ *Здано на перевірку!*\n\n"
        f"«{task['title']}» — адмін перевірить найближчим часом. ⏳",
        parse_mode="Markdown"
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

    markup = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Схвалити", callback_data=f"approve_{sub_id}"),
        InlineKeyboardButton("❌ Відхилити", callback_data=f"reject_{sub_id}"),
    ]])

    for admin_id in ADMIN_IDS:
        try:
            if proof_file_id and update.message.photo:
                await ctx.bot.send_photo(
                    admin_id,
                    photo=proof_file_id,
                    caption=admin_text,
                    reply_markup=markup,
                    parse_mode="Markdown"
                )
            else:
                await ctx.bot.send_message(
                    admin_id,
                    admin_text,
                    reply_markup=markup,
                    parse_mode="Markdown"
                )
        except Exception as e:
            logger.error(f"Не вдалося надіслати адміну {admin_id}: {e}")


def main():
    init_db()

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start",       cmd_start))
    app.add_handler(CommandHandler("help",        cmd_help))
    app.add_handler(CommandHandler("tasks",       cmd_tasks))
    app.add_handler(CommandHandler("xp",          cmd_xp))
    app.add_handler(CommandHandler("leaderboard", cmd_leaderboard))
    app.add_handler(CommandHandler("cancel",      cmd_cancel))

    app.add_handler(CommandHandler("addtask",  cmd_addtask))
    app.add_handler(CommandHandler("deltask",  cmd_deltask))
    app.add_handler(CommandHandler("givexp",   cmd_givexp))
    app.add_handler(CommandHandler("stats",    cmd_stats))

    app.add_handler(CallbackQueryHandler(on_button))

    app.add_handler(MessageHandler(
        (filters.TEXT & ~filters.COMMAND) | filters.PHOTO | filters.Document.ALL,
        handle_proof
    ))

    logger.info("🤖 Бот запущено!")
    app.run_polling()


if __name__ == "__main__":
    main()