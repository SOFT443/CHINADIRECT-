import sqlite3
import requests
from datetime import datetime
import telebot
from telebot import types
import time
import threading
import logging

# ================= КОНФИГ =================
API_TOKEN = '8657473893:AAGngc2DPixc3rLDZsw52BGMORgOfjMfxk4'
ADMIN_IDS = [7293950231, 1372806444]
RENDER_URL = 'https://chinadirect.onrender.com'
CHANNEL_ID = -1003944933503  # ID чата для дублирования завершённых заказов

bot = telebot.TeleBot(API_TOKEN)
logging.basicConfig(level=logging.INFO)

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

# ================= КЛАВИАТУРЫ ДЛЯ КЛИЕНТА =================
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

# ================= КЛАВИАТУРЫ ДЛЯ АДМИНА =================
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

def get_current_date():
    return datetime.now().strftime('%d.%m.%Y')

def get_current_time():
    return datetime.now().strftime('%H:%M:%S')

# ================= ОБРАБОТЧИКИ КЛИЕНТА =================
@bot.message_handler(commands=['start'])
def start(message):
    # Показываем клиенту меню
    bot.send_message(
        message.chat.id,
        f"🇨🇳 <b>ИМПОРТНЫЙ АГРЕГАТОР</b>\n\n"
        f"🚪 Двери | 🧱 Покрытия | 🛋 Мебель\n"
        f"🇨🇳 Прямые поставки из Китая\n\n"
        f"📅 {get_current_date()} {get_current_time()}\n\n"
        f"Выберите действие:",
        parse_mode="HTML",
        reply_markup=main_menu()
    )
    
    # Если это админ, показываем только админ-панель (без клиентского меню)
    if message.from_user.id in ADMIN_IDS:
        bot.send_message(
            message.chat.id,
            f"👑 <b>Панель администратора</b>\n\n"
            f"📅 {get_current_date()} {get_current_time()}",
            parse_mode="HTML",
            reply_markup=admin_menu()
        )

@bot.callback_query_handler(func=lambda call: call.data == "new_order")
def new_order(call):
    bot.edit_message_text(
        f"📂 <b>Выберите категорию:</b>\n\n"
        f"📅 {get_current_date()} {get_current_time()}",
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
        f"Введите <b>название</b> товара, который хотите заказать:\n"
        f"Например: Дверь Венеция, Ламинат 8мм, Диван угловой\n\n"
        f"📅 {get_current_date()} {get_current_time()}",
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
    
    # Отправляем уведомление админам
    for admin_id in ADMIN_IDS:
        try:
            bot.send_message(
                admin_id,
                f"🆕 <b>НОВЫЙ ЗАКАЗ #{order_id}</b>\n\n"
                f"👤 Клиент: @{username} (ID: {user_id})\n"
                f"📂 Категория: {category}\n"
                f"📦 Товар: {product_name}\n"
                f"📅 Время создания: {created_at}\n\n"
                f"Свяжитесь с клиентом и подтвердите заказ:",
                parse_mode="HTML",
                reply_markup=order_actions(order_id, user_id, product_name)
            )
        except:
            pass
    
    bot.send_message(
        message.chat.id,
        f"✅ <b>Заказ #{order_id} принят!</b>\n\n"
        f"📦 Товар: {product_name}\n"
        f"📅 Время заказа: {created_at}\n\n"
        f"Менеджер свяжется с вами в ближайшее время.\n"
        f"Статус заказа можно отслеживать в разделе «Мои заказы».",
        parse_mode="HTML",
        reply_markup=main_menu()
    )

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
            f"📅 {get_current_date()} {get_current_time()}",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            parse_mode="HTML",
            reply_markup=main_menu()
        )
        bot.answer_callback_query(call.id)
        return
    
    text = f"📋 <b>МОИ ЗАКАЗЫ</b>\n\n"
    text += f"📅 {get_current_date()} {get_current_time()}\n"
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
        f"📅 {get_current_date()} {get_current_time()}",
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
        f"📅 {get_current_date()} {get_current_time()}\n\n"
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
            f"📅 {get_current_date()} {get_current_time()}",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            parse_mode="HTML",
            reply_markup=admin_menu()
        )
        bot.answer_callback_query(call.id)
        return
    
    text = f"📋 <b>ЗАКАЗЫ В СТАТУСЕ «{status.upper()}»</b>\n\n"
    text += f"📅 {get_current_date()} {get_current_time()}\n"
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
    text += f"📅 {get_current_date()} {get_current_time()}\n"
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

# ================= ПОДТВЕРЖДЕНИЕ ЗАКАЗА (через кнопку) =================
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
        f"📅 {get_current_date()} {get_current_time()}\n\n"
        f"Введите <b>количество</b> (например: 2, 5, 10):",
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
    
    # Получаем данные заказа для дублирования
    cur.execute("SELECT user_id, username, product_name, quantity FROM orders WHERE id=?", (order_id,))
    order_data = cur.fetchone()
    conn.close()
    
    if order_data:
        user_id, username, product_name, qty = order_data
        
        # Отправляем уведомление клиенту с датой и временем
        try:
            bot.send_message(
                user_id,
                f"✅ <b>ЗАКАЗ #{order_id} ПОДТВЕРЖДЁН!</b>\n\n"
                f"📦 Товар: {product_name}\n"
                f"🔢 Количество: {qty} шт.\n"
                f"📅 Дата подтверждения: {confirmed_at}\n\n"
                f"Менеджер свяжется с вами для уточнения деталей.",
                parse_mode="HTML"
            )
        except:
            pass
        
        # Получаем инфо о менеджере
        try:
            admin_info = bot.get_chat(admin_id)
            admin_name = admin_info.username or str(admin_id)
        except:
            admin_name = str(admin_id)
        
        # Дублируем в канал
        try:
            bot.send_message(
                CHANNEL_ID,
                f"✅ <b>ЗАКАЗ #{order_id} ЗАВЕРШЁН</b>\n\n"
                f"👤 <b>Клиент:</b> @{username} (ID: {user_id})\n"
                f"👑 <b>Менеджер:</b> @{admin_name}\n"
                f"📦 <b>Товар:</b> {product_name}\n"
                f"🔢 <b>Количество:</b> {qty} шт.\n"
                f"📅 <b>Время создания:</b> {confirmed_at}\n"
                f"📅 <b>Время завершения:</b> {completed_at}",
                parse_mode="HTML"
            )
        except Exception as e:
            logging.error(f"Не удалось отправить в канал: {e}")
    
    bot.reply_to(
        message,
        f"✅ <b>Заказ #{order_id} подтверждён!</b>\n\n"
        f"📦 Товар: {product_name}\n"
        f"🔢 Количество: {quantity} шт.\n"
        f"📅 Время подтверждения: {confirmed_at}\n\n"
        f"Клиент получил уведомление.\n"
        f"Заказ продублирован в канал.",
        parse_mode="HTML"
    )

# ================= ОТМЕНА ЗАКАЗА (через кнопку) =================
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

# ================= ПИНГОВАНИЕ =================
def ping_self():
    """Каждые 30 секунд пингует себя, чтобы Render не засыпал"""
    while True:
        try:
            response = requests.get(RENDER_URL, timeout=10)
            logging.info(f"[PING] {get_current_datetime()} - Status: {response.status_code}")
        except Exception as e:
            logging.error(f"[PING ERROR] {get_current_datetime()} - {e}")
        time.sleep(30)

# ================= ЗАПУСК =================
if __name__ == "__main__":
    logging.info(f"🚀 Бот запущен! {get_current_datetime()}")
    
    # Запускаем пингование в фоновом потоке
    ping_thread = threading.Thread(target=ping_self, daemon=True)
    ping_thread.start()
    
    # Запускаем бота
    bot.infinity_polling()
