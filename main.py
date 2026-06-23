import asyncio
import sqlite3
import requests
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Command
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils import executor

# ================= КОНФИГ =================
API_TOKEN = '8657473893:AAGngc2DPixc3rLDZsw52BGMORgOfjMfxk4'  # Замени на свой токен от @BotFather
ADMIN_IDS = [7293950231]  # Замени на свой Telegram ID (узнай у @userinfobot)
RENDER_URL = 'https://chinadirect.onrender.com'  # Замени на URL твоего бота на Render

bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

# ================= БАЗА ДАННЫХ =================
def init_db():
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            product_name TEXT,
            quantity TEXT,
            status TEXT DEFAULT 'новый',
            created_at TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# ================= СОСТОЯНИЯ =================
class OrderState(StatesGroup):
    waiting_for_product = State()

# ================= КЛАВИАТУРЫ =================
def main_menu():
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton("🛒 Сделать заказ", callback_data="new_order"),
        InlineKeyboardButton("📋 Мои заказы", callback_data="my_orders"),
        InlineKeyboardButton("📞 Связаться с менеджером", callback_data="contact")
    )
    return keyboard

def categories_menu():
    keyboard = InlineKeyboardMarkup(row_width=2)
    categories = ["🚪 Двери", "🧱 Покрытия", "🛋 Мебель", "🪟 Другое"]
    for cat in categories:
        keyboard.add(InlineKeyboardButton(cat, callback_data=f"cat_{cat}"))
    keyboard.add(InlineKeyboardButton("◀️ Назад", callback_data="back"))
    return keyboard

# ================= СТАРТ =================
@dp.message_handler(Command("start"))
async def start(message: types.Message):
    await message.answer(
        "🇨🇳 <b>ИМПОРТНЫЙ АГРЕГАТОР</b>\n\n"
        "🚪 Двери | 🧱 Покрытия | 🛋 Мебель\n"
        "🇨🇳 Прямые поставки из Китая\n\n"
        "Выберите действие:",
        parse_mode="HTML",
        reply_markup=main_menu()
    )

# ================= НОВЫЙ ЗАКАЗ =================
@dp.callback_query_handler(lambda c: c.data == "new_order")
async def new_order(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "📂 <b>Выберите категорию:</b>",
        parse_mode="HTML",
        reply_markup=categories_menu()
    )
    await callback.answer()

@dp.callback_query_handler(lambda c: c.data.startswith("cat_"))
async def choose_category(callback: types.CallbackQuery, state: FSMContext):
    category = callback.data.replace("cat_", "")
    await state.update_data(category=category)
    
    await callback.message.edit_text(
        f"📂 <b>{category}</b>\n\n"
        "Введите <b>название</b> товара, который хотите заказать:\n"
        "Например: Дверь Венеция, Ламинат 8мм, Диван угловой",
        parse_mode="HTML"
    )
    await OrderState.waiting_for_product.set()
    await callback.answer()

@dp.message_handler(state=OrderState.waiting_for_product)
async def get_product_name(message: types.Message, state: FSMContext):
    data = await state.get_data()
    category = data.get('category')
    product_name = message.text
    
    user_id = message.from_user.id
    username = message.from_user.username or "без username"
    
    # Сохраняем заказ в базу
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO orders (user_id, username, product_name, quantity, status, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, username, product_name, "уточняется", "новый", datetime.now().strftime('%d.%m.%Y %H:%M'))
    )
    order_id = cur.lastrowid
    conn.commit()
    conn.close()
    
    # Отправляем уведомление менеджеру
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                f"🆕 <b>НОВЫЙ ЗАКАЗ #{order_id}</b>\n\n"
                f"👤 Клиент: @{username}\n"
                f"📂 Категория: {category}\n"
                f"📦 Товар: {product_name}\n"
                f"📅 Время: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
                f"Свяжитесь с клиентом и утвердите заказ:\n"
                f"<code>/approve {username} {product_name} 5</code>\n"
                f"(где 5 - количество)",
                parse_mode="HTML"
            )
        except:
            pass
    
    await message.answer(
        f"✅ <b>Заказ #{order_id} принят!</b>\n\n"
        f"📦 Товар: {product_name}\n\n"
        f"Менеджер свяжется с вами в ближайшее время.\n"
        f"Статус заказа можно отслеживать в разделе «Мои заказы».",
        parse_mode="HTML",
        reply_markup=main_menu()
    )
    await state.finish()

# ================= МОИ ЗАКАЗЫ =================
@dp.callback_query_handler(lambda c: c.data == "my_orders")
async def my_orders(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute(
        "SELECT id, product_name, quantity, status, created_at FROM orders "
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
        order_id, product, qty, status, created = order
        status_emoji = {
            'новый': '🟡',
            'утверждён': '🟢',
            'отменён': '🔴'
        }.get(status, '⚪')
        
        text += f"{status_emoji} <b>Заказ #{order_id}</b>\n"
        text += f"📦 {product}\n"
        text += f"🔢 {qty}\n"
        text += f"📅 {created}\n"
        text += f"📌 Статус: <b>{status.upper()}</b>\n"
        text += "─" * 20 + "\n"
    
    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=main_menu()
    )
    await callback.answer()

# ================= УТВЕРЖДЕНИЕ ЗАКАЗА (АДМИН) =================
@dp.message_handler(Command("approve"))
async def approve_order(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ Нет прав")
        return
    
    parts = message.text.split(maxsplit=3)
    if len(parts) < 4:
        await message.answer(
            "❌ Используйте:\n"
            "<code>/approve @username товар количество</code>\n\n"
            "Пример:\n"
            "<code>/approve @ivanov Дверь Венеция 2</code>",
            parse_mode="HTML"
        )
        return
    
    username = parts[1].replace('@', '')
    product_name = parts[2]
    quantity = parts[3]
    
    # Ищем заказ в базе
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute(
        "SELECT id, user_id FROM orders "
        "WHERE username=? AND product_name=? AND status='новый' "
        "ORDER BY id DESC LIMIT 1",
        (username, product_name)
    )
    order = cur.fetchone()
    
    if not order:
        await message.answer(
            f"❌ Не найден активный заказ для @{username} с товаром «{product_name}»"
        )
        conn.close()
        return
    
    order_id, user_id = order
    
    # Обновляем статус заказа
    cur.execute(
        "UPDATE orders SET quantity=?, status='утверждён' WHERE id=?",
        (quantity, order_id)
    )
    conn.commit()
    conn.close()
    
    # Отправляем уведомление клиенту
    try:
        await bot.send_message(
            user_id,
            f"✅ <b>ЗАКАЗ #{order_id} УТВЕРЖДЁН!</b>\n\n"
            f"📦 Товар: {product_name}\n"
            f"🔢 Количество: {quantity} шт.\n\n"
            f"Менеджер свяжется с вами для уточнения деталей.",
            parse_mode="HTML"
        )
    except:
        pass
    
    await message.answer(
        f"✅ Заказ #{order_id} утверждён!\n"
        f"👤 @{username}\n"
        f"📦 {product_name}\n"
        f"🔢 {quantity} шт."
    )

# ================= ОТМЕНА ЗАКАЗА (АДМИН) =================
@dp.message_handler(Command("cancel"))
async def cancel_order(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ Нет прав")
        return
    
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(
            "❌ Используйте: <code>/cancel @username</code>",
            parse_mode="HTML"
        )
        return
    
    username = parts[1].replace('@', '')
    
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute(
        "UPDATE orders SET status='отменён' WHERE username=? AND status='новый'",
        (username,)
    )
    affected = cur.rowcount
    conn.commit()
    conn.close()
    
    if affected > 0:
        await message.answer(f"✅ Отменены все активные заказы для @{username}")
    else:
        await message.answer(f"❌ Нет активных заказов для @{username}")

# ================= СВЯЗЬ С МЕНЕДЖЕРОМ =================
@dp.callback_query_handler(lambda c: c.data == "contact")
async def contact_manager(callback: types.CallbackQuery):
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                f"📞 Клиент @{callback.from_user.username or 'без username'} хочет связаться"
            )
        except:
            pass
    
    await callback.message.edit_text(
        "📞 <b>Менеджер свяжется с вами в ближайшее время!</b>",
        parse_mode="HTML",
        reply_markup=main_menu()
    )
    await callback.answer()

# ================= НАЗАД В ГЛАВНОЕ МЕНЮ =================
@dp.callback_query_handler(lambda c: c.data == "back")
async def back(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "🇨🇳 <b>ИМПОРТНЫЙ АГРЕГАТОР</b>\n\n"
        "🚪 Двери | 🧱 Покрытия | 🛋 Мебель\n"
        "🇨🇳 Прямые поставки из Китая\n\n"
        "Выберите действие:",
        parse_mode="HTML",
        reply_markup=main_menu()
    )
    await callback.answer()

# ================= ПИНГОВАНИЕ (чтоб бот не засыпал) =================
async def ping_self():
    """Каждую минуту пингует себя, чтобы Render не засыпал"""
    while True:
        try:
            response = requests.get(RENDER_URL, timeout=10)
            print(f"[PING] {datetime.now().strftime('%H:%M:%S')} - Status: {response.status_code}")
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
