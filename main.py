import sqlite3
import requests
from datetime import datetime
import telebot
from telebot import types
import time
import threading

# ================= КОНФИГ =================
API_TOKEN = '8657473893:AAGngc2DPixc3rLDZsw52BGMORgOfjMfxk4'
ADMIN_IDS = [7293950231, 1372806444]  # Добавлен второй админ
RENDER_URL = 'https://chinadirect.onrender.com'

bot = telebot.TeleBot(API_TOKEN)

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

def message_client_actions(user_id, order_id):
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        types.InlineKeyboardButton("📩 Отправить сообщение", callback_data=f"send_msg_{user_id}_{order_id}"),
        types.InlineKeyboardButton("◀️ Назад к заказу", callback_data=f"back_to_order_{order_id}")
    )
    return keyboard

# ================= ОБРАБОТЧИКИ КЛИЕНТА =================
@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(
        message.chat.id,
        "🇨🇳 <b>ИМПОРТНЫЙ АГРЕГАТОР</b>\n\n"
        "🚪 Двери | 🧱 Покрытия | 🛋 Мебель\n"
        "🇨🇳 Прямые поставки из Китая\n\n"
        "Выберите действие:",
        parse_mode="HTML",
        reply_markup=main_menu()
    )
    
    # Если это админ, показываем админ-меню
    if message.from_user.id in ADMIN_IDS:
        bot.send_message(
            message.chat.id,
            "👑 <b>Панель администратора</b>",
            parse_mode="HTML",
            reply_markup=admin_menu()
        )

@bot.callback_query_handler(func=lambda call: call.data == "new_order")
def new_order(call):
    bot.edit_message_text(
        "📂 <b>Выберите категорию:</b>",
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
        "Введите <b>название</b> товара, который хотите заказать:\n"
        "Например: Дверь Венеция, Ламинат 8мм, Диван угловой",
        parse_mode="HTML"
    )
    bot.register_next_step_handler(msg, get_product_name, category)
    bot.answer_callback_query(call.id)

def get_product_name(message, category):
    product_name = message.text
    user_id = message.from_user.id
    username = message.from_user.username or str(user_id)
    
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
    
    # Отправляем уведомление админам
    for admin_id in ADMIN_IDS:
        try:
            bot.send_message(
                admin_id,
                f"🆕 <b>НОВЫЙ ЗАКАЗ #{order_id}</b>\n\n"
                f"👤 Клиент: @{username} (ID: {user_id})\n"
                f"📂 Категория: {category}\n"
                f"📦 Товар: {product_name}\n"
                f"📅 Время: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
                f"Свяжитесь с клиентом и подтвердите заказ:",
                parse_mode="HTML",
                reply_markup=order_actions(order_id, user_id, product_name)
            )
        except:
            pass
    
    bot.send_message(
        message.chat.id,
        f"✅ <b>Заказ #{order_id} принят!</b>\n\n"
        f"📦 Товар: {product_name}\n\n"
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
        "SELECT id, product_name, quantity, status, created_at FROM orders "
        "WHERE user_id=? ORDER BY id DESC",
        (user_id,)
    )
    orders = cur.fetchall()
    conn.close()
    
    if not orders:
        bot.edit_message_text(
            "📋 <b>У вас пока нет заказов</b>",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            parse_mode="HTML",
            reply_markup=main_menu()
        )
        bot.answer_callback_query(call.id)
        return
    
    text = "📋 <b>МОИ ЗАКАЗЫ</b>\n\n"
    for order in orders:
        order_id, product, qty, status, created = order
        status_emoji = {
            'новый': '🟡',
            'активный': '🟠',
            'подтверждён': '🟢',
            'отменён': '🔴'
        }.get(status, '⚪')
        
        text += f"{status_emoji} <b>Заказ #{order_id}</b>\n"
        text += f"📦 {product}\n"
        text += f"🔢 {qty}\n"
        text += f"📅 {created}\n"
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
    
    for admin_id in ADMIN_IDS:
        try:
            bot.send_message(
                admin_id,
                f"📞 Клиент @{username} (ID: {user_id}) хочет связаться\n\n"
                f"Напишите ему: https://t.me/{username if username != str(user_id) else ''}",
                reply_markup=types.InlineKeyboardMarkup().add(
                    types.InlineKeyboardButton("💬 Написать клиенту", callback_data=f"message_{user_id}_0")
                )
            )
        except:
            pass
    
    bot.edit_message_text(
        "📞 <b>Менеджер свяжется с вами в ближайшее время!</b>",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        parse_mode="HTML",
        reply_markup=main_menu()
    )
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "back")
def back(call):
    bot.edit_message_text(
        "🇨🇳 <b>ИМПОРТНЫЙ АГРЕГАТОР</b>\n\n"
        "🚪 Двери | 🧱 Покрытия | 🛋 Мебель\n"
        "🇨🇳 Прямые поставки из Китая\n\n"
        "Выберите действие:",
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
            "SELECT id, user_id, username, product_name, quantity, created_at FROM orders "
            "WHERE status IN ('подтверждён', 'отменён') ORDER BY id DESC"
        )
    else:
        cur.execute(
            "SELECT id, user_id, username, product_name, quantity, created_at FROM orders "
            "WHERE status=? ORDER BY id DESC",
            (status,)
        )
    orders = cur.fetchall()
    conn.close()
    
    if not orders:
        bot.edit_message_text(
            f"📋 <b>Нет заказов в статусе «{status}»</b>",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            parse_mode="HTML",
            reply_markup=admin_menu()
        )
        bot.answer_callback_query(call.id)
        return
    
    text = f"📋 <b>ЗАКАЗЫ В СТАТУСЕ «{status.upper()}»</b>\n\n"
    for order in orders:
        order_id, user_id, username, product, qty, created = order
        text += f"🆔 #{order_id}\n"
        text += f"👤 {username} (ID: {user_id})\n"
        text += f"📦 {product}\n"
        text += f"🔢 {qty}\n"
        text += f"📅 {created}\n"
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
    
    # Проверяем, есть ли у клиента username
    try:
        chat = bot.get_chat(user_id)
        username = chat.username
    except:
        username = None
    
    text = f"💬 <b>Связаться с клиентом</b>\n\n"
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
        # Отправляем сообщение через бота (если клиент писал боту)
        try:
            bot.send_message(user_id, "📩 Менеджер хочет связаться с вами. Напишите ему, пожалуйста.")
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
    # Показываем информацию о заказе
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute("SELECT user_id, username, product_name, quantity, status, created_at FROM orders WHERE id=?", (order_id,))
    order = cur.fetchone()
    conn.close()
    
    if order:
        user_id, username, product, qty, status, created = order
        text = f"🆔 <b>Заказ #{order_id}</b>\n\n"
        text += f"👤 {username} (ID: {user_id})\n"
        text += f"📦 {product}\n"
        text += f"🔢 {qty}\n"
        text += f"📅 {created}\n"
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
        f"Товар: {product_name}\n\n"
        f"Введите <b>количество</b> (например: 2, 5, 10):",
        parse_mode="HTML"
    )
    bot.register_next_step_handler(msg, process_confirm_quantity, order_id, user_id, product_name)
    bot.answer_callback_query(call.id)

def process_confirm_quantity(message, order_id, user_id, product_name):
    try:
        quantity = int(message.text)
        if quantity <= 0:
            bot.reply_to(message, "❌ Количество должно быть больше 0.")
            return
    except ValueError:
        bot.reply_to(message, "❌ Введите число.")
        return
    
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute(
        "UPDATE orders SET quantity=?, status='подтверждён' WHERE id=?",
        (quantity, order_id)
    )
    conn.commit()
    conn.close()
    
    try:
        bot.send_message(
            user_id,
            f"✅ <b>ЗАКАЗ #{order_id} ПОДТВЕРЖДЁН!</b>\n\n"
            f"📦 Товар: {product_name}\n"
            f"🔢 Количество: {quantity} шт.\n\n"
            f"Менеджер свяжется с вами для уточнения деталей.",
            parse_mode="HTML"
        )
    except:
        pass
    
    bot.reply_to(
        message,
        f"✅ <b>Заказ #{order_id} подтверждён!</b>\n\n"
        f"📦 Товар: {product_name}\n"
        f"🔢 Количество: {quantity} шт.\n\n"
        f"Клиент получил уведомление.",
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
    
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute("UPDATE orders SET status='отменён' WHERE id=?", (order_id,))
    conn.commit()
    conn.close()
    
    try:
        bot.send_message(
            user_id,
            f"❌ <b>ЗАКАЗ #{order_id} ОТМЕНЁН</b>\n\n"
            f"По вопросам обращайтесь к менеджеру.",
            parse_mode="HTML"
        )
    except:
        pass
    
    bot.edit_message_text(
        f"✅ Заказ #{order_id} отменён",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id
    )
    bot.answer_callback_query(call.id)

# ================= КОМАНДЫ ДЛЯ АДМИНА (через текст) =================
@bot.message_handler(commands=['approve'])
def approve_order_text(message):
    if message.from_user.id not in ADMIN_IDS:
        bot.reply_to(message, "⛔ Нет прав")
        return
    
    parts = message.text.split(maxsplit=3)
    if len(parts) < 4:
        bot.reply_to(
            message,
            "❌ Используйте:\n"
            "<code>/approve @username товар количество</code>\n"
            "или\n"
            "<code>/approve 123456789 товар количество</code>",
            parse_mode="HTML"
        )
        return
    
    user_identifier = parts[1].replace('@', '')
    product_name = parts[2]
    quantity = parts[3]
    
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    
    cur.execute(
        "SELECT id, user_id FROM orders "
        "WHERE username=? AND product_name=? AND status='новый' "
        "ORDER BY id DESC LIMIT 1",
        (user_identifier, product_name)
    )
    order = cur.fetchone()
    
    if not order and user_identifier.isdigit():
        cur.execute(
            "SELECT id, user_id FROM orders "
            "WHERE user_id=? AND product_name=? AND status='новый' "
            "ORDER BY id DESC LIMIT 1",
            (int(user_identifier), product_name)
        )
        order = cur.fetchone()
    
    if not order:
        bot.reply_to(
            message,
            f"❌ Не найден активный заказ для @{user_identifier} или ID {user_identifier} с товаром «{product_name}»"
        )
        conn.close()
        return
    
    order_id, user_id = order
    
    cur.execute(
        "UPDATE orders SET quantity=?, status='подтверждён' WHERE id=?",
        (quantity, order_id)
    )
    conn.commit()
    conn.close()
    
    try:
        bot.send_message(
            user_id,
            f"✅ <b>ЗАКАЗ #{order_id} ПОДТВЕРЖДЁН!</b>\n\n"
            f"📦 Товар: {product_name}\n"
            f"🔢 Количество: {quantity} шт.\n\n"
            f"Менеджер свяжется с вами для уточнения деталей.",
            parse_mode="HTML"
        )
    except:
        pass
    
    bot.reply_to(
        message,
        f"✅ Заказ #{order_id} подтверждён!\n"
        f"👤 ID: {user_id}\n"
        f"📦 {product_name}\n"
        f"🔢 {quantity} шт."
    )

# ================= ПИНГОВАНИЕ =================
def ping_self():
    while True:
        try:
            response = requests.get(RENDER_URL, timeout=10)
            print(f"[PING] {datetime.now().strftime('%H:%M:%S')} - Status: {response.status_code}")
        except Exception as e:
            print(f"[PING ERROR] {e}")
        time.sleep(60)

# ================= ЗАПУСК =================
if __name__ == "__main__":
    ping_thread = threading.Thread(target=ping_self, daemon=True)
    ping_thread.start()
    print("🚀 Бот запущен!")
    bot.infinity_polling()
