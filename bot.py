import sqlite3
import os
import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command

logging.basicConfig(level=logging.INFO)

API_TOKEN = "7993633698:AAGyhYZonytprP2UypN__galoGDgi2TvlBw"  # Токен берём из переменной окружения

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# ================== БАЗА ДАННЫХ ==================
DB_PATH = os.getenv("DB_PATH", "roommates.db")
os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)

conn = sqlite3.connect(DB_PATH, check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER UNIQUE,
    first_name TEXT,
    last_name TEXT,
    role TEXT,
    apartment_desc TEXT,
    price INTEGER
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS likes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_user INTEGER,
    to_user INTEGER,
    UNIQUE(from_user, to_user)
)
""")

conn.commit()

# ================== ОБРАБОТЧИКИ ==================

@dp.message(Command("start"))
async def start(message: Message):
    cursor.execute("INSERT OR IGNORE INTO users (telegram_id, first_name, last_name) VALUES (?, ?, ?)",
                   (message.from_user.id, message.from_user.first_name, message.from_user.last_name))
    conn.commit()

    kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="Ищу соседа для подселения", callback_data="role_roommate")],
        [types.InlineKeyboardButton(text="Ищу жильё и сожителя", callback_data="role_seeker")]
    ])
    await message.answer("Привет! 🏠 Давай создадим твою анкету. Кем ты являешься?", reply_markup=kb)


@dp.callback_query(lambda c: c.data.startswith("role"))
async def process_role(callback: CallbackQuery):
    role = callback.data.split("_")[1]
    cursor.execute("UPDATE users SET role=? WHERE telegram_id=?", (role, callback.from_user.id))
    conn.commit()

    if role == "roommate":
        await bot.send_message(callback.from_user.id, "Опиши квартиру (район, условия, стоимость)")
    else:
        await bot.send_message(callback.from_user.id, "Отлично! Мы будем показывать тебе квартиры, где ищут соседей. Используй /search")

    await callback.answer()


@dp.message()
async def save_apartment_desc(message: Message):
    cursor.execute("SELECT role FROM users WHERE telegram_id=?", (message.from_user.id,))
    row = cursor.fetchone()
    if row and row[0] == "roommate":
        cursor.execute("UPDATE users SET apartment_desc=? WHERE telegram_id=?", (message.text, message.from_user.id))
        conn.commit()
        await message.answer("Описание квартиры сохранено ✅ Теперь используй /search, чтобы найти жильца")


@dp.message(Command("search"))
async def search(message: Message):
    cursor.execute("SELECT role FROM users WHERE telegram_id=?", (message.from_user.id,))
    row = cursor.fetchone()
    if not row:
        await message.answer("Сначала зарегистрируй анкету через /start")
        return

    role = row[0]
    if role == "roommate":
        cursor.execute("SELECT telegram_id, first_name, last_name FROM users WHERE role='seeker' AND telegram_id != ? LIMIT 1", (message.from_user.id,))
    else:
        cursor.execute("SELECT telegram_id, first_name, last_name, apartment_desc FROM users WHERE role='roommate' AND telegram_id != ? LIMIT 1", (message.from_user.id,))

    match = cursor.fetchone()
    if not match:
        await message.answer("Пока нет подходящих анкет 😔")
        return

    kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="✅ Заинтересован", callback_data=f"like_{match[0]}")],
        [types.InlineKeyboardButton(text="❌ Пропустить", callback_data=f"skip_{match[0]}")]
    ])

    if role == "roommate":
        text = f"👤 {match[1]} {match[2]}\nИщет жильё и сожителя"
    else:
        text = f"👤 {match[1]} {match[2]}\nПредлагает квартиру:\n{match[3]}"

    await message.answer(text, reply_markup=kb)


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
            # Получаем данные пользователей
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

# ================== ЗАПУСК ==================
async def main():
    logging.info("Бот запущен и слушает сообщения...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
