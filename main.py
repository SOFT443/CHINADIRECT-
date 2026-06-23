import asyncio
import logging
import sqlite3
import os
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton

# ================= КОНФИГУРАЦИЯ =================
API_TOKEN = 'ТВОЙ_ТОКЕН_СЮДА'  # Замени на свой токен от @BotFather
ADMIN_IDS = [123456789]  # Замени на свой Telegram ID (узнай у @userinfobot)

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# ================= БАЗА ДАННЫХ =================
def init_db():
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    
    # Таблица товаров (каталог)
    cur.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT,
            name TEXT,
            description TEXT,
            price TEXT
        )
    ''')
    
    # Таблица заказов
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
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📦 Каталог товаров", callback_data="catalog"),
        InlineKeyboardButton(text="📋 Мои заказы", callback_data="my_orders")
    )
    builder.row(
        InlineKeyboardButton(text="📞 Связаться с менеджером", callback_data="contact_manager")
    )
    return builder.as_markup()

def categories_menu():
    builder = InlineKeyboardBuilder()
    categories = ["🚪 Двери", "🧱 Настенные покрытия", "🧱 Напольные покрытия", "🛋 Мебель", "🪟 Другое"]
    for cat in categories:
        builder.row(InlineKeyboardButton(text=cat, callback_data=f"cat_{cat}"))
    builder.row(InlineKeyboardButton(text="◀️ Главное меню", callback_data="main_menu"))
    return builder.as_markup()

def product_buttons(product_id):
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🛒 Заказать", callback_data=f"order_{product_id}"),
        InlineKeyboardButton(text="◀️ Назад", callback_data="catalog")
    )
    return builder.as_markup()

# ================= СТАРТ =================
@dp.message(Command("start"))
async def start(message: Message):
    await message.answer(
        "🇨🇳 <b>ИМПОРТНЫЙ АГРЕГАТОР</b>\n\n"
        "🚪 Двери | 🧱 Покрытия | 🛋 Мебель\n"
        "🇨🇳 Прямые поставки из Китая\n\n"
        "📌 <b>Как сделать заказ:</b>\n"
        "1. Выберите товар из каталога\n"
        "2. Нажмите «Заказать»\n"
        "3. Наш менеджер свяжется с вами\n"
        "4. После согласования заказ подтвердится\n\n"
        "⬇️ Выберите действие:",
        parse_mode="HTML",
        reply_markup=main_menu()
    )

# ================= КАТАЛОГ =================
@dp.callback_query(F.data == "catalog")
async def show_catalog(callback: CallbackQuery):
    await callback.message.edit_text(
        "📂 <b>Выберите категорию:</b>",
        parse_mode="HTML",
        reply_markup=categories_menu()
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("cat_"))
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
    
    builder = InlineKeyboardBuilder()
    for prod_id, name, price in products:
        builder.row(InlineKeyboardButton(
            text=f"{name} - {price}",
            callback_data=f"prod_{prod_id}"
        ))
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="catalog"))
    
    await callback.message.edit_text(
        f"📂 <b>{category}</b>\nВыберите товар:",
        parse_mode="HTML",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("prod_"))
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
    
    text = f"📦 <b>{name}</b>\n\n"
    text += f"📝 {desc}\n\n"
    text += f"💰 {price}\n\n"
    text += "🔄 Для заказа нажмите кнопку ниже.\n"
    text += "Менеджер свяжется с вами для уточнения деталей."
    
    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=product_buttons(product_id)
    )
    await callback.answer()

# ================= ОФОРМЛЕНИЕ ЗАКАЗА (КЛИЕНТ) =================
@dp.callback_query(F.data.startswith("order_"))
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
    await state.update_data(product_id=product_id)
    
    await callback.message.answer(
        f"🛒 <b>Оформление заказа</b>\n\n"
        f"Товар: {product[0]}\n\n"
        f"Введите <b>количество</b> (например: 2, 5, 10):",
        parse_mode="HTML"
    )
    await state.set_state(OrderStates.waiting_for_quantity)
    await callback.answer()

@dp.message(OrderStates.waiting_for_quantity)
async def process_quantity(message: Message, state: FSMContext):
    try:
        quantity = int(message.text)
        if quantity <= 0:
            await message.answer("❌ Количество должно быть больше 0. Попробуйте снова:")
            return
    except ValueError:
        await message.answer("❌ Введите число. Например: 2, 5, 10")
        return
    
    data = await state.get_data()
    product_name = data.get('product_name')
    user_id = message.from_user.id
    username = message.from_user.username or "без username"
    
    # Сохраняем заказ в БД
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
    
    # Отправляем уведомление админам
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                f"🆕 <b>НОВЫЙ ЗАКАЗ #{order_id}</b>\n\n"
                f"👤 Клиент: @{username} (ID: {user_id})\n"
                f"📦 Товар: {product_name}\n"
                f"🔢 Количество: {quantity}\n"
                f"💰 Цена: уточняется\n"
                f"📅 Время: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
                f"📌 Свяжитесь с клиентом для согласования.\n"
                f"После согласования используйте команду:\n"
                f"<code>/confirm {username} {product_name} {quantity} 15000</code>",
                parse_mode="HTML"
            )
        except:
            pass
    
    await message.answer(
        f"✅ <b>Заказ #{order_id} оформлен!</b>\n\n"
        f"📦 Товар: {product_name}\n"
        f"🔢 Количество: {quantity}\n\n"
        f"📞 Наш менеджер свяжется с вами в ближайшее время\n"
        f"для уточнения цены и сроков доставки.\n\n"
        f"Статус заказа можно отслеживать в разделе «Мои заказы».",
        parse_mode="HTML",
        reply_markup=main_menu()
    )
    
    await state.clear()

# ================= МОИ ЗАКАЗЫ (КЛИЕНТ) =================
@dp.callback_query(F.data == "my_orders")
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
            "📋 <b>У вас пока нет заказов</b>\n\n"
            "Перейдите в каталог и оформите первый заказ!",
            parse_mode="HTML",
            reply_markup=main_menu()
        )
        await callback.answer()
        return
    
    text = "📋 <b>МОИ ЗАКАЗЫ</b>\n\n"
    
    for order in orders:
        order_id, product, qty, price, status, created, confirmed = order
        
        status_emoji = {
            'новый': '🟡',
            'в обработке': '🟠',
            'подтверждён': '🟢',
            'отменён': '🔴'
        }.get(status, '⚪')
        
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
@dp.message(Command("confirm"))
async def confirm_order(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ У вас нет прав для подтверждения заказов")
        return
    
    parts = message.text.split(maxsplit=4)
    if len(parts) < 5:
        await message.answer(
            "❌ Неправильный формат!\n\n"
            "Используйте:\n"
            "<code>/confirm @username товар количество цена</code>\n\n"
            "Пример:\n"
            "<code>/confirm @ivanov Дверь Венеция 2 15000</code>",
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
        await message.answer(
            f"❌ Заказ не найден для @{username} с товаром {product_name} и количеством {quantity}.\n"
            f"Возможно заказ уже обработан или не существует."
        )
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
            f"📅 Дата подтверждения: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
            f"🤝 Спасибо за заказ!\n"
            f"Следите за статусом в разделе «Мои заказы».",
            parse_mode="HTML"
        )
    except:
        pass
    
    await message.answer(
        f"✅ <b>Заказ #{order_id} подтверждён!</b>\n\n"
        f"👤 Клиент: @{username}\n"
        f"📦 Товар: {product_name}\n"
        f"🔢 Количество: {quantity}\n"
        f"💰 Цена: {price} руб.\n\n"
        f"Клиент получил уведомление.",
        parse_mode="HTML"
    )

# ================= ОТМЕНА ЗАКАЗА (АДМИН) =================
@dp.message(Command("cancel"))
async def cancel_order(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ Нет прав")
        return
    
    parts = message.text.split(maxsplit=2)
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
        await message.answer(f"✅ Отменены заказы для @{username}")
    else:
        await message.answer(f"❌ Нет активных заказов для @{username}")

# ================= СВЯЗЬ С МЕНЕДЖЕРОМ =================
@dp.callback_query(F.data == "contact_manager")
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
        "📞 <b>Менеджер свяжется с вами!</b>\n\n"
        "Ожидайте сообщения в ближайшее время.\n"
        "Мы ответим на все вопросы по товарам, ценам и доставке.",
        parse_mode="HTML",
        reply_markup=main_menu()
    )
    await callback.answer()

# ================= ВОЗВРАТ В ГЛАВНОЕ =================
@dp.callback_query(F.data == "main_menu")
async def back_main(callback: CallbackQuery):
    await callback.message.edit_text(
        "🇨🇳 <b>ИМПОРТНЫЙ АГРЕГАТОР</b>\n\n"
        "🚪 Двери | 🧱 Покрытия | 🛋 Мебель\n"
        "🇨🇳 Прямые поставки из Китая\n\n"
        "⬇️ Выберите действие:",
        parse_mode="HTML",
        reply_markup=main_menu()
    )
    await callback.answer()

# ================= АДМИНКА: ДОБАВЛЕНИЕ ТОВАРОВ =================
@dp.message(Command("add"))
async def cmd_add(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ Нет прав")
        return
    await message.answer("Введите <b>категорию</b> (Двери, Настенные покрытия, Напольные покрытия, Мебель, Другое):", parse_mode="HTML")
    await state.set_state(AdminStates.waiting_for_category)

@dp.message(AdminStates.waiting_for_category)
async def add_category(message: Message, state: FSMContext):
    await state.update_data(category=message.text)
    await message.answer("Введите <b>название</b> товара:", parse_mode="HTML")
    await state.set_state(AdminStates.waiting_for_name)

@dp.message(AdminStates.waiting_for_name)
async def add_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("Введите <b>описание</b> товара:", parse_mode="HTML")
    await state.set_state(AdminStates.waiting_for_description)

@dp.message(AdminStates.waiting_for_description)
async def add_description(message: Message, state: FSMContext):
    await state.update_data(description=message.text)
    await message.answer("Введите <b>цену</b> (например: от 15000 руб.):", parse_mode="HTML")
    await state.set_state(AdminStates.waiting_for_price)

@dp.message(AdminStates.waiting_for_price)
async def add_price(message: Message, state: FSMContext):
    data = await state.get_data()
    
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO products (category, name, description, price) VALUES (?, ?, ?, ?)",
        (data['category'], data['name'], data['description'], message.text)
    )
    conn.commit()
    conn.close()
    
    await message.answer("✅ Товар добавлен в каталог!")
    await state.clear()

# ================= ЗАПУСК =================
async def main():
    logging.basicConfig(level=logging.INFO)
    print("🚀 Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
