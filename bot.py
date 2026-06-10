import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from config import BOT_TOKEN, ADMIN_ID, PAYMENT_DETAILS, PRICE_PER_DESCRIPTION, DISCOUNT_PACKAGE_SIZE, DISCOUNT_PERCENT
from database import init_db, get_or_create_user, get_balance, add_balance, deduct_balance, save_generation, get_history, add_favorite, get_favorites, remove_favorite
from yandex_gpt import generate_description

# Настройка логирования — чтобы видеть, что происходит в консоли
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Состояния диалога (FSM — Finite State Machine)
PLATFORM, TONE, CATEGORY, CHARACTERISTICS, AUDIENCE, ADVANTAGES, KEYWORDS = range(7)

# Хранилище данных пользователя на время диалога
user_data_store = {}

# Хранилище данных последней генерации для кнопки «Другой вариант»
last_generation_data = {}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start — приветствие, регистрация, показ меню."""
    user = update.effective_user
    db_user = get_or_create_user(user.id, user.username, user.first_name)
    balance = db_user[3]

    low_balance_text = ""
    if balance <= 2 and balance > 0:
        low_balance_text = (
            f"⚠️ Внимание: у вас осталось {balance} описаний. "
            f"Рекомендуем пополнить баланс заранее.\n\n"
        )

    text = (
        f"Привет, {user.first_name}! 👋\n\n"
        "Я бот для генерации описаний товаров.\n"
        "Выберите площадку, расскажите о товаре — и я подготовлю готовый текст.\n\n"
        f"💰 Ваш баланс: {balance} описаний\n\n"
        + low_balance_text +
        "Чтобы начать, нажмите кнопку ниже.\n"
        "Нужна помощь? Отправьте /help"
    )

    keyboard = [
        [InlineKeyboardButton("📝 Создать описание", callback_data="new")],
        [InlineKeyboardButton("💳 Пополнить баланс", callback_data="pay")],
        [InlineKeyboardButton("👤 Мой профиль", callback_data="profile")],
        [InlineKeyboardButton("📜 История", callback_data="history"), InlineKeyboardButton("⭐ Избранное", callback_data="favorites")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(text, reply_markup=reply_markup)


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает нажатия на кнопки."""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id

    if query.data == "new":
        # Проверяем баланс
        balance = get_balance(user_id)
        if balance <= 0:
            keyboard = [
                [InlineKeyboardButton("💳 Пополнить баланс", callback_data="pay")],
                [InlineKeyboardButton("🔙 В меню", callback_data="menu")],
            ]
            await query.edit_message_text(
                "❌ У вас закончились описания.\n\n"
                "Нажмите кнопку ниже для пополнения:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return

        # Предупреждение о низком балансе
        low_balance_warning = ""
        if balance <= 2:
            low_balance_warning = (
                f"⚠️ Внимание: у вас осталось {balance} описаний.\n"
                f"Рекомендуем пополнить баланс заранее.\n\n"
            )

        # Начинаем диалог
        keyboard = [
            [InlineKeyboardButton("Wildberries", callback_data="wb"),
             InlineKeyboardButton("Ozon", callback_data="ozon")],
            [InlineKeyboardButton("Яндекс.Маркет", callback_data="yandex"),
             InlineKeyboardButton("Авито", callback_data="avito")],
            [InlineKeyboardButton("Свой сайт", callback_data="ownsite")],
        ]
        await query.edit_message_text(
            low_balance_warning + "Выберите площадку:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return PLATFORM

    elif query.data == "pay":
        keyboard = [
            [InlineKeyboardButton("✅ Я оплатил", callback_data="paid")],
            [InlineKeyboardButton("🔙 В меню", callback_data="menu")],
        ]

        # Рассчитываем цену пакета со скидкой
        discount_amount = (DISCOUNT_PACKAGE_SIZE * PRICE_PER_DESCRIPTION * DISCOUNT_PERCENT) // 100
        discount_price = DISCOUNT_PACKAGE_SIZE * PRICE_PER_DESCRIPTION - discount_amount

        await query.edit_message_text(
            f"💳 Пополнение баланса\n\n"
            f"💰 Стоимость: 1 описание = {PRICE_PER_DESCRIPTION} ₽\n\n"
            f"📦 Рекомендуемые пакеты:\n"
            f"• 5 описаний = {5 * PRICE_PER_DESCRIPTION} ₽\n"
            f"• 10 описаний = {10 * PRICE_PER_DESCRIPTION} ₽\n"
            f"• {DISCOUNT_PACKAGE_SIZE} описаний = ~~{DISCOUNT_PACKAGE_SIZE * PRICE_PER_DESCRIPTION} ₽~~ → {discount_price} ₽ (экономия {discount_amount} ₽, скидка {DISCOUNT_PERCENT}%)\n\n"
            f"{PAYMENT_DETAILS}\n\n"
            f"После перевода нажмите «Я оплатил» — администратор получит уведомление и начислит описания.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif query.data == "paid":
        # Уведомляем администратора
        user = update.effective_user
        # Рассчитываем цену пакета со скидкой для уведомления
        discount_amount = (DISCOUNT_PACKAGE_SIZE * PRICE_PER_DESCRIPTION * DISCOUNT_PERCENT) // 100
        discount_price = DISCOUNT_PACKAGE_SIZE * PRICE_PER_DESCRIPTION - discount_amount
        try:
            await context.bot.send_message(
                chat_id=int(ADMIN_ID),
                text=(
                    f"💰 Новый запрос на пополнение!\n\n"
                    f"Пользователь: {user.first_name} (@{user.username or 'нет username'})\n"
                    f"ID: {user.id}\n\n"
                    f"💵 Прайс:\n"
                    f"• 1 описание = {PRICE_PER_DESCRIPTION} ₽\n"
                    f"• 5 описаний = {5 * PRICE_PER_DESCRIPTION} ₽\n"
                    f"• 10 описаний = {10 * PRICE_PER_DESCRIPTION} ₽\n"
                    f"• {DISCOUNT_PACKAGE_SIZE} описаний = {discount_price} ₽ (скидка {DISCOUNT_PERCENT}%)\n\n"
                    f"Проверьте поступление средств и начислите баланс.\n\n"
                    f"Для начисления отправьте в бот:\n"
                    f"/add_balance {user.id} <количество>\n\n"
                    f"Например: /add_balance {user.id} 5"
                )
            )
        except Exception as e:
            logger.error(f"Не удалось отправить уведомление админу: {e}")

        await query.edit_message_text(
            "✅ Уведомление отправлено администратору.\n"
            "После подтверждения оплаты баланс будет начислен.\n\n"
            "Чтобы вернуться в меню, отправьте /start"
        )

    elif query.data == "menu":
        # Возврат в главное меню через имитацию /start
        user = update.effective_user
        db_user = get_or_create_user(user.id, user.username, user.first_name)
        balance = db_user[3]
        text = (
            f"Привет, {user.first_name}! 👋\n\n"
            "Я бот для генерации описаний товаров.\n"
            "Выберите площадку, расскажите о товаре — и я подготовлю готовый текст.\n\n"
            f"💰 Ваш баланс: {balance} описаний\n\n"
            "Чтобы начать, нажмите кнопку ниже."
        )
        keyboard = [
            [InlineKeyboardButton("📝 Создать описание", callback_data="new")],
            [InlineKeyboardButton("💳 Пополнить баланс", callback_data="pay")],
            [InlineKeyboardButton("👤 Мой профиль", callback_data="profile")],
            [InlineKeyboardButton("📜 История", callback_data="history"), InlineKeyboardButton("⭐ Избранное", callback_data="favorites")],
        ]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data == "profile":
        user = get_or_create_user(user_id, None, None)
        balance = user[3]
        await query.edit_message_text(
            f"👤 Ваш профиль\n\n"
            f"Имя: {user[2]}\n"
            f"Баланс: {balance} описаний\n\n"
            "Чтобы вернуться в меню, отправьте /start"
        )

    elif query.data == "history":
        history = get_history(user_id)
        if not history:
            text = "📜 История пуста.\n\nОтправьте /start для возврата в меню."
        else:
            text = "📜 Последние генерации:\n\n"
            for i, (platform, category, tone, result, created) in enumerate(history, 1):
                short = result[:100].replace('\n', ' ')
                tone_label = f" | {tone}" if tone else ""
                text += f"{i}. [{platform.upper()}] {category}{tone_label}\n   {short}...\n\n"
            text += "Отправьте /start для возврата в меню."
        await query.edit_message_text(text)

    elif query.data == "favorites":
        favorites = get_favorites(user_id)
        if not favorites:
            text = "⭐ Избранное пусто.\n\nОтправьте /start для возврата в меню."
        else:
            text = "⭐ Избранное:\n\n"
            for i, (platform, category, tone, result, created, fav_id) in enumerate(favorites, 1):
                short = result[:100].replace('\n', ' ')
                tone_label = f" | {tone}" if tone else ""
                text += f"{i}. [{platform.upper()}] {category}{tone_label}\n   {short}...\n\n"
            text += "Отправьте /start для возврата в меню."
        await query.edit_message_text(text)

    elif query.data.startswith("save_fav_"):
        generation_id = int(query.data.split("_")[2])
        add_favorite(user_id, generation_id)
        await query.answer("✅ Сохранено в избранное!")
        # Обновляем кнопку, чтобы не было повторного нажатия
        await query.edit_message_reply_markup(
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Сохранено", callback_data="saved")],
                [InlineKeyboardButton("📝 Создать описание", callback_data="new")],
                [InlineKeyboardButton("💳 Пополнить баланс", callback_data="pay")],
                [InlineKeyboardButton("👤 Мой профиль", callback_data="profile")],
                [InlineKeyboardButton("📜 История", callback_data="history"), InlineKeyboardButton("⭐ Избранное", callback_data="favorites")],
            ])
        )

    elif query.data == "regenerate":
        # Проверяем баланс
        balance = get_balance(user_id)
        if balance <= 0:
            keyboard = [
                [InlineKeyboardButton("💳 Пополнить баланс", callback_data="pay")],
                [InlineKeyboardButton("🔙 В меню", callback_data="menu")],
            ]
            await query.edit_message_text(
                "❌ У вас закончились описания.\n\n"
                "Нажмите кнопку ниже для пополнения:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return

        # Проверяем наличие данных для перегенерации
        data = last_generation_data.get(user_id)
        if not data:
            await query.answer("❌ Нет данных для повторной генерации.")
            return

        await query.answer("⏳ Генерирую другой вариант...")

        # Отправляем сообщение о генерации
        wait_message = await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="⏳ Генерирую описание, подождите несколько секунд..."
        )

        try:
            result = await generate_description(
                platform=data["platform"],
                category=data["category"],
                characteristics=data["characteristics"],
                audience=data["audience"],
                advantages=data["advantages"],
                keywords=data["keywords"],
                tone=data.get("tone")
            )
        except Exception as e:
            logger.exception("Ошибка перегенерации")
            await wait_message.delete()
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text="⚠️ Произошла ошибка при генерации. Попробуйте ещё раз или обратитесь к администратору."
            )
            return

        # Списываем баланс и сохраняем
        deduct_balance(user_id)
        generation_id = save_generation(
            user_id, data["platform"], data["category"], result, data.get("tone")
        )

        await wait_message.delete()
        await context.bot.send_message(chat_id=query.message.chat_id, text=result)

        # Показываем меню с кнопками
        keyboard = [
            [InlineKeyboardButton("⭐ Сохранить в избранное", callback_data=f"save_fav_{generation_id}")],
            [InlineKeyboardButton("🔁 Сгенерировать другой вариант", callback_data="regenerate")],
            [InlineKeyboardButton("📝 Создать описание", callback_data="new")],
            [InlineKeyboardButton("💳 Пополнить баланс", callback_data="pay")],
            [InlineKeyboardButton("👤 Мой профиль", callback_data="profile")],
            [InlineKeyboardButton("📜 История", callback_data="history"), InlineKeyboardButton("⭐ Избранное", callback_data="favorites")],
        ]
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="Готово! Что дальше?",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif query.data == "support":
        user = update.effective_user
        username = user.username
        try:
            # Формируем кликабельные ссылки
            user_link = f'<a href="tg://user?id={user.id}">Написать пользователю</a>'
            if username:
                username_link = f'<a href="https://t.me/{username}">@{username}</a>'
            else:
                username_link = "нет username"

            await context.bot.send_message(
                chat_id=int(ADMIN_ID),
                text=(
                    f"💬 Пользователь хочет связаться с вами!\n\n"
                    f"Имя: {user.first_name}\n"
                    f"Username: {username_link}\n"
                    f"ID: {user.id}\n\n"
                    f"{user_link}"
                ),
                parse_mode="HTML",
                disable_web_page_preview=True
            )
        except Exception as e:
            logger.error(f"Не удалось отправить уведомление админу: {e}")

        keyboard = [
            [InlineKeyboardButton("🔙 В меню", callback_data="menu")],
        ]
        await query.edit_message_text(
            "✅ Уведомление отправлено администратору.\n"
            "Ожидайте ответа в ближайшее время.\n\n"
            "Если срочно — можете написать напрямую, если знаете контакты.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


async def platform_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Пользователь выбрал площадку."""
    query = update.callback_query
    await query.answer()

    platform_map = {
        "wb": "Wildberries",
        "ozon": "Ozon",
        "yandex": "Яндекс.Маркет",
        "avito": "Авито",
        "ownsite": "Свой сайт"
    }
    platform = platform_map.get(query.data, "Wildberries")
    user_id = update.effective_user.id
    user_data_store[user_id] = {"platform": platform}

    keyboard = [
        [InlineKeyboardButton("🎯 Стандартный тон", callback_data="tone_default")],
        [InlineKeyboardButton("✨ Выбрать другой тон", callback_data="tone_custom")],
        [InlineKeyboardButton("❌ Отмена", callback_data="cancel_dialog")],
    ]
    await query.edit_message_text(
        f"✅ Площадка: {platform}\n\n"
        "Выберите тон описания или пропустите этот шаг:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return TONE


async def tone_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Пользователь выбрал тон (или пропустил)."""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id

    if query.data == "tone_custom":
        # Показываем список тонов
        keyboard = [
            [InlineKeyboardButton("🏢 Формальный", callback_data="tone_formal"),
             InlineKeyboardButton("🤝 Дружелюбный", callback_data="tone_friendly")],
            [InlineKeyboardButton("🔥 Агрессивный", callback_data="tone_aggressive"),
             InlineKeyboardButton("😂 Юмористический", callback_data="tone_humorous")],
            [InlineKeyboardButton("🎯 Стандартный тон", callback_data="tone_default")],
            [InlineKeyboardButton("❌ Отмена", callback_data="cancel_dialog")],
        ]
        await query.edit_message_text(
            "Выберите тон описания:\n\n"
            "🏢 <b>Формальный</b> — сухие факты, без эмоций\n"
            "🤝 <b>Дружелюбный</b> — тёплый, разговорный\n"
            "🔥 <b>Агрессивный</b> — акции, срочность, прямой CTA\n"
            "😂 <b>Юмористический</b> — лёгкий, ироничный подход",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
        )
        return TONE

    tone_map = {
        "tone_default": "Стандартный",
        "tone_formal": "Формальный",
        "tone_friendly": "Дружелюбный",
        "tone_aggressive": "Агрессивный",
        "tone_humorous": "Юмористический",
    }
    tone = tone_map.get(query.data, "Стандартный")
    user_data_store[user_id]["tone"] = tone

    keyboard = [
        [InlineKeyboardButton("❌ Отмена", callback_data="cancel_dialog")],
    ]
    await query.edit_message_text(
        f"✅ Площадка: {user_data_store[user_id]['platform']}\n"
        f"✅ Тон: {tone}\n\n"
        "Введите категорию товара (например: «Женские кроссовки», «Ноутбук»):",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return CATEGORY


def cancel_keyboard():
    """Возвращает клавиатуру с кнопкой Отмена для шагов диалога."""
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отмена", callback_data="cancel_dialog")]])


async def category_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получена категория."""
    user_id = update.effective_user.id
    user_data_store[user_id]["category"] = update.message.text

    await update.message.reply_text(
        "Введите ключевые характеристики товара:\n"
        "(материал, размер, цвет, комплектация и т.д.)",
        reply_markup=cancel_keyboard()
    )
    return CHARACTERISTICS


async def characteristics_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получены характеристики."""
    user_id = update.effective_user.id
    user_data_store[user_id]["characteristics"] = update.message.text

    await update.message.reply_text(
        "Кто ваша целевая аудитория?\n"
        "(например: «молодые мамы», «офисные работники», «автолюбители»)",
        reply_markup=cancel_keyboard()
    )
    return AUDIENCE


async def audience_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получена аудитория."""
    user_id = update.effective_user.id
    user_data_store[user_id]["audience"] = update.message.text

    await update.message.reply_text(
        "Какие уникальные преимущества и особенности товара нужно подчеркнуть?",
        reply_markup=cancel_keyboard()
    )
    return ADVANTAGES


async def advantages_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получены преимущества."""
    user_id = update.effective_user.id
    user_data_store[user_id]["advantages"] = update.message.text

    await update.message.reply_text(
        "Введите ключевые слова для SEO (через запятую):\n"
        "Или отправьте «нет», если не нужны.",
        reply_markup=cancel_keyboard()
    )
    return KEYWORDS


async def keywords_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получены ключевые слова. Генерация описания через YandexGPT."""
    user_id = update.effective_user.id
    data = user_data_store[user_id]
    data["keywords"] = update.message.text

    platform = data["platform"]
    category = data["category"]

    # Отправляем сообщение о том, что идёт генерация
    wait_message = await update.message.reply_text("⏳ Генерирую описание, подождите несколько секунд...")

    try:
        result = await generate_description(
            platform=platform,
            category=category,
            characteristics=data["characteristics"],
            audience=data["audience"],
            advantages=data["advantages"],
            keywords=data["keywords"],
            tone=data.get("tone")
        )
    except Exception as e:
        logger.exception("Ошибка генерации")
        await wait_message.delete()

        # Уведомляем администратора о деталях ошибки
        try:
            await context.bot.send_message(
                chat_id=int(ADMIN_ID),
                text=(
                    f"🚨 Ошибка генерации для пользователя {user_id}\n\n"
                    f"Платформа: {platform}\n"
                    f"Категория: {category}\n"
                    f"Ошибка: {e}"
                )
            )
        except Exception as notify_err:
            logger.error(f"Не удалось уведомить админа об ошибке: {notify_err}")

        await update.message.reply_text(
            "⚠️ Произошла ошибка при генерации. Попробуйте ещё раз или обратитесь к администратору."
        )
        keyboard = [
            [InlineKeyboardButton("📝 Создать описание", callback_data="new")],
            [InlineKeyboardButton("💳 Пополнить баланс", callback_data="pay")],
            [InlineKeyboardButton("👤 Мой профиль", callback_data="profile")],
            [InlineKeyboardButton("📜 История", callback_data="history"), InlineKeyboardButton("⭐ Избранное", callback_data="favorites")],
        ]
        await update.message.reply_text(
            "Что дальше?", reply_markup=InlineKeyboardMarkup(keyboard)
        )
        user_data_store.pop(user_id, None)
        return ConversationHandler.END

    # Списываем баланс и сохраняем
    deduct_balance(user_id)
    generation_id = save_generation(user_id, platform, category, result, data.get("tone"))

    await wait_message.delete()
    await update.message.reply_text(result)

    # Сохраняем данные для возможной перегенерации
    last_generation_data[user_id] = data.copy()

    # Показываем меню снова + кнопки сохранения и перегенерации
    keyboard = [
        [InlineKeyboardButton("⭐ Сохранить в избранное", callback_data=f"save_fav_{generation_id}")],
        [InlineKeyboardButton("🔁 Сгенерировать другой вариант", callback_data="regenerate")],
        [InlineKeyboardButton("📝 Создать описание", callback_data="new")],
        [InlineKeyboardButton("💳 Пополнить баланс", callback_data="pay")],
        [InlineKeyboardButton("👤 Мой профиль", callback_data="profile")],
        [InlineKeyboardButton("📜 История", callback_data="history"), InlineKeyboardButton("⭐ Избранное", callback_data="favorites")],
    ]
    await update.message.reply_text(
        "Готово! Что дальше?", reply_markup=InlineKeyboardMarkup(keyboard)
    )

    # Чистим временные данные диалога (последняя генерация остаётся)
    user_data_store.pop(user_id, None)
    return ConversationHandler.END


async def add_balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для пополнения баланса. Администратор может пополнить любого пользователя."""
    admin_user_id = update.effective_user.id

    # Проверяем, является ли пользователь администратором (дополнительная защита)
    if str(admin_user_id) != str(ADMIN_ID):
        await update.message.reply_text("⛔ У вас нет прав для этой команды.")
        return

    try:
        if len(context.args) == 1:
            # /add_balance 5 — пополняем себя
            target_id = admin_user_id
            amount = int(context.args[0])
        elif len(context.args) == 2:
            # /add_balance user_id 5 — пополняем указанного пользователя
            target_id = int(context.args[0])
            amount = int(context.args[1])
        else:
            raise ValueError
    except (IndexError, ValueError):
        await update.message.reply_text(
            "Использование:\n"
            "• /add_balance <количество> — пополнить себя\n"
            "• /add_balance <user_id> <количество> — пополнить пользователя\n\n"
            "Пример: /add_balance 5\n"
            "Пример: /add_balance 123456789 5"
        )
        return

    add_balance(target_id, amount)
    new_balance = get_balance(target_id)
    await update.message.reply_text(
        f"✅ Баланс пользователя {target_id} пополнен на {amount} описаний.\n"
        f"💰 Текущий баланс: {new_balance}"
    )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена диалога."""
    user_id = update.effective_user.id
    user_data_store.pop(user_id, None)
    await update.message.reply_text("Диалог отменён. Отправьте /start для начала.")
    return ConversationHandler.END


async def cancel_dialog_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена диалога по кнопке."""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    user_data_store.pop(user_id, None)
    await query.edit_message_text(
        "❌ Диалог отменён.\n\n"
        "Отправьте /start для возврата в меню."
    )
    return ConversationHandler.END


async def start_fallback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сброс диалога и показ главного меню (используется как fallback в ConversationHandler)."""
    user_id = update.effective_user.id
    user_data_store.pop(user_id, None)
    # Показываем меню сразу
    user = update.effective_user
    db_user = get_or_create_user(user.id, user.username, user.first_name)
    balance = db_user[3]

    low_balance_text = ""
    if balance <= 2 and balance > 0:
        low_balance_text = (
            f"⚠️ Внимание: у вас осталось {balance} описаний. "
            f"Рекомендуем пополнить баланс заранее.\n\n"
        )

    text = (
        f"Привет, {user.first_name}! 👋\n\n"
        "Я бот для генерации описаний товаров.\n"
        "Выберите площадку, расскажите о товаре — и я подготовлю готовый текст.\n\n"
        f"💰 Ваш баланс: {balance} описаний\n\n"
        + low_balance_text +
        "Чтобы начать, нажмите кнопку ниже.\n"
        "Нужна помощь? Отправьте /help"
    )
    keyboard = [
        [InlineKeyboardButton("📝 Создать описание", callback_data="new")],
        [InlineKeyboardButton("💳 Пополнить баланс", callback_data="pay")],
        [InlineKeyboardButton("👤 Мой профиль", callback_data="profile")],
        [InlineKeyboardButton("📜 История", callback_data="history"), InlineKeyboardButton("⭐ Избранное", callback_data="favorites")],
    ]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    return ConversationHandler.END


async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /help — справка по боту."""
    keyboard = [
        [InlineKeyboardButton("💬 Написать администратору", callback_data="support")],
    ]
    text = (
        "📖 <b>Справка по боту</b>\n\n"
        "<b>Кнопки в меню:</b>\n"
        "• <b>📝 Создать описание</b> — начать генерацию текста для товара\n"
        "• <b>💳 Пополнить баланс</b> — узнать реквизиты для оплаты\n"
        "• <b>👤 Мой профиль</b> — проверить баланс\n"
        "• <b>📜 История</b> — посмотреть прошлые генерации\n\n"
        "<b>Полезные команды:</b>\n"
        "• /start — главное меню\n"
        "• /cancel — отменить текущий диалог (если застряли)\n"
        "• /help — эта справка\n\n"
        "<b>Если что-то пошло не так:</b>\n"
        "1. Отправьте /cancel\n"
        "2. Отправьте /start\n"
        "3. Попробуйте снова\n\n"
        "❓ Остались вопросы? Нажмите кнопку ниже — администратор получит уведомление."
    )
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))


def main():
    """Главная функция — точка входа."""
    init_db()  # Создаём таблицы в базе данных

    application = Application.builder().token(BOT_TOKEN).build()

    # Диалог генерации описания
    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(button_handler, pattern="^new$")],
        states={
            PLATFORM: [CallbackQueryHandler(platform_chosen, pattern="^(wb|ozon|yandex|avito|ownsite)$")],
            TONE: [CallbackQueryHandler(tone_chosen, pattern="^(tone_default|tone_custom|tone_formal|tone_friendly|tone_aggressive|tone_humorous)$")],
            CATEGORY: [MessageHandler(filters.TEXT & ~filters.COMMAND, category_received)],
            CHARACTERISTICS: [MessageHandler(filters.TEXT & ~filters.COMMAND, characteristics_received)],
            AUDIENCE: [MessageHandler(filters.TEXT & ~filters.COMMAND, audience_received)],
            ADVANTAGES: [MessageHandler(filters.TEXT & ~filters.COMMAND, advantages_received)],
            KEYWORDS: [MessageHandler(filters.TEXT & ~filters.COMMAND, keywords_received)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("start", start_fallback),
            CallbackQueryHandler(cancel_dialog_handler, pattern="^cancel_dialog$"),
        ],
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_handler))
    application.add_handler(CommandHandler("add_balance", add_balance_command))
    application.add_handler(conv_handler)
    application.add_handler(CallbackQueryHandler(button_handler, pattern=r"^(profile|history|favorites|pay|paid|menu|support|saved|regenerate|save_fav_\d+)$"))

    print("Бот запущен. Нажмите Ctrl+C для остановки.")
    application.run_polling()


if __name__ == "__main__":
    main()
