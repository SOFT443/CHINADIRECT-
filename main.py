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
        InlineKeyboardButton(text="📄 Скачать каталог", callback_data="catalog"),
        InlineKeyboardButton(text="🛒 Корзина", callback_data="view_cart")
    )
    builder.row(
        InlineKeyboardButton(text="📞 Связаться с менеджером", callback_data="contact_manager")
    )
    return builder.as_markup()

def catalog_format_menu():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📄 PDF (красивый)", callback_data="get_pdf"),
        InlineKeyboardButton(text="📊 Excel (для опта)", callback_data="get_excel")
    )
    builder.row(
        InlineKeyboardButton(text="📦 ZIP (фото+прайс)", callback_data="get_zip")
    )
    builder.row(
        InlineKeyboardButton(text="◀️ Главное меню", callback_data="main_menu")
    )
    return builder.as_markup()

def categories_menu():
    builder = InlineKeyboardBuilder()
    categories = ["🚪 Двери", "🧱 Покрытия", "🛋 Мебель", "🪟 Другое"]
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
        "🚪 Двери | 🧱 Покрытия | 🛋 Мебель\n"
        "🇨🇳 Прямые поставки из Китая\n\n"
        "📥 Скачайте наш каталог или свяжитесь с менеджером:",
        reply_markup=main_menu()
    )

# ================= КАТАЛОГ (ВЫБОР ФОРМАТА) =================
@dp.callback_query(F.data == "catalog")
async def show_catalog_options(callback: CallbackQuery):
    await callback.message.edit_text(
        "📄 <b>Выберите формат каталога:</b>\n\n"
        "• PDF — красивый каталог для презентации\n"
        "• Excel — для сортировки и фильтрации\n"
        "• ZIP — все фото отдельно + прайс-лист\n\n"
        "Все файлы содержат фото, названия и цены товаров.",
        parse_mode="HTML",
        reply_markup=catalog_format_menu()
    )
    await callback.answer()

# ================= ГЕНЕРАЦИЯ И ОТПРАВКА КАТАЛОГА =================
@dp.callback_query(F.data == "get_pdf")
async def send_pdf_catalog(callback: CallbackQuery):
    await callback.answer("⏳ Генерирую PDF...", show_alert=True)
    
    try:
        from generate_catalog import create_catalog_pdf
        pdf_path = create_catalog_pdf()
        
        if not pdf_path or not os.path.exists(pdf_path):
            await callback.message.answer("❌ Ошибка создания PDF. Попробуйте позже.")
            return
        
        doc = FSInputFile(pdf_path)
        await callback.message.answer_document(
            document=doc,
            caption="📄 <b>Каталог товаров (PDF)</b>\n\n"
                    "📥 Скачайте и выберите товары.\n"
                    "💬 Для заказа напишите артикулы менеджеру.\n\n"
                    "🇨🇳 Цены и сроки уточняйте индивидуально.",
            parse_mode="HTML"
        )
        await callback.message.delete()
        
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка: {str(e)}")

@dp.callback_query(F.data == "get_excel")
async def send_excel_catalog(callback: CallbackQuery):
    await callback.answer("⏳ Генерирую Excel...", show_alert=True)
    
    try:
        from generate_excel import create_excel_catalog
        excel_path = create_excel_catalog()
        
        if not excel_path or not os.path.exists(excel_path):
            await callback.message.answer("❌ Ошибка создания Excel. Попробуйте позже.")
            return
        
        doc = FSInputFile(excel_path)
        await callback.message.answer_document(
            document=doc,
            caption="📊 <b>Прайс-лист (Excel)</b>\n\n"
                    "📥 Скачайте для фильтрации и сортировки.\n"
                    "💬 Для заказа напишите артикулы менеджеру.\n\n"
                    "🇨🇳 Цены и сроки уточняйте индивидуально.",
            parse_mode="HTML"
        )
        await callback.message.delete()
        
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка: {str(e)}")

@dp.callback_query(F.data == "get_zip")
async def send_zip_catalog(callback: CallbackQuery):
    await callback.answer("⏳ Создаю архив...", show_alert=True)
    
    try:
        from generate_zip import create_zip_catalog
        zip_path = create_zip_catalog()
        
        if not zip_path or not os.path.exists(zip_path):
            await callback.message.answer("❌ Ошибка создания ZIP. Попробуйте позже.")
            return
        
        doc = FSInputFile(zip_path)
        await callback.message.answer_document(
            document=doc,
            caption="📦 <b>Архив с каталогом (ZIP)</b>\n\n"
                    "📁 Внутри архива:\n"
                    "• 📊 catalog.csv — прайс-лист\n"
                    "• 🖼 images/ — все фото товаров\n"
                    "• 📄 README.txt — инструкция\n\n"
                    "💬 Для заказа напишите артикулы менеджеру.\n\n"
                    "🇨🇳 Цены и сроки уточняйте индивидуально.",
            parse_mode="HTML"
        )
        await callback.message.delete()
        
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка: {str(e)}")

# ================= КОРЗИНА (БАЗОВАЯ, ОПЦИОНАЛЬНО) =================
@dp.callback_query(F.data == "view_cart")
async def view_cart(callback: CallbackQuery):
    await callback.answer("🛒 Корзина пока в разработке. Используйте каталог для заказа!", show_alert=True)

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
        "📞 Менеджер свяжется с вами в ближайшее время!\n"
        "Ожидайте звонка или сообщения.",
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
    await message.answer("Введите <b>описание</b> товара:", parse_mode="HTML")
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

# ================= АДМИНКА: ОБНОВЛЕНИЕ КАТАЛОГА =================
@dp.message(Command("update"))
async def update_catalog(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ Нет прав")
        return
    
    await message.answer("⏳ Обновляю каталоги...")
    
    try:
        from generate_catalog import create_catalog_pdf
        from generate_excel import create_excel_catalog
        from generate_zip import create_zip_catalog
        
        pdf = create_catalog_pdf()
        excel = create_excel_catalog()
        zip_file = create_zip_catalog()
        
        result = "✅ <b>Все каталоги обновлены!</b>\n\n"
        result += f"📄 PDF: {'✅' if pdf else '❌'}\n"
        result += f"📊 Excel: {'✅' if excel else '❌'}\n"
        result += f"📦 ZIP: {'✅' if zip_file else '❌'}\n"
        
        await message.answer(result, parse_mode="HTML")
        
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")

# ================= НАЗАД В ГЛАВНОЕ =================
@dp.callback_query(F.data == "main_menu")
async def back_main(callback: CallbackQuery):
    await callback.message.edit_text(
        "🇨🇳 Главное меню:\nВыберите действие:",
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
