import sqlite3
import requests
from datetime import datetime
import telebot
from telebot import types
import time
import threading

# ================= КОНФИГ =================
API_TOKEN = '8657473893:AAGngc2DPixc3rLDZsw52BGMORgOfjMfxk4'
ADMIN_IDS = [7293950231]
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

# ================= ОБРАБОТЧИКИ =================
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
    username = message.from_user.username or "без username"
    
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
    
    for admin_id in ADMIN_IDS:
        try:
            bot.send_message(
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
            'утверждён': '🟢',
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
    for admin_id in ADMIN_IDS:
        try:
            bot.send_message(
                admin_id,
                f"📞 Клиент @{call.from_user.username or 'без username'} хочет связаться"
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

# ================= АДМИН-КОМАНДЫ =================
@bot.message_handler(commands=['approve'])
def approve_order(message):
    if message.from_user.id not in ADMIN_IDS:
        bot.reply_to(message, "⛔ Нет прав")
        return
    
    parts = message.text.split(maxsplit=3)
    if len(parts) < 4:
        bot.reply_to(
            message,
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
        bot.reply_to(
            message,
            f"❌ Не найден активный заказ для @{username} с товаром «{product_name}»"
        )
        conn.close()
        return
    
    order_id, user_id = order
    
    cur.execute(
        "UPDATE orders SET quantity=?, status='утверждён' WHERE id=?",
        (quantity, order_id)
    )
    conn.commit()
    conn.close()
    
    try:
        bot.send_message(
            user_id,
            f"✅ <b>ЗАКАЗ #{order_id} УТВЕРЖДЁН!</b>\n\n"
            f"📦 Товар: {product_name}\n"
            f"🔢 Количество: {quantity} шт.\n\n"
            f"Менеджер свяжется с вами для уточнения деталей.",
            parse_mode="HTML"
        )
    except:
        pass
    
    bot.reply_to(
        message,
        f"✅ Заказ #{order_id} утверждён!\n"
        f"👤 @{username}\n"
        f"📦 {product_name}\n"
        f"🔢 {quantity} шт."
    )

@bot.message_handler(commands=['cancel'])
def cancel_order(message):
    if message.from_user.id not in ADMIN_IDS:
        bot.reply_to(message, "⛔ Нет прав")
        return
    
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(
            message,
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
        bot.reply_to(message, f"✅ Отменены все активные заказы для @{username}")
    else:
        bot.reply_to(message, f"❌ Нет активных заказов для @{username}")

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
    # Запускаем пингование в фоновом потоке
    ping_thread = threading.Thread(target=ping_self, daemon=True)
    ping_thread.start()
    
    # Запускаем бота
    print("🚀 Бот запущен!")
    bot.infinity_polling()
