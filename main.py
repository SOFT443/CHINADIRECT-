import asyncio
import logging
import sqlite3
import os
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton

# ================= КОНФИГУРАЦИЯ =================
API_TOKEN = '8657473893:AAGngc2DPixc3rLDZsw52BGMORgOfjMfxk4'  # Замени на свой токен от @BotFather
ADMIN_IDS = 7293950231  # Замени на свой Telegram ID (узнай у @userinfobot)

# Инициализация
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# ================= БАЗА ДАННЫХ =================
def init_db():
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    
    # Таблица товаров
    cur.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT,
            name TEXT,
            description TEXT,
            price TEXT,
            photo_path TEXT
        )
    ''')
    
    # Таблица корзины
    cur.execute('''
        CREATE TABLE IF NOT EXISTS cart (
            user_id INTEGER,
            product_id INTEGER,
            quantity INTEGER DEFAULT 1,
            PRIMARY KEY (user_id, product_id)
        )
    ''')
    
    conn.commit()
    conn.close()

init_db()

# ================= СОСТОЯНИЯ ДЛЯ ДОБАВЛЕНИЯ ТОВАРОВ =================
class AdminStates(StatesGroup):
    waiting_for_category = State()
    waiting_for_name = State()
    waiting_for_description = State()
    waiting_for_price = State()
    waiting_for_photo = State()

# ================= КЛАВИАТУРЫ =================
def main_menu():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📦 Каталог", callback_data="catalog"),
        InlineKeyboardButton(text="🛒 Корзина", callback_data="view_cart")
    )
    builder.row(
        InlineKeyboardButton(text="📞 Связаться с менеджером", callback_data="contact_manager")
    )
    return builder.as_markup()

def categories_menu():
    builder = InlineKeyboardBuilder()
    categories = [" Двери", " Покрытия", " Мебель", " Другое"]
    for cat in categories:
        builder.row(InlineKeyboardButton(text=cat, callback_data=f"cat_{cat}"))
    builder.row(InlineKeyboardButton(text="◀️ Главное меню", callback_data="main_menu"))
    return builder.as_markup()

def product_buttons(product_id):
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="➕ В корзину", callback_data=f"add_{product_id}"),
        InlineKeyboardButton(text="◀️ Назад", callback_data="catalog")
    )
    return builder.as_markup()

# ================= СТАРТ =================
@dp.message(Command("start"))
async def start(message: Message):
    await message.answer(
        "🇨🇳 Добро пожаловать в Импортный Агрегатор!\n\n"
        " Двери |  Покрытия |  Мебель\n"
        "🇨🇳 Прямые поставки из Китая\n\n"
        "Выберите действие:",
        reply_markup=main_menu()
    )

# ================= КАТАЛОГ =================
@dp.callback_query(F.data == "catalog")
async def show_catalog(callback: CallbackQuery):
    await callback.message.edit_text(
        "📂 Выберите категорию:",
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
        await callback.answer("Товаров пока нет", show_alert=True)
        return
    
    builder = InlineKeyboardBuilder()
    for prod_id, name, price in products:
        builder.row(InlineKeyboardButton(
            text=f"{name} - {price}",
            callback_data=f"prod_{prod_id}"
        ))
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="catalog"))
    
    await callback.message.edit_text(
        f"📂 {category}\nВыберите товар:",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("prod_"))
async def show_product(callback: CallbackQuery):
    product_id = int(callback.data.replace("prod_", ""))
    
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute("SELECT name, description, price, photo_path FROM products WHERE id=?", (product_id,))
    product = cur.fetchone()
    conn.close()
    
    if not product:
        await callback.answer("Товар не найден", show_alert=True)
        return
    
    name, desc, price, photo_path = product
    
    text = f"<b>{name}</b>\n\n📝 {desc}\n\n💰 {price}\n\n🕒 Точную цену и сроки уточняйте у менеджера"
    
    if photo_path and os.path.exists(photo_path):
        photo = FSInputFile(photo_path)
        await callback.message.delete()
        await callback.message.answer_photo(
            photo=photo,
            caption=text,
            parse_mode="HTML",
            reply_markup=product_buttons(product_id)
        )
    else:
        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=product_buttons(product_id)
        )
    await callback.answer()

# ================= КОРЗИНА =================
@dp.callback_query(F.data.startswith("add_"))
async def add_to_cart(callback: CallbackQuery):
    product_id = int(callback.data.replace("add_", ""))
    user_id = callback.from_user.id
    
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    
    cur.execute(
        "INSERT INTO cart (user_id, product_id, quantity) VALUES (?, ?, 1) "
        "ON CONFLICT(user_id, product_id) DO UPDATE SET quantity = quantity + 1",
        (user_id, product_id)
    )
    conn.commit()
    conn.close()
    
    await callback.answer("✅ Добавлено в корзину!", show_alert=True)

@dp.callback_query(F.data == "view_cart")
async def view_cart(callback: CallbackQuery):
    user_id = callback.from_user.id
    
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute('''
        SELECT p.name, p.price, c.quantity, p.id
        FROM cart c
        JOIN products p ON c.product_id = p.id
        WHERE c.user_id = ?
    ''', (user_id,))
    items = cur.fetchall()
    conn.close()
    
    if not items:
        await callback.answer("Корзина пуста", show_alert=True)
        return
    
    text = "🛒 <b>Ваша корзина:</b>\n\n"
    total = 0
    builder = InlineKeyboardBuilder()
    
    for name, price, qty, prod_id in items:
        # Извлекаем число из цены
        price_num = ''.join(filter(str.isdigit, price))
        if price_num:
            total += int(price_num) * qty
        text += f"• {name} x{qty} = {price}\n"
        builder.row(InlineKeyboardButton(
            text=f"❌ Убрать {name}",
            callback_data=f"remove_{prod_id}"
        ))
    
    text += f"\n<b>Примерная сумма:</b> {total} руб."
    
    builder.row(
        InlineKeyboardButton(text="📝 Оформить заказ", callback_data="checkout"),
        InlineKeyboardButton(text="◀️ Назад", callback_data="catalog")
    )
    
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup())
    await callback.answer()

@dp.callback_query(F.data.startswith("remove_"))
async def remove_from_cart(callback: CallbackQuery):
    product_id = int(callback.data.replace("remove_", ""))
    user_id = callback.from_user.id
    
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute("DELETE FROM cart WHERE user_id=? AND product_id=?", (user_id, product_id))
    conn.commit()
    conn.close()
    
    await callback.answer("🗑 Удалено", show_alert=True)
    await view_cart(callback)

# ================= ОФОРМЛЕНИЕ ЗАКАЗА =================
@dp.callback_query(F.data == "checkout")
async def checkout(callback: CallbackQuery):
    user_id = callback.from_user.id
    
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute('''
        SELECT p.name, p.price, c.quantity
        FROM cart c
        JOIN products p ON c.product_id = p.id
        WHERE c.user_id = ?
    ''', (user_id,))
    items = cur.fetchall()
    
    cur.execute("DELETE FROM cart WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()
    
    if not items:
        await callback.answer("Корзина пуста", show_alert=True)
        return
    
    order_text = f"🆕 <b>НОВЫЙ ЗАКАЗ!</b>\n\n"
    order_text += f"👤 Клиент: @{callback.from_user.username or 'нет username'} (ID: {user_id})\n"
    order_text += f"📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
    order_text += "<b>Товары:</b>\n"
    
    total = 0
    for name, price, qty in items:
        price_num = ''.join(filter(str.isdigit, price))
        if price_num:
            total += int(price_num) * qty
        order_text += f"• {name} x{qty} = {price}\n"
    
    order_text += f"\n<b>Итого:</b> {total} руб."
    
    # Отправляем админам
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, order_text, parse_mode="HTML")
        except:
            pass
    
    await callback.message.edit_text(
        "✅ <b>Заказ принят!</b>\n\n"
        "Свяжемся с вами для уточнения деталей.\n"
        "Спасибо! 🇨🇳",
        parse_mode="HTML",
        reply_markup=main_menu()
    )
    await callback.answer()

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
        "📞 Менеджер свяжется с вами в ближайшее время!",
        reply_markup=main_menu()
    )
    await callback.answer()

# ================= АДМИНКА: ДОБАВЛЕНИЕ ТОВАРОВ =================
@dp.message(Command("add"))
async def cmd_add(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ Нет прав")
        return
    await message.answer("Введите <b>категорию</b> (Двери, Покрытия, Мебель, Другое):", parse_mode="HTML")
    await state.set_state(AdminStates.waiting_for_category)

@dp.message(AdminStates.waiting_for_category)
async def add_category(message: Message, state: FSMContext):
    await state.update_data(category=message.text)
    await message.answer("Введите <b>название</b> товара:", parse_mode="HTML")
    await state.set_state(AdminStates.waiting_for_name)

@dp.message(AdminStates.waiting_for_name)
async def add_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("Введите <b>описание</b>:", parse_mode="HTML")
    await state.set_state(AdminStates.waiting_for_description)

@dp.message(AdminStates.waiting_for_description)
async def add_description(message: Message, state: FSMContext):
    await state.update_data(description=message.text)
    await message.answer("Введите <b>цену</b> (например: от 5000 руб.):", parse_mode="HTML")
    await state.set_state(AdminStates.waiting_for_price)

@dp.message(AdminStates.waiting_for_price)
async def add_price(message: Message, state: FSMContext):
    await state.update_data(price=message.text)
    await message.answer("📸 Отправьте <b>фото</b> товара:", parse_mode="HTML")
    await state.set_state(AdminStates.waiting_for_photo)

@dp.message(AdminStates.waiting_for_photo, F.photo)
async def add_photo(message: Message, state: FSMContext):
    data = await state.get_data()
    
    # Создаём папку для фото
    if not os.path.exists("images"):
        os.makedirs("images")
    
    # Скачиваем фото
    photo = message.photo[-1]
    file = await bot.get_file(photo.file_id)
    file_path = f"images/{photo.file_id}.jpg"
    await bot.download_file(file.file_path, file_path)
    
    # Сохраняем в БД
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO products (category, name, description, price, photo_path) VALUES (?, ?, ?, ?, ?)",
        (data['category'], data['name'], data['description'], data['price'], file_path)
    )
    conn.commit()
    conn.close()
    
    await message.answer("✅ Товар добавлен!")
    await state.clear()

# ================= НАЗАД В ГЛАВНОЕ =================
@dp.callback_query(F.data == "main_menu")
async def back_main(callback: CallbackQuery):
    await callback.message.edit_text(
        "🇨🇳 Главное меню:",
        reply_markup=main_menu()
    )
    await callback.answer()

# ================= ЗАПУСК =================
async def main():
    logging.basicConfig(level=logging.INFO)
    print("🚀 Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
