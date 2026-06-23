import sqlite3
import requests
from datetime import datetime
import telebot
from telebot import types
import time
import threading
import logging
from flask import Flask, request
import os

# ================= КОНФИГ =================
API_TOKEN = '8657473893:AAGngc2DPixc3rLDZsw52BGMORgOfjMfxk4'
ADMIN_IDS = [7293950231, 1372806444]
RENDER_URL = 'https://chinadirect.onrender.com'
CHANNEL_ID = -1003944933503

bot = telebot.TeleBot(API_TOKEN)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# ================= ВЕБ-СЕРВЕР (чтобы Render не усыплял) =================
app = Flask(__name__)

@app.route('/')
def health_check():
    """Просто отвечаем, что бот жив"""
    return f"🤖 Бот работает! {get_current_datetime()}", 200

@app.route('/ping')
def ping():
    """Проверка работоспособности"""
    return f"PONG! {get_current_datetime()}", 200

def run_web_server():
    """Запускаем веб-сервер в отдельном потоке"""
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)

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
            created_at TEXT,
            confirmed_by INTEGER DEFAULT 0,
            confirmed_at TEXT,
            completed_at TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# ================= КЛАВИАТУРЫ =================
def main_menu():
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    btn1 = types.InlineKeyboardButton("🛒 Сделать заказ", callback_data="new_order")
    btn2 = types.InlineKeyboardButton("📋 Мои заказы", callback_data="my_orders")
    btn3 = types.InlineKeyboardButton("📞 Связаться с менеджером", callback_data="contact")
    keyboard.add(btn1, btn2, btn3)
    return keyboard

def categories_menu():
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    categories = ["🚪 Двери", "🧱 Покрытия", "🛋 Мебель", "🪟 Другое"]
    for cat in categories:
        keyboard.add(types.InlineKeyboardButton(cat, callback_data=f"cat_{cat}"))
    keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back"))
    return keyboard

def admin_menu():
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        types.InlineKeyboardButton("🆕 Новые заказы", callback_data="admin_new"),
        types.InlineKeyboardButton("🔄 Активные заказы", callback_data="admin_active"),
        types.InlineKeyboardButton("✅ Завершённые заказы", callback_data="admin_done")
    )
    return keyboard

def order_actions(order_id, user_id, product_name):
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton("✅ Подтвердить", callback_data=f"confirm_{order_id}_{user_id}_{product_name}"),
        types.InlineKeyboardButton("❌ Отменить", callback_data=f"reject_{order_id}_{user_id}")
    )
    keyboard.add(
        types.InlineKeyboardButton("💬 Написать клиенту", callback_data=f"message_{user_id}_{order_id}")
    )
    return keyboard

# ================= ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =================
def get_current_datetime():
    return datetime.now().strftime('%d.%m.%Y %H:%M:%S')

# ================= ОБРАБОТЧИКИ КЛИЕНТА =================
@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(
        message.chat.id,
        f"🇨🇳 <b>ЗДРАВСТВУЙТЕ - МЫ ИМПОРТНЫЙ АГРЕГАТОР</b>\n\n"
        f"🚪 Двери | 🧱 Покрытия | 🛋 Мебель\n"
        f"🇨🇳 Прямые поставки из Китая\n\n"
        f"📅 {get_current_datetime()}\n\n"
        f"Выберите действие:",
        parse_mode="HTML",
        reply_markup=main_menu()
    )
    
    if message.from_user.id in ADMIN_IDS:
        bot.send_message(
            message.chat.id,
            f"👑 <b>Панель администратора</b>\n\n"
            f"📅 {get_current_datetime()}",
            parse_mode="HTML",
            reply_markup=admin_menu()
        )

@bot.callback_query_handler(func=lambda call: call.data == "new_order")
def new_order(call):
    bot.edit_message_text(
        f"📂 <b>Выберите категорию:</b>\n\n"
        f"📅 {get_current_datetime()}",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        parse_mode="HTML",
        reply_markup=categories_menu()
    )
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("cat_"))
def choose_category(call):
    category = call.data.replace("cat_", "")
    msg = bot.send_message(
        call.message.chat.id,
        f"📂 <b>{category}</b>\n\n"
        f"Введите <b>название</b> товара:\n\n"
        f"📅 {get_current_datetime()}",
        parse_mode="HTML"
    )
    bot.register_next_step_handler(msg, get_product_name, category)
    bot.answer_callback_query(call.id)

def get_product_name(message, category):
    product_name = message.text
    user_id = message.from_user.id
    username = message.from_user.username or str(user_id)
    created_at = get_current_datetime()
    
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO orders (user_id, username, product_name, quantity, status, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, username, product_name, "уточняется", "новый", created_at)
    )
    order_id = cur.lastrowid
    conn.commit()
    conn.close()
    
    for admin_id in ADMIN_IDS:
        try:
            bot.send_message(
                admin_id,
                f"🆕 <b>НОВЫЙ ЗАКАЗ #{order_id}</b>\n\n"
                f"👤 Клиент: @{username} (ID: {user_id})\n"
                f"📂 Категория: {category}\n"
                f"📦 Товар: {product_name}\n"
                f"📅 Время: {created_at}",
                parse_mode="HTML",
                reply_markup=order_actions(order_id, user_id, product_name)
            )
        except:
            pass
    
    bot.send_message(
        message.chat.id,
        f"✅ <b>Заказ #{order_id} принят!</b>\n\n"
        f"📦 {product_name}\n"
        f"📅 {created_at}",
        parse_mode="HTML",
        reply_markup=main_menu()
    )

# ================= ОСТАЛЬНЫЕ КОМАНДЫ =================
@bot.callback_query_handler(func=lambda call: call.data == "my_orders")
def my_orders(call):
    user_id = call.from_user.id
    
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute(
        "SELECT id, product_name, quantity, status, created_at, confirmed_at, completed_at FROM orders "
        "WHERE user_id=? ORDER BY id DESC",
        (user_id,)
    )
    orders = cur.fetchall()
    conn.close()
    
    if not orders:
        bot.edit_message_text(
            f"📋 <b>У вас пока нет заказов</b>\n\n"
            f"📅 {get_current_datetime()}",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            parse_mode="HTML",
            reply_markup=main_menu()
        )
        bot.answer_callback_query(call.id)
        return
    
    text = f"📋 <b>МОИ ЗАКАЗЫ</b>\n\n"
    text += f"📅 {get_current_datetime()}\n"
    text += "─" * 20 + "\n\n"
    
    for order in orders:
        order_id, product, qty, status, created_at, confirmed_at, completed_at = order
        status_emoji = {
            'новый': '🟡',
            'активный': '🟠',
            'подтверждён': '🟢',
            'отменён': '🔴'
        }.get(status, '⚪')
        
        text += f"{status_emoji} <b>Заказ #{order_id}</b>\n"
        text += f"📦 {product}\n"
        text += f"🔢 {qty}\n"
        text += f"📅 Создан: {created_at}\n"
        
        if confirmed_at:
            text += f"📅 Подтверждён: {confirmed_at}\n"
        if completed_at:
            text += f"📅 Завершён: {completed_at}\n"
            
        text += f"📌 Статус: <b>{status.upper()}</b>\n"
        text += "─" * 20 + "\n"
    
    bot.edit_message_text(
        text,
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        parse_mode="HTML",
        reply_markup=main_menu()
    )
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "contact")
def contact_manager(call):
    user_id = call.from_user.id
    username = call.from_user.username or str(user_id)
    contact_time = get_current_datetime()
    
    for admin_id in ADMIN_IDS:
        try:
            bot.send_message(
                admin_id,
                f"📞 <b>ЗАПРОС СВЯЗИ</b>\n\n"
                f"👤 Клиент: @{username} (ID: {user_id})\n"
                f"📅 Время запроса: {contact_time}\n\n"
                f"Напишите ему: https://t.me/{username if username != str(user_id) else ''}",
                parse_mode="HTML",
                reply_markup=types.InlineKeyboardMarkup().add(
                    types.InlineKeyboardButton("💬 Написать клиенту", callback_data=f"message_{user_id}_0")
                )
            )
        except:
            pass
    
    bot.edit_message_text(
        f"📞 <b>Менеджер свяжется с вами в ближайшее время!</b>\n\n"
        f"📅 {get_current_datetime()}",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        parse_mode="HTML",
        reply_markup=main_menu()
    )
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "back")
def back(call):
    bot.edit_message_text(
        f"🇨🇳 <b>ИМПОРТНЫЙ АГРЕГАТОР</b>\n\n"
        f"🚪 Двери | 🧱 Покрытия | 🛋 Мебель\n"
        f"🇨🇳 Прямые поставки из Китая\n\n"
        f"📅 {get_current_datetime()}\n\n"
        f"Выберите действие:",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        parse_mode="HTML",
        reply_markup=main_menu()
    )
    bot.answer_callback_query(call.id)

# ================= АДМИНСКАЯ ПАНЕЛЬ =================
@bot.callback_query_handler(func=lambda call: call.data.startswith("admin_"))
def admin_panel(call):
    status_map = {
        "admin_new": "новый",
        "admin_active": "активный",
        "admin_done": "подтверждён"
    }
    
    status = status_map.get(call.data, "новый")
    
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    if status == "подтверждён":
        cur.execute(
            "SELECT id, user_id, username, product_name, quantity, created_at, confirmed_at, completed_at, confirmed_by FROM orders "
            "WHERE status IN ('подтверждён', 'отменён') ORDER BY id DESC"
        )
    else:
        cur.execute(
            "SELECT id, user_id, username, product_name, quantity, created_at, confirmed_at, completed_at, confirmed_by FROM orders "
            "WHERE status=? ORDER BY id DESC",
            (status,)
        )
    orders = cur.fetchall()
    conn.close()
    
    if not orders:
        bot.edit_message_text(
            f"📋 <b>Нет заказов в статусе «{status}»</b>\n\n"
            f"📅 {get_current_datetime()}",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            parse_mode="HTML",
            reply_markup=admin_menu()
        )
        bot.answer_callback_query(call.id)
        return
    
    text = f"📋 <b>ЗАКАЗЫ В СТАТУСЕ «{status.upper()}»</b>\n\n"
    text += f"📅 {get_current_datetime()}\n"
    text += "─" * 20 + "\n\n"
    
    for order in orders:
        order_id, user_id, username, product, qty, created_at, confirmed_at, completed_at, confirmed_by = order
        text += f"🆔 #{order_id}\n"
        text += f"👤 {username} (ID: {user_id})\n"
        text += f"📦 {product}\n"
        text += f"🔢 {qty}\n"
        text += f"📅 Создан: {created_at}\n"
        
        if confirmed_at:
            text += f"📅 Подтверждён: {confirmed_at}\n"
        if completed_at:
            text += f"📅 Завершён: {completed_at}\n"
            
        if confirmed_by:
            try:
                admin_info = bot.get_chat(confirmed_by)
                admin_name = admin_info.username or str(confirmed_by)
                text += f"👑 Менеджер: @{admin_name}\n"
            except:
                text += f"👑 Менеджер: {confirmed_by}\n"
        text += "─" * 20 + "\n"
    
    bot.edit_message_text(
        text,
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        parse_mode="HTML",
        reply_markup=admin_menu()
    )
    bot.answer_callback_query(call.id)

# ================= НАПИСАТЬ КЛИЕНТУ =================
@bot.callback_query_handler(func=lambda call: call.data.startswith("message_"))
def message_client(call):
    parts = call.data.split("_")
    user_id = int(parts[1])
    order_id = int(parts[2]) if len(parts) > 2 else 0
    
    try:
        chat = bot.get_chat(user_id)
        username = chat.username
    except:
        username = None
    
    text = f"💬 <b>Связаться с клиентом</b>\n\n"
    text += f"📅 {get_current_datetime()}\n"
    text += f"👤 ID: {user_id}\n"
    
    if username:
        text += f"👤 @{username}\n"
        text += f"🔗 <a href='https://t.me/{username}'>Написать в Telegram</a>"
    else:
        text += f"⚠️ У клиента нет username.\n"
        text += f"Но вы можете написать ему, используя ID: {user_id}\n\n"
        text += f"📌 <b>Как это сделать:</b>\n"
        text += f"1. Откройте Telegram\n"
        text += f"2. Начните новый чат\n"
        text += f"3. Введите ID в поиске или используйте бота @userinfobot\n"
        text += f"4. Или просто скопируйте ID и используйте для отправки"
    
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    if username:
        keyboard.add(types.InlineKeyboardButton("💬 Написать в Telegram", url=f"https://t.me/{username}"))
    else:
        try:
            bot.send_message(user_id, f"📩 Менеджер хочет связаться с вами. Напишите ему, пожалуйста.\n\n📅 {get_current_datetime()}")
            keyboard.add(types.InlineKeyboardButton("✅ Сообщение отправлено", callback_data="msg_sent"))
        except:
            keyboard.add(types.InlineKeyboardButton("❌ Не могу отправить", callback_data="msg_fail"))
    
    if order_id > 0:
        keyboard.add(types.InlineKeyboardButton("◀️ Назад к заказу", callback_data=f"back_to_order_{order_id}"))
    
    bot.edit_message_text(
        text,
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        parse_mode="HTML",
        reply_markup=keyboard
    )
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "msg_sent")
def msg_sent(call):
    bot.answer_callback_query(call.id, "✅ Сообщение отправлено!", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data == "msg_fail")
def msg_fail(call):
    bot.answer_callback_query(call.id, "❌ Не удалось отправить. Клиент не писал боту.", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data.startswith("back_to_order_"))
def back_to_order(call):
    order_id = int(call.data.split("_")[3])
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute("SELECT user_id, username, product_name, quantity, status, created_at, confirmed_at, completed_at FROM orders WHERE id=?", (order_id,))
    order = cur.fetchone()
    conn.close()
    
    if order:
        user_id, username, product, qty, status, created_at, confirmed_at, completed_at = order
        text = f"🆔 <b>Заказ #{order_id}</b>\n\n"
        text += f"👤 {username} (ID: {user_id})\n"
        text += f"📦 {product}\n"
        text += f"🔢 {qty}\n"
        text += f"📅 Создан: {created_at}\n"
        
        if confirmed_at:
            text += f"📅 Подтверждён: {confirmed_at}\n"
        if completed_at:
            text += f"📅 Завершён: {completed_at}\n"
            
        text += f"📌 Статус: <b>{status.upper()}</b>"
        
        bot.edit_message_text(
            text,
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            parse_mode="HTML",
            reply_markup=order_actions(order_id, user_id, product)
        )
    bot.answer_callback_query(call.id)

# ================= ПОДТВЕРЖДЕНИЕ ЗАКАЗА =================
@bot.callback_query_handler(func=lambda call: call.data.startswith("confirm_"))
def confirm_order(call):
    if call.from_user.id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "⛔ Нет прав", show_alert=True)
        return
    
    parts = call.data.split("_")
    order_id = int(parts[1])
    user_id = int(parts[2])
    product_name = parts[3]
    
    msg = bot.send_message(
        call.message.chat.id,
        f"📦 <b>Заказ #{order_id}</b>\n\n"
        f"Товар: {product_name}\n"
        f"📅 {get_current_datetime()}\n\n"
        f"Введите <b>количество</b>:",
        parse_mode="HTML"
    )
    bot.register_next_step_handler(msg, process_confirm_quantity, order_id, user_id, product_name, call.from_user.id)
    bot.answer_callback_query(call.id)

def process_confirm_quantity(message, order_id, user_id, product_name, admin_id):
    try:
        quantity = int(message.text)
        if quantity <= 0:
            bot.reply_to(message, "❌ Количество должно быть больше 0.")
            return
    except ValueError:
        bot.reply_to(message, "❌ Введите число.")
        return
    
    confirmed_at = get_current_datetime()
    completed_at = get_current_datetime()
    
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute(
        "UPDATE orders SET quantity=?, status='подтверждён', confirmed_by=?, confirmed_at=?, completed_at=? WHERE id=?",
        (quantity, admin_id, confirmed_at, completed_at, order_id)
    )
    conn.commit()
    
    cur.execute("SELECT user_id, username, product_name, quantity FROM orders WHERE id=?", (order_id,))
    order_data = cur.fetchone()
    conn.close()
    
    if order_data:
        user_id, username, product_name, qty = order_data
        
        try:
            bot.send_message(
                user_id,
                f"✅ <b>ЗАКАЗ #{order_id} ПОДТВЕРЖДЁН</b>\n\n"
                f"📦 {product_name}\n"
                f"🔢 {qty} шт.\n"
                f"📅 {confirmed_at}",
                parse_mode="HTML"
            )
        except:
            pass
        
        try:
            admin_info = bot.get_chat(admin_id)
            admin_name = admin_info.username or str(admin_id)
        except:
            admin_name = str(admin_id)
        
        try:
            channel_msg = (
                f"✅ <b>ЗАКАЗ #{order_id} ЗАВЕРШЁН</b>\n\n"
                f"👤 Клиент: @{username} (ID: {user_id})\n"
                f"👑 Менеджер: @{admin_name}\n"
                f"📦 Товар: {product_name}\n"
                f"🔢 Количество: {qty} шт.\n"
                f"📅 Создан: {confirmed_at}\n"
                f"📅 Завершён: {completed_at}"
            )
            
            bot.send_message(CHANNEL_ID, channel_msg, parse_mode="HTML")
            logging.info(f"Заказ #{order_id} отправлен в канал {CHANNEL_ID}")
            
        except Exception as e:
            logging.error(f"Ошибка отправки в канал {CHANNEL_ID}: {e}")
            for admin_id in ADMIN_IDS:
                try:
                    bot.send_message(admin_id, f"⚠️ Не удалось отправить заказ #{order_id} в канал. Ошибка: {e}")
                except:
                    pass
    
    bot.reply_to(
        message,
        f"✅ Заказ #{order_id} подтверждён\n\n"
        f"📦 {product_name}\n"
        f"🔢 {quantity} шт.\n"
        f"📅 {confirmed_at}",
        parse_mode="HTML"
    )

# ================= ОТМЕНА ЗАКАЗА =================
@bot.callback_query_handler(func=lambda call: call.data.startswith("reject_"))
def reject_order(call):
    if call.from_user.id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "⛔ Нет прав", show_alert=True)
        return
    
    parts = call.data.split("_")
    order_id = int(parts[1])
    user_id = int(parts[2])
    canceled_at = get_current_datetime()
    
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute("UPDATE orders SET status='отменён', confirmed_by=?, completed_at=? WHERE id=?", (call.from_user.id, canceled_at, order_id))
    conn.commit()
    conn.close()
    
    try:
        bot.send_message(
            user_id,
            f"❌ <b>ЗАКАЗ #{order_id} ОТМЕНЁН</b>\n\n"
            f"📅 Время отмены: {canceled_at}\n\n"
            f"По вопросам обращайтесь к менеджеру.",
            parse_mode="HTML"
        )
    except:
        pass
    
    bot.edit_message_text(
        f"✅ Заказ #{order_id} отменён\n\n📅 {canceled_at}",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id
    )
    bot.answer_callback_query(call.id)

# ================= ЗАПУСК =================
if __name__ == "__main__":
    logging.info(f"🚀 Бот запущен {get_current_datetime()}")
    logging.info(f"Канал ID: {CHANNEL_ID}")
    
    # Запускаем веб-сервер в отдельном потоке
    web_thread = threading.Thread(target=run_web_server, daemon=True)
    web_thread.start()
    logging.info("🌐 Веб-сервер запущен на порту 10000")
    
    # Запускаем бота
    bot.infinity_polling()
