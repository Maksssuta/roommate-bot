# Предполагается, что предыдущий код с FSM и таблицами остаётся без изменений

# ================== ПОИСК С КАРУСЕЛЬЮ ==================
from collections import defaultdict

# Хранение индекса текущей анкеты для каждого пользователя
user_search_index = defaultdict(int)

async def send_next_profile(chat_id: int, user_id: int):
    cursor.execute("SELECT role FROM users WHERE telegram_id=?", (user_id,))
    row = cursor.fetchone()
    if not row:
        await bot.send_message(chat_id, "Сначала зарегистрируй анкету через /start")
        return

    role = row[0]
    if role == "roommate":
        cursor.execute("SELECT telegram_id, first_name, last_name, user_photo, about FROM users WHERE role='seeker' AND telegram_id != ? ORDER BY id", (user_id,))
    else:
        cursor.execute("SELECT telegram_id, first_name, last_name, user_photo, apartment_photo, apartment_desc, price FROM users WHERE role='roommate' AND telegram_id != ? ORDER BY id", (user_id,))

    matches = cursor.fetchall()
    if not matches:
        await bot.send_message(chat_id, "Пока нет подходящих анкет 😔")
        return

    index = user_search_index[user_id]
    if index >= len(matches):
        await bot.send_message(chat_id, "Анкеты закончились 😔")
        user_search_index[user_id] = 0
        return

    match = matches[index]

    kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="✅ Заинтересован", callback_data=f"like_{match[0]}")],
        [types.InlineKeyboardButton(text="❌ Пропустить", callback_data=f"skip_{match[0]}")]
    ])

    if role == "roommate":
        text = f"👤 {match[1]} {match[2]}\n{match[4]}"
        await bot.send_photo(chat_id, photo=match[3], caption=text, reply_markup=kb)
    else:
        text = f"👤 {match[1]} {match[2]}\nО квартире:\n{match[5]}\nЦена: {match[6]}"
        # Отправляем фото пользователя + квартиры
        await bot.send_media_group(
            chat_id,
            media=[
                types.InputMediaPhoto(match[3], caption="Пользователь"),
                types.InputMediaPhoto(match[4], caption=text)
            ]
        )
        await bot.send_message(chat_id, "Выбери действие:", reply_markup=kb)

@dp.message(Command("search"))
async def search(message: Message):
    user_search_index[message.from_user.id] = 0  # Начинаем с первой анкеты
    await send_next_profile(message.chat.id, message.from_user.id)

# ================== ЛАЙКИ С ПЕРЕХОДОМ К СЛЕДУЮЩЕЙ АНКЕТЕ ==================
@dp.callback_query(lambda c: c.data.startswith(("like", "skip")))
async def process_like(callback: CallbackQuery):
    action, target_id = callback.data.split("_")
    target_id = int(target_id)

    if action == "like":
        cursor.execute("INSERT OR IGNORE INTO likes (from_user, to_user) VALUES (?, ?)", (callback.from_user.id, target_id))
        conn.commit()

        # Проверяем взаимный лайк
        cursor.execute("SELECT 1 FROM likes WHERE from_user=? AND to_user=?", (target_id, callback.from_user.id))
        mutual = cursor.fetchone()

        if mutual:
            cursor.execute("SELECT first_name, last_name FROM users WHERE telegram_id=?", (target_id,))
            target_data = cursor.fetchone()
            cursor.execute("SELECT first_name, last_name FROM users WHERE telegram_id=?", (callback.from_user.id,))
            user_data = cursor.fetchone()

            await bot.send_message(callback.from_user.id,
                                   f"🎉 У вас взаимный интерес! Вот ссылка на собеседника: tg://user?id={target_id}\n👤 {target_data[0]} {target_data[1]}")
            await bot.send_message(target_id,
                                   f"🎉 У вас взаимный интерес! Вот ссылка на собеседника: tg://user?id={callback.from_user.id}\n👤 {user_data[0]} {user_data[1]}")
        else:
            await callback.answer("Отправлен интерес ✅")
    else:
        await callback.answer("Пропущено ❌")

    # Переходим к следующей анкете
    user_search_index[callback.from_user.id] += 1
    await send_next_profile(callback.from_user.id, callback.from_user.id)

