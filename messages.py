"""Multi-language message system for xp-bot"""

import logging

logger = logging.getLogger(__name__)

# All messages in 3 languages: English (en), Romanian (ro), Ukrainian (uk)
MESSAGES = {
    # ========== STARTUP FLOW ==========
    "lang_select": {
        "en": "🌍 *Select language / Selectează limba / Виберіть мову:*",
        "ro": "🌍 *Select language / Selectează limba / Виберіть мову:*",
        "uk": "🌍 *Обери мову:*",
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
        "uk": "✅ *Дякую! Ти підписаний* 🎉\n\nТепер обери свій департамент:",
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
        "en": "✅ *Departments saved!*\n\n🏢 Your departments:\n{depts}\n\nYou can now start completing tasks!\n\nUse /menu to see all commands or /start to change departments.",
        "ro": "✅ *Departamente salvate!*\n\n🏢 Departamentele tale:\n{depts}\n\nPoți acum să completezi sarcini!\n\nFoloseşte /menu pentru comenzi sau /start pentru a schimba departamentele.",
        "uk": "✅ *Департаменти збережені!*\n\n🏢 Твої департаменти:\n{depts}\n\nТепер можеш виконувати завдання!\n\nНапиши /menu для команд або /start щоб змінити департаменти.",
    },

    "dept_btn_done": {
        "en": "✅ Done",
        "ro": "✅ Gata",
        "uk": "✅ Готово",
    },

    "dept_btn_change": {
        "en": "🏢 Change Departments",
        "ro": "🏢 Schimbă Departamentele",
        "uk": "🏢 Змінити департаменти",
    },

    "dept_manage_btn": {
        "en": "🏢 Manage Departments",
        "ro": "🏢 Gestionează Departamentele",
        "uk": "🏢 Керувати департаментами",
    },

    "dept_manage_prompt": {
        "en": "🏢 *Your departments:*\n\nClick ❌ to leave, or ➕ to add more.",
        "ro": "🏢 *Departamentele tale:*\n\nFă clic pe ❌ pentru a ieși, sau ➕ pentru a adăuga.",
        "uk": "🏢 *Твої департаменти:*\n\nНатисни ❌ щоб покинути, або ➕ за додаванням.",
    },

    "dept_leave_btn": {
        "en": "❌ Leave",
        "ro": "❌ Ieși",
        "uk": "❌ Вийти",
    },

    "dept_add_more_prompt": {
        "en": "🏢 *Add more departments:*\n\nSelect departments to add",
        "ro": "🏢 *Adaugă mai multe departamente:*\n\nSelectează departamentele",
        "uk": "🏢 *Додати ще департаменти:*\n\nОбери департаменти",
    },

    "dept_add_more_btn": {
        "en": "➕ Add More",
        "ro": "➕ Adaugă Mai Mult",
        "uk": "➕ Додати Ще",
    },

    "dept_updated": {
        "en": "✅ *Departments updated!*\n\n🏢 Your departments:\n{depts}",
        "ro": "✅ *Departamente actualizate!*\n\n🏢 Departamentele tale:\n{depts}",
        "uk": "✅ *Департаменти оновлені!*\n\n🏢 Твої департаменти:\n{depts}",
    },

    "menu_prompt": {
        "en": "📋 *Main Menu*\n\n✨ /tasks — view tasks\n⭐ /info — your profile\n🏆 /leaderboard — leaderboard\n⚙️ /settings — change department & language\n❓ /help — help & commands\nℹ️ /about — about the bot\n🎯 /idea — share an idea",
        "ro": "📋 *Meniu Principal*\n\n✨ /tasks — vizualizare sarcini\n⭐ /info — profilul tău\n🏆 /leaderboard — clasament\n⚙️ /settings — schimbă departamentul și limbă\n❓ /help — ajutor și comenzi\nℹ️ /about — despre bot\n🎯 /idea — partajează o idee",
        "uk": "📋 *Головне меню*\n\n✨ /tasks — завдання\n⭐ /info — твій профіль\n🏆 /leaderboard — топ\n⚙️ /settings — змінити департамент & мову\n❓ /help — допомога і команди\nℹ️ /about — про бота\n🎯 /idea — поділись ідеєю",
    },

    "welcome_multi_returning": {
        "en": "👋 *Welcome back, {first_name}!*\n\n🏢 Your departments:\n{depts}\n\n✨ /tasks — tasks\n⭐ /info — profile\n🏆 /leaderboard — leaderboard\n⚙️ /settings — change department & language\n❓ /help — help\nℹ️ /about — about bot\n🎯 /idea — share an idea",
        "ro": "👋 *Bine ai revenit, {first_name}!*\n\n🏢 Departamentele tale:\n{depts}\n\n✨ /tasks — sarcini\n⭐ /info — profil\n🏆 /leaderboard — clasament\n⚙️ /settings — schimbă departamentul și limbă\n❓ /help — ajutor\nℹ️ /about — despre bot\n🎯 /idea — partajează o idee",
        "uk": "👋 *Привіт знову, {first_name}!*\n\n🏢 Твої департаменти:\n{depts}\n\n✨ /tasks — завдання\n⭐ /info — профіль\n🏆 /leaderboard — топ\n⚙️ /settings — змінити департамент & мову\n❓ /help — допомога\nℹ️ /about — про бота\n🎯 /idea — поділись ідеєю",
    },

    "dept_welcome": {
        "en": "✅ *Great, {first_name}!*\n\n🐿 Welcome to ATUR! I'm Білка Валерій!\n\nYou're in department: *{emoji} {dept_name}*\n\nNow you can start completing tasks!\n\n✨ /tasks — task list\n⭐ /info — your profile\n🏆 /leaderboard — top players\n⚙️ /settings — change department & language",
        "ro": "✅ *Grozav, {first_name}!*\n\n🐿 Bine ai venit la ATUR! Sunt Білка Валерій!\n\nEști în departamentul: *{emoji} {dept_name}*\n\nAcum poți începe să completezi sarcini!\n\n✨ /tasks — lista sarcinilor\n⭐ /info — profilul tău\n🏆 /leaderboard — top jucători\n⚙️ /settings — schimbă departamentul și limbă",
        "uk": "✅ *Чудово, {first_name}!*\n\n🐿 Ласкаво просимо до ATUR! Я Білка Валерій!\n\nТи в департаменті: *{emoji} {dept_name}*\n\nТепер можеш розпочати виконувати завдання!\n\n✨ /tasks — список завдань\n⭐ /info — твій профіль\n🏆 /leaderboard — топ гравців\n⚙️ /settings — змінити департамент & мову",
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
        "en": "📤 *Submitting: {title}*\n\nSend proof of completion:\n• 📸 Screenshot\n• 📝 Or text description",
        "ro": "📤 *Trimitere: {title}*\n\nTrimite dovada finalizării:\n• 📸 Captură de ecran\n• 📝 Sau descriere text",
        "uk": "📤 *Здача: {title}*\n\nНадішли підтвердження виконання:\n• 📸 Скріншот\n• 📝 Або текстовий опис",
    },
    
    "cancel_btn": {
        "en": "❌ Cancel",
        "ro": "❌ Anulare",
        "uk": "❌ Скасувати",
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
    
    # ========== ADMIN/ERROR MESSAGES ==========
    "user_not_found": {
        "en": "❌ Error: user not found. Try /start",
        "ro": "❌ Eroare: utilizatorul nu a fost găsit. Încearcă /start",
        "uk": "❌ Помилка: користувач не знайдено. Спробуй /start",
    },
    
    "dept_required": {
        "en": "❌ First select your department. Click /start",
        "ro": "❌ Mai întâi selectează-ți departamentul. Click /start",
        "uk": "❌ Спочатку обери департамент через /start",
    },
    
    "no_proof": {
        "en": "❌ Send text or an image.",
        "ro": "❌ Trimite text sau o imagine.",
        "uk": "❌ Надішли текст або зображення.",
    },
    
    "task_not_found": {
        "en": "❌ Task not found. /tasks",
        "ro": "❌ Sarcina nu a fost găsită. /tasks",
        "uk": "❌ Завдання не знайдено. /tasks",
    },
    
    "format_addproduct": {
        "en": "❌ Format: /addproduct <price> <name> <description>",
        "ro": "❌ Format: /addproduct <preț> <nume> <descriere>",
        "uk": "❌ Формат: /addproduct <ціна> <назва> <опис>",
    },
    
    "format_deltask": {
        "en": "❌ Format: /deltask <task_id>",
        "ro": "❌ Format: /deltask <task_id>",
        "uk": "❌ Формат: /deltask <task_id>",
    },
    
    "format_editproduct": {
        "en": "❌ Format: /editproduct <product_id> <price> <name> <description>",
        "ro": "❌ Format: /editproduct <product_id> <preț> <nume> <descriere>",
        "uk": "❌ Формат: /editproduct <product_id> <ціна> <назва> <опис>",
    },
    
    "format_givexp": {
        "en": "❌ Format: /givexp <user_id> <amount>",
        "ro": "❌ Format: /givexp <user_id> <cantitate>",
        "uk": "❌ Формат: /givexp <user_id> <кількість>",
    },
    
    "product_added": {
        "en": "✅ Product #{product_id} added: {name} ({price} XP)",
        "ro": "✅ Produs #{product_id} adăugat: {name} ({price} XP)",
        "uk": "✅ Товар #{product_id} додано: {name} ({price} XP)",
    },
    
    "product_deleted": {
        "en": "✅ Product #{product_id} deleted.",
        "ro": "✅ Produs #{product_id} șters.",
        "uk": "✅ Товар #{product_id} видалено.",
    },
    
    "product_updated": {
        "en": "✅ Product #{product_id} updated: {name} ({price} XP)",
        "ro": "✅ Produs #{product_id} actualizat: {name} ({price} XP)",
        "uk": "✅ Товар #{product_id} оновлено: {name} ({price} XP)",
    },
    
    "task_added": {
        "en": "✅ Task #{task_id} added!\n📌 {title}\n💎 {xp} XP",
        "ro": "✅ Sarcina #{task_id} adăugată!\n📌 {title}\n💎 {xp} XP",
        "uk": "✅ Завдання #{task_id} додано!\n📌 {title}\n💎 {xp} XP",
    },
    
    "task_deleted": {
        "en": "✅ Task #{task_id} deactivated.",
        "ro": "✅ Sarcina #{task_id} dezactivată.",
        "uk": "✅ Завдання #{task_id} деактивовано.",
    },
    
    "xp_given": {
        "en": "✅ Awarded {amount} XP → {user_id}",
        "ro": "✅ Acordat {amount} XP → {user_id}",
        "uk": "✅ Нараховано {amount} XP → {user_id}",
    },
    
    "xp_removed": {
        "en": "✅ Removed {amount} XP → {user_id}",
        "ro": "✅ Eliminat {amount} XP → {user_id}",
        "uk": "✅ Знято {amount} XP → {user_id}",
    },
    
    "bot_infoedit": {
        "en": "🧩 *Bot Information Editor*",
        "ro": "🧩 *Editor Informații Bot*",
        "uk": "🧩 *Редактор інформації бота*",
    },
    
    # ========== USER PROFILE & INFO ==========
    "info_header": {
        "en": "👤 *My profile*",
        "ro": "👤 *Profilul meu*",
        "uk": "👤 *Мій профіль*",
    },
    
    "info_id": {
        "en": "🆔 ID",
        "ro": "🆔 ID",
        "uk": "🆔 ID",
    },
    
    "info_name": {
        "en": "📝 Name",
        "ro": "📝 Nume",
        "uk": "📝 Ім'я",
    },
    
    "info_username": {
        "en": "🔗 Username",
        "ro": "🔗 Utilizator",
        "uk": "🔗 Користувач",
    },
    
    "info_registered": {
        "en": "📅 Registered",
        "ro": "📅 Înregistrat",
        "uk": "📅 Дата реєстрації",
    },
    
    "info_verified": {
        "en": "✔️ Verified",
        "ro": "✔️ Verificat",
        "uk": "✔️ Верифіковано",
    },
    
    "info_verified_yes": {
        "en": "Yes",
        "ro": "Da",
        "uk": "Так",
    },
    
    "info_verified_no": {
        "en": "No",
        "ro": "Nu",
        "uk": "Ні",
    },
    
    "info_xp_section": {
        "en": "💎 *XP & Statistics*",
        "ro": "💎 *XP & Statistici*",
        "uk": "💎 *XP & Статистика*",
    },
    
    "info_xp_current": {
        "en": "Current XP",
        "ro": "XP curent",
        "uk": "Поточний XP",
    },
    
    "info_xp_total": {
        "en": "Total earned",
        "ro": "Total câștigat",
        "uk": "Всього заробив",
    },
    
    "info_xp_spent": {
        "en": "Spent",
        "ro": "Cheltuiți",
        "uk": "Витратив",
    },
    
    "info_departments": {
        "en": "🏢 *Departments*",
        "ro": "🏢 *Departamente*",
        "uk": "🏢 *Департаменти*",
    },
    
    "info_none_selected": {
        "en": "Not selected",
        "ro": "Neselecționat",
        "uk": "Не обрано",
    },
    
    # ========== SETTINGS & LANGUAGE ==========
    "settings_header": {
        "en": "⚙️ *Settings*",
        "ro": "⚙️ *Setări*",
        "uk": "⚙️ *Налаштування*",
    },
    
    "settings_prompt": {
        "en": "Select what you want to change:",
        "ro": "Selectează ce vrei să schimbi:",
        "uk": "Виберіть, що хочете змінити:",
    },
    
    "settings_dept_btn": {
        "en": "🏢 Change Department",
        "ro": "🏢 Schimbă Departament",
        "uk": "🏢 Змінити департамент",
    },
    
    "settings_lang_btn": {
        "en": "🌍 Change Language",
        "ro": "🌍 Schimbă Limba",
        "uk": "🌍 Змінити мову",
    },
    
    # ========== LEADERBOARD ==========
    "leaderboard_prompt": {
        "en": "Select which \"table\" you want to view:",
        "ro": "Selectează care \"tabel\" vrei să vezi:",
        "uk": "Виберіть \"яку\" таблицю хочете переглянути:",
    },
    
    "leaderboard_global_btn": {
        "en": "🌍 Global Leaderboard",
        "ro": "🌍 Clasament Global",
        "uk": "🌍 Загальна таблиця",
    },
    
    "leaderboard_department": {
        "en": "📊 {dept}",
        "ro": "📊 {dept}",
        "uk": "📊 {dept}",
    },
    
    # ========== HELP & ABOUT ==========
    "help_header": {
        "en": "📖 *How it works*",
        "ro": "📖 *Cum funcționează*",
        "uk": "📖 *Як це працює*",
    },
    
    "help_content": {
        "en": (
            "1️⃣ View tasks: /tasks\n"
            "2️⃣ Complete task\n"
            "3️⃣ Click «📤 Submit»\n"
            "4️⃣ Send proof (screenshot or text)\n"
            "5️⃣ Admin verifies & awards XP\n\n"
            "📊 Check your rank: /xp\n"
            "🏆 Top volunteers: /leaderboard"
        ),
        "ro": (
            "1️⃣ Vizualizează sarcini: /tasks\n"
            "2️⃣ Finalizează sarcina\n"
            "3️⃣ Apasă «📤 Trimite»\n"
            "4️⃣ Trimite dovadă (captură sau text)\n"
            "5️⃣ Admin verifică și acordă XP\n\n"
            "📊 Verifică-ți rangul: /xp\n"
            "🏆 Top Voluntari: /leaderboard"
        ),
        "uk": (
            "1️⃣ Переглянь завдання: /tasks\n"
            "2️⃣ Виконай завдання\n"
            "3️⃣ Натисни «📤 Здати»\n"
            "4️⃣ Надішли підтвердження (скріншот або текст)\n"
            "5️⃣ Адмін перевірить і нарахує XP\n\n"
            "📊 Переглянь свій рейтинг: /xp\n"
            "🏆 Топ волонтерів: /leaderboard"
        ),
    },

    "support_btn": {
        "en": "📧 Write to developer",
        "ro": "📧 Scrie dezvoltatorului",
        "uk": "📧 Написати розробнику",
    },

    "support_prompt": {
        "en": "✉️ *Write your message to the developer*\n\nDescribe your issue, suggestion, or question.\nReply to this message with your text.",
        "ro": "✉️ *Scrie mesajul tău dezvoltatorului*\n\nDescrie problema, sugestia sau întrebarea ta.\nRăspunde la acest mesaj cu textul tău.",
        "uk": "✉️ *Напиши своє повідомлення розробнику*\n\nОпиши свою проблему, пропозицію або запитання.\nВідповідь цьому повідомленню зі своїм текстом.",
    },

    "support_sent": {
        "en": "✅ *Message sent!*\n\nDeveloper will review your message soon.",
        "ro": "✅ *Mesaj trimis!*\n\nDezvoltatorul va revizui mesajul tău în curând.",
        "uk": "✅ *Повідомлення відправлено!*\n\nРозробник скоро розглянути твоє повідомлення.",
    },

    "support_notification": {
        "en": "📨 *New message from user*\n\n👤 User: {user_name} (ID: {user_id})\n🏢 Department: {department}\n\n💬 Message:\n{message}",
        "ro": "📨 *Mesaj nou de la utilizator*\n\n👤 Utilizator: {user_name} (ID: {user_id})\n🏢 Departament: {department}\n\n💬 Mesaj:\n{message}",
        "uk": "📨 *Нове повідомлення від користувача*\n\n👤 Користувач: {user_name} (ID: {user_id})\n🏢 Департамент: {department}\n\n💬 Повідомлення:\n{message}",
    },

    "about_header": {
        "en": "🤖 *About XP Bot*",
        "ro": "🤖 *Despre XP Bot*",
        "uk": "🤖 *Про XP Bot*",
    },
    
    "about_content": {
        "en": (
            "A bot to motivate your community through an XP system.\n\n"
            "✨ *Features:*\n"
            "• Tasks with rewards\n"
            "• Shop system\n"
            "• Leaderboard\n"
            "• Profile & stats\n\n"
            "🚀 *Getting started:*\n"
            "1. /start — register\n"
            "2. /tasks — view tasks\n"
            "3. /leaderboard — top volunteers\n\n"
            "❓ Questions? Contact admin."
        ),
        "ro": (
            "Un bot pentru motivarea comunității prin sistem XP.\n\n"
            "✨ *Funcții:*\n"
            "• Sarcini cu recompense\n"
            "• Sistem magazin\n"
            "• Clasament\n"
            "• Profil & statistici\n\n"
            "🚀 *Primii pași:*\n"
            "1. /start — înregistrare\n"
            "2. /tasks — vizualizează sarcini\n"
            "3. /leaderboard — top voluntari\n\n"
            "❓ Întrebări? Contactează adminul."
        ),
        "uk": (
            "Бот для мотивації спільноти через систему XP.\n\n"
            "✨ *Можливості:*\n"
            "• Завдання з винагородами\n"
            "• Система магазину\n"
            "• Таблиця лідерів\n"
            "• Профіль та статистика\n\n"
            "🚀 *Як почати:*\n"
            "1. /start — реєстрація\n"
            "2. /tasks — список завдань\n"
            "3. /leaderboard — топ волонтерів\n\n"
            "❓ Питання? Зверніться до адміна."
        ),
    },
    
    # ========== ADMIN & SHOP ==========
    "admin_panel_header": {
        "en": "🛠 *Admin Panel*",
        "ro": "🛠 *Panou Admin*",
        "uk": "🛠 *Адмін-панель*",
    },
    
    "admin_add_task_btn": {
        "en": "➕ Add Task",
        "ro": "➕ Adaugă Sarcină",
        "uk": "➕ Додати завдання",
    },
    
    "admin_delete_task_btn": {
        "en": "🗑 Delete Task",
        "ro": "🗑 Șterge Sarcină",
        "uk": "🗑 Видалити завдання",
    },
    
    "admin_users_btn": {
        "en": "👥 Users",
        "ro": "👥 Utilizatori",
        "uk": "👥 Користувачі",
    },
    
    "admin_ideas_btn": {
        "en": "💡 Ideas",
        "ro": "💡 Idei",
        "uk": "💡 Ідеї",
    },
    
    "admin_xp_btn": {
        "en": "🎁 Award XP",
        "ro": "🎁 Acordă XP",
        "uk": "🎁 Нарахувати XP",
    },
    
    "admin_stats_btn": {
        "en": "📊 Statistics",
        "ro": "📊 Statistici",
        "uk": "📊 Статистика",
    },
    
    "admin_shop_btn": {
        "en": "🛒 Shop Items",
        "ro": "🛒 Articole Magazin",
        "uk": "🛒 Товари магазину",
    },
    
    "admin_edit_info_btn": {
        "en": "🧩 Edit Bot Info",
        "ro": "🧩 Editează Info Bot",
        "uk": "🧩 Редагувати інфо бота",
    },
    
    "admin_back_menu": {
        "en": "⬅ Back to Menu",
        "ro": "⬅ Înapoi la Meniu",
        "uk": "⬅ Назад",
    },
    
    "admin_back": {
        "en": "⬅ Back",
        "ro": "⬅ Înapoi",
        "uk": "⬅ Назад",
    },
    
    "admin_all_users_btn": {
        "en": "📊 All Users",
        "ro": "📊 Toți Utilizatorii",
        "uk": "📊 Всі користувачі",
    },
    
    "admin_edit_text_btn": {
        "en": "✍️ Edit welcome /start",
        "ro": "✍️ Editează salut /start",
        "uk": "✍️ Змінити привітання /start",
    },
    
    "admin_edit_help_btn": {
        "en": "✍️ Edit help /help",
        "ro": "✍️ Editează ajutor /help",
        "uk": "✍️ Змінити довідку /help",
    },
    
    "admin_preview_btn": {
        "en": "👁️ Preview texts",
        "ro": "👁️ Previzualizează textele",
        "uk": "👁️ Переглянути тексти",
    },
    
    "admin_botfather_info": {
        "en": "ℹ️ What changes only via BotFather",
        "ro": "ℹ️ Ce se schimbă doar via BotFather",
        "uk": "ℹ️ Що змінюється тільки через BotFather",
    },
    
    "admin_edit_product_btn": {
        "en": "✏️ Edit",
        "ro": "✏️ Editează",
        "uk": "✏️ Ред.",
    },
    
    "admin_anon_user": {
        "en": "🕵️ Anonymous",
        "ro": "🕵️ Anonim",
        "uk": "🕵️ Анонім",
    },
    
    "admin_botfather_limits": {
        "en": (
            "*You can change via this menu:*\n"
            "• /start text\n"
            "• /help text\n\n"
            "*Only via @BotFather:*\n"
            "• bot photo\n"
            "• bot username and name\n"
            "• bot profile description\n"
            "• bot token"
        ),
        "ro": (
            "*Puteți schimba prin acest meniu:*\n"
            "• text /start\n"
            "• text /help\n\n"
            "*Doar prin @BotFather:*\n"
            "• fotografie bot\n"
            "• username și nume bot\n"
            "• descriere profil bot\n"
            "• token bot"
        ),
        "uk": (
            "*Через це меню можна змінити:*\n"
            "• текст /start\n"
            "• текст /help\n\n"
            "*Тільки через @BotFather:*\n"
            "• фото бота\n"
            "• username та ім'я бота\n"
            "• about/description у профілі бота\n"
            "• токен бота"
        ),
    },
    
    # ========== DEPARTMENT & ADMIN FLOW ==========
    "tasks_select_dept": {
        "en": "📌 *Select department:*",
        "ro": "📌 *Selectează departamentul:*",
        "uk": "📌 *Вибери департамент:*",
    },
    
    "tasks_no_dept_alert": {
        "en": "❌ Select your department first via /start",
        "ro": "❌ Selectează mai întâi departamentul tău prin /start",
        "uk": "❌ Обери департамент через /start",
    },
    
    "dept_select_alert": {
        "en": "⚠️ Select at least one department!",
        "ro": "⚠️ Selectează cel puțin un departament!",
        "uk": "⚠️ Вибери хоча б один департамент!",
    },
    
    "user_no_departments": {
        "en": "_User does not belong to any department._",
        "ro": "_Utilizatorul nu aparține unui departament._",
        "uk": "_Користувач не належить до жодного департаменту._",
    },
    
    "user_dept_roles_header": {
        "en": "*Department roles:*",
        "ro": "*Roluri în departamente:*",
        "uk": "*Ролі в департаментах:*",
    },
    
    "user_no_dept_roles": {
        "en": "_No department roles._",
        "ro": "_Nicio rolă în departamente._",
        "uk": "_Немає ролей в департаментах._",
    },
    
    "role_supervisor": {
        "en": "Supervisor",
        "ro": "Supervizor",
        "uk": "Супервайзер",
    },
    
    "role_coordinator": {
        "en": "Coordinator",
        "ro": "Coordonator",
        "uk": "Координатор",
    },
    
    "role_helper": {
        "en": "Helper",
        "ro": "Ajutant",
        "uk": "Хелпер",
    },
    
    "role_member": {
        "en": "Member",
        "ro": "Membru",
        "uk": "Учасник",
    },
    
    "role_unknown": {
        "en": "Unknown",
        "ro": "Necunoscut",
        "uk": "Невідомо",
    },
    
    "admin_edit_task_btn": {
        "en": "✏️ Edit tasks",
        "ro": "✏️ Editează sarcini",
        "uk": "✏️ Редагувати завдання",
    },
    
    "admin_delete_tasks_header": {
        "en": "🗑 *Delete tasks*",
        "ro": "🗑 *Șterge sarcini*",
        "uk": "🗑 *Видалення завдань*",
    },
    
    "admin_delete_tasks_dept_header": {
        "en": "🗑 *Delete tasks ({dept_name})*",
        "ro": "🗑 *Șterge sarcini ({dept_name})*",
        "uk": "🗑 *Видалення завдань ({dept_name})*",
    },
    
    "admin_delete_tasks_instruction": {
        "en": "Click on a task to deactivate it.",
        "ro": "Apasă pe o sarcină pentru a o dezactiva.",
        "uk": "Натисни на завдання для деактивації.",
    },
    
    "admin_users_all_btn": {
        "en": "📊 All users",
        "ro": "📊 Toți utilizatorii",
        "uk": "📊 Всі користувачі",
    },
    
    "admin_users_by_dept_label": {
        "en": "📍 By departments:",
        "ro": "📍 După departamente:",
        "uk": "📍 За департаментами:",
    },
    
    "admin_menu_btn": {
        "en": "⬅ Menu",
        "ro": "⬅ Meniu",
        "uk": "⬅ В меню",
    },
    
    "pagination_prev_btn": {
        "en": "◀ Previous",
        "ro": "◀ Anterior",
        "uk": "◀ Попередня",
    },
    
    "pagination_next_btn": {
        "en": "Next ▶",
        "ro": "Următor ▶",
        "uk": "Наступна ▶",
    },
    
    # ========== ERROR MESSAGES & VALIDATION ==========
    "error_rate_limit": {
        "en": "Too many requests. Try again in a few seconds.",
        "ro": "Prea multe cereri. Încearcă din nou în câteva secunde.",
        "uk": "Забагато запитів. Спробуй ще раз через кілька секунд.",
    },
    
    "error_choice_failed": {
        "en": "❌ Selection failed. Try again.",
        "ro": "❌ Selecția a eșuat. Încearcă din nou.",
        "uk": "❌ Помилка вибору. Спробуй ще раз.",
    },
    
    "error_session_expired": {
        "en": "❌ Session expired. Try /idea again.",
        "ro": "❌ Sesiunea a expirat. Încearcă /idea din nou.",
        "uk": "❌ Сесія експіровала. Спробуй /idea ще раз.",
    },
    
    "tasks_none_for_difficulty": {
        "en": "😕 Sorry, no tasks at this difficulty level yet.\n\nTry another level!",
        "ro": "😕 Ne pare rău, nu sunt sarcini la acest nivel de dificultate.\n\nÎncearcă un alt nivel!",
        "uk": "😕 На жаль, завдань цього рівня немає.\n\nСпробуй інший рівень!",
    },
    
    "error_xp_calculation": {
        "en": "⚠️ Error calculating XP. Try again.",
        "ro": "⚠️ Eroare la calcularea XP. Încearcă din nou.",
        "uk": "⚠️ Помилка при нарахуванні XP. Спробуй ще раз.",
    },
    
    "error_submission_failed": {
        "en": "Try again! /tasks",
        "ro": "Încearcă din nou! /tasks",
        "uk": "Спробуй ще раз! /tasks",
    },
    
    "error_empty_message": {
        "en": "❌ Message cannot be empty. Try again:",
        "ro": "❌ Mesajul nu poate fi gol. Încearcă din nou:",
        "uk": "❌ Повідомлення не може бути порожнім. Спробуй ще раз:",
    },
    
    "error_send_failed": {
        "en": "❌ Send error. Try later.",
        "ro": "❌ Eroare la trimitere. Încearcă mai târziu.",
        "uk": "❌ Помилка при відправці. Спробуй пізніше.",
    },
    
    "error_xp_must_be_number": {
        "en": "❌ XP must be a whole number > 0. Try again:",
        "ro": "❌ XP trebuie să fie un număr întreg > 0. Încearcă din nou:",
        "uk": "❌ XP має бути цілим числом > 0. Спробуй ще раз:",
    },
    
    "error_user_id_must_be_number": {
        "en": "❌ User ID must be a number. Try again:",
        "ro": "❌ ID-ul utilizatorului trebuie să fie un număr. Încearcă din nou:",
        "uk": "❌ User ID має бути числом. Спробуй ще раз:",
    },
    
    "error_xp_cannot_be_zero": {
        "en": "❌ XP must be a number and not 0. Try again:",
        "ro": "❌ XP trebuie să fie un număr și nu 0. Încearcă din nou:",
        "uk": "❌ XP має бути числом і не 0. Спробуй ще раз:",
    },
    
    "error_price_must_be_number": {
        "en": "❌ Price must be a whole number > 0. Try again:",
        "ro": "❌ Prețul trebuie să fie un număr întreg > 0. Încearcă din nou:",
        "uk": "❌ Ціна має бути цілим числом > 0. Спробуй ще раз:",
    },
    
    "error_price_invalid_decimal": {
        "en": "❌ Price must be a whole number > 0 or '.'. Try again:",
        "ro": "❌ Prețul trebuie să fie un număr întreg > 0 sau '.'. Încearcă din nou:",
        "uk": "❌ Ціна має бути цілим числом > 0 або «.». Спробуй ще раз:",
    },
    
    "error_text_cannot_be_empty": {
        "en": "❌ Text cannot be empty. Try again:",
        "ro": "❌ Textul nu poate fi gol. Încearcă din nou:",
        "uk": "❌ Текст не може бути порожнім. Спробуй ще раз:",
    },
    
    "error_generic": {
        "en": "Something went wrong. Try again or write /help for help.",
        "ro": "Ceva nu a funcționat. Încearcă din nou sau scrie /help pentru ajutor.",
        "uk": "Щось пішло не так. Спробуй ще раз або напиши /help для довідки.",
    },
    
    "back_btn": {
        "en": "⬅ Back",
        "ro": "⬅ Înapoi",
        "uk": "⬅ Назад",
    },
    
    # ========== DEPARTMENT NAMES (TRANSLATED) ==========
    "dept_name_1": {
        "en": "Social Media & Media",
        "ro": "Rețelele Sociale și Media",
        "uk": "SMM та Медіа",
    },
    
    "dept_name_2": {
        "en": "Finance",
        "ro": "Finanțe",
        "uk": "Фінанси",
    },
    
    "dept_name_3": {
        "en": "Project Management",
        "ro": "Gestionarea Proiectelor",
        "uk": "Project Management",
    },
    
    "dept_name_4": {
        "en": "Communication",
        "ro": "Comunicare",
        "uk": "Комунікація",
    },
    
    "dept_name_5": {
        "en": "IT",
        "ro": "IT",
        "uk": "IT",
    },
}


def get_dept_name_translated(dept_id: int, lang: str) -> str:
    """Get translated department name by department ID and language."""
    key = f"dept_name_{dept_id}"
    return get_message(key, lang)


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
