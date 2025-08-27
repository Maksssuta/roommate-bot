import sqlite3
import os
import asyncio
import logging
from collections import defaultdict

from aiogram import Bot, Dispatcher, types
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage

logging.basicConfig(level=logging.INFO)

API_TOKEN = "8250866605:AAGKcaplvHLEW9BH7efSbbn2hSTN1K7TFZg"

# ================== ИНИЦИАЛИЗАЦИЯ БОТА ==================
bot = Bot(token=API_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

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
    user_photo TEXT,
    about TEXT,
    apartment_photo TEXT,
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

# ================== FSM СОСТОЯНИЯ ==================
class Form(StatesGroup):
    waiting_for_role = State()
    waiting_for_user_photo = State()
    waiting_for_about = State()
    waiting_for_apartment_photo = State()
    waiting_for_apartment_desc = State()
    waiting_for_price = State()

# ================== КАРУСЕЛЬ ==================
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
        await bot.send_media_group(
            chat_id,
            media=[
                types.InputMediaPhoto(match[3], caption="Пользователь"),
                types.InputMediaPhoto(match[4], caption=text)
            ]
        )
        await bot.send_message(chat_id, "Выбери действие:", reply_markup=kb)

# ================== ОБРАБОТЧИКИ ==================

# /start
@dp.message(Command("start"))
async def start(message: Message, state: FSMContext):
    await state.clear()
    kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="Ищу соседа для подселения", callback_data="role_roommate")],
        [types.InlineKeyboardButton(text="Ищу жильё и сожителя", callback_data="role_seeker")]
    ])
    await message.answer("Привет! 🏠 Давай создадим твою анкету. Кем ты являешься?", reply_markup=kb)
    await Form.waiting_for_role.set()

# Выбор роли
@dp.callback_query(lambda c: c.data.startswith("role"))
async def process_role(callback: CallbackQuery, state: FSMContext):
    role = callback.data.split("_")[1]
    await state.update_data(role=role)

    cursor.execute("INSERT OR IGNORE INTO users (telegram_id, first_name, last_name, role) VALUES (?, ?, ?, ?)",
                   (callback.from_user.id, callback.from_user.first_name, callback.from_user.last_name, role))
    conn.commit()

    await bot.send_message(callback.from_user.id, "Отправь, пожалуйста, своё фото (профильное).")
    await Form.waiting_for_user_photo.set()
    await callback.answer()

# Фото пользователя
@dp.message(lambda message: message.photo, state=Form.waiting_for_user_photo)
async def user_photo(message: Message, state: FSMContext):
    photo_id = message.photo[-1].file_id
    await state.update_data(user_photo=photo_id)
    await message.answer("Фото получено ✅\nРасскажи немного о себе.")
    await Form.waiting_for_about.set()

# Краткая информация
@dp.message(state=Form.waiting_for_about)
async def about(message: Message, state: FSMContext):
    await state.update_data(about=message.text)
    data = await state.get_data()
    if data['role'] == "roommate":
        await message.answer("Теперь пришли фото квартиры.")
        await Form.waiting_for_apartment_photo.set()
    else:
        cursor.execute("""
            UPDATE users SET user_photo=?, about=? WHERE telegram_id=?
        """, (data['user_photo'], data['about'], message.from_user.id))
        conn.commit()
        await message.answer("Анкета сохранена ✅ Используй /search")
        await state.clear()

# Фото квартиры
@dp.message(lambda message: message.photo, state=Form.waiting_for_apartment_photo)
async def apartment_photo(message: Message, state: FSMContext):
    photo_id = message.photo[-1].file_id
    await state.update_data(apartment_photo=photo_id)
    await message.answer("Фото квартиры сохранено ✅\nОпиши квартиру (район, условия и т.д.).")
    await Form.waiting_for_apartment_desc.set()

# Описание квартиры
@dp.message(state=Form.waiting_for_apartment_desc)
async def apartment_desc(message: Message, state: FSMContext):
    await state.update_data(apartment_desc=message.text)
    await message.answer("Укажи цену квартиры (числом).")
    await Form.waiting_for_price.set()

# Цена квартиры
@dp.message(state=Form.waiting_for_price)
async def price(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Пожалуйста, введи цену числом.")
        return
    price = int(message.text)
    await state.update_data(price=price)

    data = await state.get_data()
    cursor.execute("""
        UPDATE users SET user_photo=?, about=?, apartment_photo=?, apartment_desc=?, price=? WHERE telegram_id=?
    """, (data['user_photo'], data['about'], data['apartment_photo'], data['apartment_desc'], data['price'], message.from_user.id))
    conn.commit()

    await message.answer("Анкета сохранена ✅ Теперь используй /search для поиска жильцов.")
    await state.clear()

# /search
@dp.message(Command("search"))
async def search(message: Message):
    user_search_index[message.from_user.id] = 0
    await send_next_profile(message.chat.id, message.from_user.id)

# Лайки и пропуск
@dp.callback_query(lambda c: c.data.startswith(("like", "skip")))
async def process_like(callback: CallbackQuery):
    action, target_id = callback.data.split("_")
    target_id = int(target_id)

    if action == "like":
        cursor.execute("INSERT OR IGNORE INTO likes (from_user, to_user) VALUES (?, ?)", (callback.from_user.id, target_id))
        conn.commit()
        cursor.execute("SELECT 1 FROM likes WHERE from_user=? AND to_user=?", (target_id, callback.from_user.id))
        mutual = cursor.fetchone()
        if mutual:
            cursor.execute("SELECT first_name, last_name FROM users WHERE telegram_id=?", (target_id,))
            target_data = cursor.fetchone()
            cursor.execute("SELECT first_name, last_name FROM users WHERE telegram_id=?", (callback.from_user.id,))
            user_data = cursor.fetchone()

            await bot.send_message(callback.from_user.id,
                                   f"🎉 Взаимный интерес! tg://user?id={target_id}\n👤 {target_data[0]} {target_data[1]}")
            await bot.send_message(target_id,
                                   f"🎉 Взаимный интерес! tg://user?id={callback.from_user.id}\n👤 {user_data[0]} {user_data[1]}")
        else:
            await callback.answer("Отправлен интерес ✅")
    else:
        await callback.answer("Пропущено ❌")

    user_search_index[callback.from_user.id] += 1
    await send_next_profile(callback.from_user.id, callback.from_user.id)

# ================== ЗАПУСК ==================
async def main():
    logging.info("Удаляем webhook и pending updates...")
    await bot.delete_webhook(drop_pending_updates=True)
    logging.info("Стартуем polling...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

