"""Multi-language message system for xp-bot"""

import logging

logger = logging.getLogger(__name__)

# All messages in 3 languages: English (en), Romanian (ro), Ukrainian (uk)
MESSAGES = {
    # ========== STARTUP FLOW ==========
    "lang_select": {
        "en": "🌍 *Select language / Selectează limba / Виберіть мову:*",
        "ro": "🌍 *Select language / Selectează limba / Виберіть мову:*",
        "uk": "🌍 *Абери мову / Selectează limba / Виберіть мову:*",
    },
    
    "lang_en_btn": {
        "en": "English",
        "ro": "English",
        "uk": "English",
    },
    
    "lang_ro_btn": {
        "en": "Română",
        "ro": "Română",
        "uk": "Română",
    },
    
    "lang_uk_btn": {
        "en": "Українська",
        "ro": "Українська",
        "uk": "Українська",
    },
    
    "lang_selected": {
        "en": "✅ Language set to: *English*\n\nNow checking your subscription...",
        "ro": "✅ Limba setată la: *Română*\n\nAcum verific abonamentul tău...",
        "uk": "✅ Мова встановлена: *Українська*\n\nТепер перевіримо твою підписку...",
    },
    
    "verify_subscribed": {
        "en": "✅ *Thank you! You're subscribed* 🎉\n\nNow select your department:",
        "ro": "✅ *Mulțumesc! Ești abonat* 🎉\n\nAcum selectează departamentul tău:",
        "uk": "✅ *Спасибо! Ти підписаний* 🎉\n\nТепер обери свій департамент:",
    },
    
    "verify_not_subscribed": {
        "en": "📱 *Hello, {first_name}!*\n\nTo continue, first subscribe to our channel:\n👉 https://t.me/aturinfo\n\nOnce subscribed, click the button below 👇",
        "ro": "📱 *Bună, {first_name}!*\n\nPentru a continua, mai întâi abonează-te la canalul nostru:\n👉 https://t.me/aturinfo\n\nOdată abonat, apasă butonul de mai jos 👇",
        "uk": "📱 *Привіт, {first_name}!*\n\nЩоб продовжити, спочатку підпишись на наш канал:\n👉 https://t.me/aturinfo\n\nЯк підпишешся, натисни кнопку нижче 👇",
    },
    
    "verify_btn": {
        "en": "✅ I'm already subscribed",
        "ro": "✅ Sunt deja abonat",
        "uk": "✅ Я вже підписаний",
    },
    
    "verify_checking": {
        "en": "⏳ *Checking subscription...*",
        "ro": "⏳ *Verific abonamentul...*",
        "uk": "⏳ *Перевіряю підписку...*",
    },
    
    "dept_select": {
        "en": "🏢 *Select your department:*",
        "ro": "🏢 *Selectează-ți departamentul:*",
        "uk": "🏢 *Обери свій департамент:*",
    },

    "dept_multi_select": {
        "en": "🏢 *Select your departments* (you can choose multiple):\n\n✓ = selected | ☐ = not selected",
        "ro": "🏢 *Selectează-ți departamentele* (poți alege mai multe):\n\n✓ = selectat | ☐ = neselecționat",
        "uk": "🏢 *Обери свої департаменти* (можеш вибрати кілька):\n\n✓ = вибрано | ☐ = не вибрано",
    },

    "dept_multi_done": {
        "en": "✅ *Departments saved!*",
        "ro": "✅ *Departamente salvate!*",
        "uk": "✅ *Департаменти збережені!*",
    },

    "dept_btn_done": {
        "en": "✅ Done",
        "ro": "✅ Gata",
        "uk": "✅ Готово",
    },

    "dept_welcome": {
        "en": "✅ *Great, {first_name}!*\n\n🐿 Welcome to ATUR! I'm Білка Валерій!\n\nYou're in department: *{emoji} {dept_name}*\n\nNow you can start completing tasks!\n\n✨ /tasks — task list\n⭐ /xp — your profile\n🏆 /leaderboard — top players",
        "ro": "✅ *Grozav, {first_name}!*\n\n🐿 Bine ai venit la ATUR! Sunt Білка Валерій!\n\nEști în departamentul: *{emoji} {dept_name}*\n\nAcum poți începe să completezi sarcini!\n\n✨ /tasks — lista sarcinilor\n⭐ /xp — profilul tău\n🏆 /leaderboard — top jucători",
        "uk": "✅ *Чудово, {first_name}!*\n\n🐿 Ласкаво просимо до ATUR! Я Білка Валерій!\n\nТи в департаменті: *{emoji} {dept_name}*\n\nТепер можеш розпочати виконувати завдання!\n\n✨ /tasks — список завдань\n⭐ /xp — твій профіль\n🏆 /leaderboard — топ гравців",
    },
    
    "welcome_returning": {
        "en": "👋 *Welcome back, {first_name}!*\n\n🏢 Department: *{emoji} {dept_name}*\n\n✨ /tasks — tasks\n⭐ /xp — profile\n🏆 /leaderboard — leaderboard\n🎯 /idea — share an idea",
        "ro": "👋 *Bine ai revenit, {first_name}!*\n\n🏢 Departament: *{emoji} {dept_name}*\n\n✨ /tasks — sarcini\n⭐ /xp — profil\n🏆 /leaderboard — clasament\n🎯 /idea — partajează o idee",
        "uk": "👋 *Привіт знову, {first_name}!*\n\n🏢 Департамент: *{emoji} {dept_name}*\n\n✨ /tasks — завдання\n⭐ /xp — профіль\n🏆 /leaderboard — топ\n🎯 /idea — поділись ідеєю",
    },
    
    # ========== TASKS ==========
    "tasks_select_difficulty": {
        "en": "📋 *Select task difficulty:*",
        "ro": "📋 *Selectează dificultatea sarcinilor:*",
        "uk": "📋 *Вибери складність завдань:*",
    },
    
    "tasks_easy_btn": {
        "en": "📗 Easy",
        "ro": "📗 Ușor",
        "uk": "📗 Легкі",
    },
    
    "tasks_medium_btn": {
        "en": "📙 Medium",
        "ro": "📙 Mediu",
        "uk": "📙 Середні",
    },
    
    "tasks_hard_btn": {
        "en": "📕 Hard",
        "ro": "📕 Dificil",
        "uk": "📕 Важкі",
    },
    
    "tasks_category_header": {
        "en": "📋 *{difficulty} tasks*\n\nThese are tasks for your department.",
        "ro": "📋 *Sarcini {difficulty}*\n\nAcestea sunt sarcini pentru departamentul tău.",
        "uk": "📋 *{difficulty} завдання*\n\nЦе завдання для твого департаменту.",
    },
    
    "tasks_none": {
        "en": "😕 Sorry, no tasks of this difficulty level yet.\n\nTry another level!",
        "ro": "😕 Ne pare rău, deocamdată nu sunt sarcini de acest nivel de dificultate.\n\nÎncearcă alt nivel!",
        "uk": "😕 На жаль, завдань цього рівня немає.\n\nСпробуй інший рівень!",
    },
    
    "tasks_no_dept": {
        "en": "❌ First select your department. Click /start",
        "ro": "❌ Mai întâi selectează-ți departamentul. Click /start",
        "uk": "❌ Спочатку обери департамент. Напиши /start",
    },
    
    "task_submit_btn": {
        "en": "📤 Submit task",
        "ro": "📤 Trimite sarcina",
        "uk": "📤 Здати завдання",
    },
    
    "task_done_btn": {
        "en": "✅ Completed",
        "ro": "✅ Completat",
        "uk": "✅ Виконано",
    },
    
    "task_pending_btn": {
        "en": "⏳ Under review",
        "ro": "⏳ Sub revizuire",
        "uk": "⏳ На перевірці",
    },
    
    "task_submit_prompt": {
        "en": "📤 *Submitting: {title}*\n\nSend proof of completion:\n• 📸 Screenshot\n• 📝 Or text description\n\n_To cancel — /cancel_",
        "ro": "📤 *Trimitere: {title}*\n\nTrimite dovada finalizării:\n• 📸 Captură de ecran\n• 📝 Sau descriere text\n\n_Pentru a anula — /cancel_",
        "uk": "📤 *Здача: {title}*\n\nНадішли підтвердження виконання:\n• 📸 Скріншот\n• 📝 Або текстовий опис\n\n_Щоб скасувати — /cancel_",
    },
    
    "task_already_done": {
        "en": "✅ You've already completed this task!",
        "ro": "✅ Ai deja completat această sarcină!",
        "uk": "✅ Ти вже виконав це завдання!",
    },
    
    "task_already_pending": {
        "en": "⏳ Your answer is already under review!",
        "ro": "⏳ Răspunsul tău este deja sub revizuire!",
        "uk": "⏳ Твоя відповідь вже на перевірці!",
    },
    
    "task_submitted": {
        "en": "✅ *Submitted for review!*\n\n«{title}» — admin will check soon. ⏳",
        "ro": "✅ *Trimis pentru revizuire!*\n\n«{title}» — adminul va verifica în curând. ⏳",
        "uk": "✅ *Здано на перевірку!*\n\n«{title}» — адмін перевірить найближчим часом. ⏳",
    },
    
    "task_no_proof": {
        "en": "❌ Send text or an image.",
        "ro": "❌ Trimite text sau o imagine.",
        "uk": "❌ Надішли текст або зображення.",
    },
    
    "task_approved": {
        "en": "🎉 *Task verified!*\n\n✅ «{title}» — completed!\n💎 +{xp} XP earned!\n\nCheck your profile: /xp",
        "ro": "🎉 *Sarcină verificată!*\n\n✅ «{title}» — finalizată!\n💎 +{xp} XP câștigați!\n\nVerifică-ți profilul: /xp",
        "uk": "🎉 *Завдання підтверджено!*\n\n✅ «{title}» — зараховано!\n💎 +{xp} XP нараховано!\n\nПереглянь профіль: /xp",
    },
    
    "task_rejected": {
        "en": "❌ *Task rejected*\n\n«{title}» — not accepted.\nTry again! /tasks",
        "ro": "❌ *Sarcină respinsă*\n\n«{title}» — neacceptată.\nÎncearcă din nou! /tasks",
        "uk": "❌ *Завдання не прийнято*\n\n«{title}» — відхилено.\nСпробуй ще раз! /tasks",
    },
    
    # ========== PROFILE & LEADERBOARD ==========
    "profile_header": {
        "en": "👤 *Your profile {first_name}*\n\n🏆 Total XP (Leaderboard): *{total_xp} XP*\n💰 Available for spending (Shop): *{spendable_xp} XP*\n📊 Rank: *#{rank}* of {total}",
        "ro": "👤 *Profilul tău {first_name}*\n\n🏆 XP total (Clasament): *{total_xp} XP*\n💰 Disponibil pentru cheltuire (Magazin): *{spendable_xp} XP*\n📊 Rang: *#{rank}* din {total}",
        "uk": "👤 *Твій профіль {first_name}*\n\n🏆 Загальний рейтинг (Leaderboard): *{total_xp} XP*\n💰 Доступно для витрат у Магазині: *{spendable_xp} XP*\n📊 Місце: *#{rank}* з {total}",
    },
    
    "leaderboard_header": {
        "en": "🏆 *Leaderboard* (cumulative XP)\n",
        "ro": "🏆 *Clasament* (XP cumulative)\n",
        "uk": "🏆 *Таблиця лідерів* (кумулятивний XP)\n",
    },
    
    "leaderboard_empty": {
        "en": "🏆 Leaderboard is empty. Be the first!",
        "ro": "🏆 Clasamentul este gol. Fii primul!",
        "uk": "🏆 Таблиця порожня. Будь першим!",
    },
    
    "leaderboard_medals": {
        "en": ["🥇", "🥈", "🥉"],
        "ro": ["🥇", "🥈", "🥉"],
        "uk": ["🥇", "🥈", "🥉"],
    },
    
    # ========== SHOP & INVENTORY ==========
    "shop_placeholder": {
        "en": "🚧 *Shop is under construction!*\n\n🐿 I'm laying out our best nuts, merchandise and other goodies on the shelves.\n\n⏳ Check back soon, and in the meantime keep farming XP! 🌰",
        "ro": "🚧 *Magazinul este în construcție!*\n\n🐿 Pun pe raft cel mai bun alune, mărfuri și alte bunătăți.\n\n⏳ Revino curând, și între timp continuă să faci XP! 🌰",
        "uk": "🚧 *Магазин ще в процесі!*\n\n🐿 Я якраз розкладаю наші найкращі горішки, мерч та інші ніштяки по поличках.\n\n⏳ Зазирни сюди трохи згодом, а поки продовжуй фармити XP! 🌰",
    },
    
    "inventory_placeholder": {
        "en": "🚧 *Inventory is under construction!*\n\n📦 Soon here will be all your purchases and donations!\n\n⏳ For now keep collecting XP in /tasks 🐿",
        "ro": "🚧 *Inventarul este în construcție!*\n\n📦 Curând aici vor fi toate achizițiile și donațiile tale!\n\n⏳ Deocamdată continuă să strângi XP în /tasks 🐿",
        "uk": "🚧 *Інвентар ще в процесі!*\n\n📦 Скоро тут будуть усі твої покупки та донати!\n\n⏳ Поки що продовжуй збирати XP в /tasks 🐿",
    },
    
    # ========== ACHIEVEMENTS ==========
    "achievements_placeholder": {
        "en": "🏆 *Hall of Fame coming soon!*\n\n✨ Soon here will be your unique badges and achievements for hard work in ATUR.\n\n💎 In the meantime, I'm polishing them to perfection ✨",
        "ro": "🏆 *Sala Faimei vine curând!*\n\n✨ Curând aici vor fi insignele și realizările tale unice pentru munca grea în ATUR.\n\n💎 Între timp, le lustresc la perfecțiune ✨",
        "uk": "🏆 *Стіна Слави готується!*\n\n✨ Скоро тут з'являться твої унікальні бейджі та ачівки за розривну роботу в ATUR.\n\n💎 Поки що я ретельно полірую їх до блиску ✨",
    },
    
    # ========== IDEAS ==========
    "idea_prompt": {
        "en": "💡 *Share your idea!*\n\nHow would you like to see ATUR? What can be improved?\n\n_Just type your idea below (or /cancel to skip)_",
        "ro": "💡 *Partajează-ți ideea!*\n\nCum ai dori să vezi ATUR? Ce se poate îmbunătăți?\n\n_Doar tastează ideea ta mai jos (sau /cancel pentru a sări)_",
        "uk": "💡 *Ось, поділись своєю ідеєю!*\n\nЯк би ти хотів/а, щоб ATUR розвивався? Що можна покращити?\n\n_Просто напиши свою ідею нижче (або /cancel щоб пропустити)_",
    },
    
    "idea_empty": {
        "en": "❌ Idea can't be empty. Try again!",
        "ro": "❌ Ideea nu poate fi goală. Încearcă din nou!",
        "uk": "❌ Ідея не може бути порожною. Спробуй ще раз!",
    },
    
    "idea_anonymity_ask": {
        "en": "Would you like to share this idea anonymously or with your name?",
        "ro": "Doriți să partajați această idee anonim sau cu numele vostru?",
        "uk": "Надіслати ідею анонімно чи від свого імені?",
    },
    
    "idea_btn_named": {
        "en": "👤 With my name",
        "ro": "👤 Cu numele meu",
        "uk": "👤 Від мого імені",
    },
    
    "idea_btn_anon": {
        "en": "🕵️ Anonymously",
        "ro": "🕵️ Anonim",
        "uk": "🕵️ Анонімно",
    },
    
    "idea_submitted": {
        "en": "✅ *Thanks!* 🐿️\n\nI'm already forwarding your idea to the admins — they'll definitely check it out!",
        "ro": "✅ *Mulțumesc!* 🐿️\n\nDeja trimit ideea ta administratorilor — o vor citi cu siguranță!",
        "uk": "✅ *Дякую!* 🐿️\n\nЯ вже передаю твою ідею адмінам — вони обов'язково її розглянуть!",
    },
    
    # ========== HELP ==========
    "help_text": {
        "en": "📖 *How it works:*\n\n1) View tasks: /tasks\n2) Complete a task\n3) Click «📤 Submit task»\n4) Send proof (screenshot or text)\n5) Admin will check and award XP\n\nTo cancel: /cancel",
        "ro": "📖 *Cum funcționează:*\n\n1) Vizualizează sarcinile: /tasks\n2) Completează o sarcină\n3) Apasă «📤 Trimite sarcina»\n4) Trimite dovada (captură sau text)\n5) Adminul va verifica și va acorda XP\n\nPentru a anula: /cancel",
        "uk": "📖 *Як це працює:*\n\n1) Переглянь завдання: /tasks\n2) Виконай завдання\n3) Натисни «📤 Здати завдання»\n4) Надішли підтвердження (скріншот або текст)\n5) Адмін перевірить і нарахує XP\n\nЩоб скасувати: /cancel",
    },
    
    # ========== ERRORS & NOTIFICATIONS ==========
    "not_subscribed_reminder": {
        "en": "ℹ️ We noticed you're not subscribed to our channel!\n\n📱 Subscribe to @aturinfo to stay updated.\n\nBut you can continue working 😊",
        "ro": "ℹ️ Am observat că nu ești abonat la canalul nostru!\n\n📱 Abonează-te la @aturinfo pentru a rămâne actualizat.\n\nDar poți continua să lucrezi 😊",
        "uk": "ℹ️ Помітили, що ти не підписаний на наш канал!\n\n📱 Підпишись на @aturinfo, щоб не пропустити важливе.\n\nАле можеш продовжити роботити 😊",
    },
    
    "rate_limit": {
        "en": "Too many requests. Try again in a few seconds.",
        "ro": "Prea multe cereri. Încearcă din nou în câteva secunde.",
        "uk": "Забагато запитів. Спробуй ще раз через кілька секунд.",
    },
    
    "banned": {
        "en": "❌ Access denied. Contact admin.",
        "ro": "❌ Acces refuzat. Contactează adminul.",
        "uk": "❌ Доступ обмежено. Напиши адміну.",
    },
    
    "admin_only": {
        "en": "❌ Admin only!",
        "ro": "❌ Doar pentru admini!",
        "uk": "❌ Тільки для адміністраторів!",
    },
    
    "cancel_no_action": {
        "en": "No active action to cancel.",
        "ro": "Nicio acțiune activă de anulat.",
        "uk": "Немає активної дії для скасування.",
    },
    
    "cancel_success": {
        "en": "❌ Current action cancelled.",
        "ro": "❌ Acțiunea curentă anulată.",
        "uk": "❌ Поточну дію скасовано.",
    },
}


def get_message(key: str, lang: str, **kwargs) -> str:
    """
    Get a message in the specified language.
    
    Args:
        key: Message key (e.g., "lang_select", "tasks_submit_btn")
        lang: Language code (en, ro, uk)
        **kwargs: Format variables (e.g., first_name="John", xp=100)
    
    Returns:
        Formatted message string in the specified language.
        Falls back to English if language not found.
    """
    if key not in MESSAGES:
        return f"[Missing message: {key}]"
    
    msg_dict = MESSAGES[key]
    
    # Get message in requested language, fallback to English
    msg = msg_dict.get(lang, msg_dict.get("en", f"[Missing: {key}/{lang}]"))
    
    # Format with provided variables
    try:
        return msg.format(**kwargs)
    except (KeyError, ValueError) as e:
        logger.warning(f"Failed to format message {key}: {e}")
        return msg
