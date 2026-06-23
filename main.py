import asyncio
import logging
import sqlite3
import aiohttp
import time
from datetime import datetime
from aiogram import Bot, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import Dispatcher, FSMContext
from aiogram.dispatcher.filters import Command
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.utils import executor

# ================= КОНФИГУРАЦИЯ =================
API_TOKEN = '8657473893:AAGngc2DPixc3rLDZsw52BGMORgOfjMfxk4'  # Замени на свой токен от @BotFather
ADMIN_IDS = [7293950231]  # Замени на свой Telegram ID
RENDER_URL = 'https://chinadirect.onrender.com'  # Замени на URL твоего сервиса на Render

bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

# ================= БАЗА ДАННЫХ =================
def init_db():
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT,
            name TEXT,
            description TEXT,
            price TEXT
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            product_name TEXT,
            quantity INTEGER,
            price TEXT,
            status TEXT DEFAULT 'новый',
            created_at TEXT,
            confirmed_at TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# ================= СОСТОЯНИЯ =================
class OrderStates(StatesGroup):
    waiting_for_quantity = State()

class AdminStates(StatesGroup):
    waiting_for_category = State()
    waiting_for_name = State()
    waiting_for_description = State()
    waiting_for_price = State()

# ================= КЛАВИАТУРЫ =================
def main_menu():
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("📦 Каталог", callback_data="catalog"),
        InlineKeyboardButton("📋 Мои заказы", callback_data="my_orders")
    )
    keyboard.add(
        InlineKeyboardButton("📞 Связаться с менеджером", callback_data="contact_manager")
    )
    return keyboard

def categories_menu():
    keyboard = InlineKeyboardMarkup(row_width=1)
    categories = ["🚪 Двери", "🧱 Настенные покрытия", "🧱 Напольные покрытия", "🛋 Мебель", "🪟 Другое"]
    for cat in categories:
        keyboard.add(InlineKeyboardButton(cat, callback_data=f"cat_{cat}"))
    keyboard.add(InlineKeyboardButton("◀️ Главное меню", callback_data="main_menu"))
    return keyboard

def product_buttons(product_id):
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(InlineKeyboardButton("🛒 Заказать", callback_data=f"order_{product_id}"))
    keyboard.add(InlineKeyboardButton("◀️ Назад", callback_data="catalog"))
    return keyboard

# ================= СТАРТ =================
@dp.message_handler(Command("start"))
async def start(message: types.Message):
    await message.answer(
        "🇨🇳 <b>ИМПОРТНЫЙ АГРЕГАТОР</b>\n\n"
        "🚪 Двери | 🧱 Покрытия | 🛋 Мебель\n"
        "🇨🇳 Прямые поставки из Китая\n\n"
        "⬇️ Выберите действие:",
        parse_mode="HTML",
        reply_markup=main_menu()
    )

# ================= КАТАЛОГ =================
@dp.callback_query_handler(lambda c: c.data == "catalog")
async def show_catalog(callback: CallbackQuery):
    await callback.message.edit_text(
        "📂 <b>Выберите категорию:</b>",
        parse_mode="HTML",
        reply_markup=categories_menu()
    )
    await callback.answer()

@dp.callback_query_handler(lambda c: c.data.startswith("cat_"))
async def show_products(callback: CallbackQuery):
    category = callback.data.replace("cat_", "")
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute("SELECT id, name, price FROM products WHERE category=?", (category,))
    products = cur.fetchall()
    conn.close()
    
    if not products:
        await callback.answer("В этой категории пока нет товаров", show_alert=True)
        return
    
    keyboard = InlineKeyboardMarkup(row_width=1)
    for prod_id, name, price in products:
        keyboard.add(InlineKeyboardButton(f"{name} - {price}", callback_data=f"prod_{prod_id}"))
    keyboard.add(InlineKeyboardButton("◀️ Назад", callback_data="catalog"))
    
    await callback.message.edit_text(
        f"📂 <b>{category}</b>\nВыберите товар:",
        parse_mode="HTML",
        reply_markup=keyboard
    )
    await callback.answer()

@dp.callback_query_handler(lambda c: c.data.startswith("prod_"))
async def show_product_detail(callback: CallbackQuery):
    product_id = int(callback.data.replace("prod_", ""))
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute("SELECT name, description, price FROM products WHERE id=?", (product_id,))
    product = cur.fetchone()
    conn.close()
    
    if not product:
        await callback.answer("Товар не найден", show_alert=True)
        return
    
    name, desc, price = product
    text = f"📦 <b>{name}</b>\n\n📝 {desc}\n\n💰 {price}"
    
    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=product_buttons(product_id)
    )
    await callback.answer()

# ================= ЗАКАЗ =================
@dp.callback_query_handler(lambda c: c.data.startswith("order_"))
async def start_order(callback: CallbackQuery, state: FSMContext):
    product_id = int(callback.data.replace("order_", ""))
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute("SELECT name FROM products WHERE id=?", (product_id,))
    product = cur.fetchone()
    conn.close()
    
    if not product:
        await callback.answer("Товар не найден", show_alert=True)
        return
    
    await state.update_data(product_name=product[0])
    await callback.message.answer(
        f"🛒 <b>Оформление заказа</b>\n\nТовар: {product[0]}\n\nВведите <b>количество</b>:",
        parse_mode="HTML"
    )
    await OrderStates.waiting_for_quantity.set()
    await callback.answer()

@dp.message_handler(state=OrderStates.waiting_for_quantity)
async def process_quantity(message: types.Message, state: FSMContext):
    try:
        quantity = int(message.text)
        if quantity <= 0:
            await message.answer("❌ Количество должно быть больше 0.")
            return
    except ValueError:
        await message.answer("❌ Введите число.")
        return
    
    data = await state.get_data()
    product_name = data.get('product_name')
    user_id = message.from_user.id
    username = message.from_user.username or "без username"
    
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO orders (user_id, username, product_name, quantity, price, status, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (user_id, username, product_name, quantity, "уточняется", "новый", datetime.now().strftime('%d.%m.%Y %H:%M'))
    )
    order_id = cur.lastrowid
    conn.commit()
    conn.close()
    
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                f"🆕 <b>НОВЫЙ ЗАКАЗ #{order_id}</b>\n\n"
                f"👤 Клиент: @{username} (ID: {user_id})\n"
                f"📦 Товар: {product_name}\n"
                f"🔢 Количество: {quantity}\n"
                f"📅 Время: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
                f"После согласования подтвердите:\n"
                f"<code>/confirm {username} {product_name} {quantity} 15000</code>",
                parse_mode="HTML"
            )
        except:
            pass
    
    await message.answer(
        f"✅ <b>Заказ #{order_id} оформлен!</b>\n\nМенеджер свяжется с вами.",
        parse_mode="HTML",
        reply_markup=main_menu()
    )
    await state.finish()

# ================= МОИ ЗАКАЗЫ =================
@dp.callback_query_handler(lambda c: c.data == "my_orders")
async def show_my_orders(callback: CallbackQuery):
    user_id = callback.from_user.id
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute(
        "SELECT id, product_name, quantity, price, status, created_at, confirmed_at FROM orders "
        "WHERE user_id=? ORDER BY id DESC",
        (user_id,)
    )
    orders = cur.fetchall()
    conn.close()
    
    if not orders:
        await callback.message.edit_text(
            "📋 <b>У вас пока нет заказов</b>",
            parse_mode="HTML",
            reply_markup=main_menu()
        )
        await callback.answer()
        return
    
    text = "📋 <b>МОИ ЗАКАЗЫ</b>\n\n"
    for order in orders:
        order_id, product, qty, price, status, created, confirmed = order
        status_emoji = {'новый': '🟡', 'подтверждён': '🟢', 'отменён': '🔴'}.get(status, '⚪')
        text += f"{status_emoji} <b>Заказ #{order_id}</b>\n"
        text += f"📦 {product}\n"
        text += f"🔢 {qty} шт.\n"
        text += f"💰 {price}\n"
        text += f"📅 {created}\n"
        if status == 'подтверждён' and confirmed:
            text += f"✅ Подтверждён: {confirmed}\n"
        text += f"📌 Статус: <b>{status.upper()}</b>\n"
        text += "─" * 20 + "\n"
    
    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=main_menu()
    )
    await callback.answer()

# ================= КОНФИРМАЦИЯ ЗАКАЗА (АДМИН) =================
@dp.message_handler(Command("confirm"))
async def confirm_order(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ Нет прав")
        return
    
    parts = message.text.split(maxsplit=4)
    if len(parts) < 5:
        await message.answer(
            "❌ Используйте: <code>/confirm @username товар количество цена</code>",
            parse_mode="HTML"
        )
        return
    
    username = parts[1].replace('@', '')
    product_name = parts[2]
    quantity = int(parts[3])
    price = parts[4]
    
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute(
        "SELECT id, user_id FROM orders "
        "WHERE username=? AND product_name=? AND quantity=? AND status='новый' "
        "ORDER BY id DESC LIMIT 1",
        (username, product_name, quantity)
    )
    order = cur.fetchone()
    
    if not order:
        await message.answer(f"❌ Заказ не найден для @{username}")
        conn.close()
        return
    
    order_id, user_id = order
    cur.execute(
        "UPDATE orders SET price=?, status='подтверждён', confirmed_at=? WHERE id=?",
        (price, datetime.now().strftime('%d.%m.%Y %H:%M'), order_id)
    )
    conn.commit()
    conn.close()
    
    try:
        await bot.send_message(
            user_id,
            f"✅ <b>ЗАКАЗ #{order_id} ПОДТВЕРЖДЁН!</b>\n\n"
            f"📦 Товар: {product_name}\n"
            f"🔢 Количество: {quantity}\n"
            f"💰 Цена: {price} руб.\n\n"
            f"🤝 Спасибо за заказ!",
            parse_mode="HTML"
        )
    except:
        pass
    
    await message.answer(f"✅ Заказ #{order_id} подтверждён для @{username}")

# ================= ОТМЕНА ЗАКАЗА (АДМИН) =================
@dp.message_handler(Command("cancel"))
async def cancel_order(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ Нет прав")
        return
    
    parts = message.text.split(maxsplit=2)
    if len(parts) < 2:
        await message.answer("❌ Используйте: <code>/cancel @username</code>", parse_mode="HTML")
        return
    
    username = parts[1].replace('@', '')
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute("UPDATE orders SET status='отменён' WHERE username=? AND status='новый'", (username,))
    affected = cur.rowcount
    conn.commit()
    conn.close()
    
    await message.answer(f"✅ Отменены заказы для @{username}" if affected > 0 else f"❌ Нет активных заказов для @{username}")

# ================= КОНТАКТ С МЕНЕДЖЕРОМ =================
@dp.callback_query_handler(lambda c: c.data == "contact_manager")
async def contact_manager(callback: CallbackQuery):
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                f"📞 Клиент @{callback.from_user.username or 'без username'} (ID: {callback.from_user.id}) хочет связаться"
            )
        except:
            pass
    
    await callback.message.edit_text(
        "📞 <b>Менеджер свяжется с вами!</b>",
        parse_mode="HTML",
        reply_markup=main_menu()
    )
    await callback.answer()

# ================= НАЗАД В ГЛАВНОЕ =================
@dp.callback_query_handler(lambda c: c.data == "main_menu")
async def back_main(callback: CallbackQuery):
    await callback.message.edit_text(
        "🇨🇳 <b>ИМПОРТНЫЙ АГРЕГАТОР</b>\n\n⬇️ Выберите действие:",
        parse_mode="HTML",
        reply_markup=main_menu()
    )
    await callback.answer()

# ================= АДМИНКА: ДОБАВЛЕНИЕ ТОВАРОВ =================
@dp.message_handler(Command("add"))
async def cmd_add(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ Нет прав")
        return
    await message.answer("Введите <b>категорию</b> (Двери, Настенные покрытия, Напольные покрытия, Мебель, Другое):", parse_mode="HTML")
    await AdminStates.waiting_for_category.set()

@dp.message_handler(state=AdminStates.waiting_for_category)
async def add_category(message: types.Message, state: FSMContext):
    await state.update_data(category=message.text)
    await message.answer("Введите <b>название</b> товара:", parse_mode="HTML")
    await AdminStates.waiting_for_name.set()

@dp.message_handler(state=AdminStates.waiting_for_name)
async def add_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("Введите <b>описание</b> товара:", parse_mode="HTML")
    await AdminStates.waiting_for_description.set()

@dp.message_handler(state=AdminStates.waiting_for_description)
async def add_description(message: types.Message, state: FSMContext):
    await state.update_data(description=message.text)
    await message.answer("Введите <b>цену</b> (например: от 15000 руб.):", parse_mode="HTML")
    await AdminStates.waiting_for_price.set()

@dp.message_handler(state=AdminStates.waiting_for_price)
async def add_price(message: types.Message, state: FSMContext):
    data = await state.get_data()
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO products (category, name, description, price) VALUES (?, ?, ?, ?)",
        (data['category'], data['name'], data['description'], message.text)
    )
    conn.commit()
    conn.close()
    await message.answer("✅ Товар добавлен!")
    await state.finish()

# ================= ФУНКЦИЯ ДЛЯ ПИНГОВАНИЯ =================
async def ping_self():
    """Каждую минуту отправляет GET-запрос к себе, чтобы Render не засыпал"""
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(RENDER_URL) as response:
                    print(f"[PING] {datetime.now().strftime('%H:%M:%S')} - Status: {response.status}")
        except Exception as e:
            print(f"[PING ERROR] {e}")
        await asyncio.sleep(60)  # Пауза 60 секунд

# ================= ЗАПУСК =================
if __name__ == "__main__":
    # Запускаем пингование в фоновом режиме
    loop = asyncio.get_event_loop()
    loop.create_task(ping_self())
    
    # Запускаем бота
    executor.start_polling(dp, skip_updates=True)
