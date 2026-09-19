import os
import random
import sqlite3
import telebot
from telebot.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton
)

TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_USERNAME = "flaybbe"   # без @
ADMIN_ID = None              # определится, когда админ напишет /start

bot = telebot.TeleBot(TOKEN)

# ---------- БАЗА ----------
conn = sqlite3.connect("clicker.db", check_same_thread=False)
cur = conn.cursor()
cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    balance INTEGER DEFAULT 0,
    total_clicks INTEGER DEFAULT 0,
    banned INTEGER DEFAULT 0
)
""")
conn.commit()

def get_user(uid):
    cur.execute("SELECT user_id, username, first_name, balance, total_clicks, banned FROM users WHERE user_id=?", (uid,))
    return cur.fetchone()

def create_user(uid, username, first_name):
    cur.execute("INSERT OR IGNORE INTO users (user_id, username, first_name) VALUES (?,?,?)",
                (uid, username, first_name))
    conn.commit()

def is_banned(uid):
    u = get_user(uid)
    return u and u[5] == 1

def add_balance(uid, amount):
    cur.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (amount, uid))
    conn.commit()

def add_click(uid):
    cur.execute("UPDATE users SET balance = balance + 1, total_clicks = total_clicks + 1 WHERE user_id=?", (uid,))
    conn.commit()

def find_by_username(username):
    username = username.replace("@", "").lower()
    cur.execute("SELECT user_id FROM users WHERE LOWER(username)=?", (username,))
    row = cur.fetchone()
    return row[0] if row else None

def set_ban(uid, banned):
    cur.execute("UPDATE users SET banned=? WHERE user_id=?", (banned, uid))
    conn.commit()

def get_top(limit=10):
    cur.execute("SELECT first_name, username, total_clicks FROM users ORDER BY total_clicks DESC LIMIT ?", (limit,))
    return cur.fetchall()

def get_all_users():
    cur.execute("SELECT user_id FROM users")
    return [r[0] for r in cur.fetchall()]

# ---------- КЛАВИАТУРЫ ----------
def main_menu(uid):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(KeyboardButton("💰 Играть"))
    kb.row(KeyboardButton("👤 Мой профиль"), KeyboardButton("🏆 Топ кликеров"))
    kb.row(KeyboardButton("💵 Пополнить $"), KeyboardButton("🆘 Поддержка"))
    if ADMIN_ID and uid == ADMIN_ID:
        kb.row(KeyboardButton("🔧 Админ-панель"))
    return kb

def clicker_kb():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(KeyboardButton("💵 Кликнуть (+$1)"))
    kb.row(KeyboardButton("🎭 Докс за $500"))
    kb.row(KeyboardButton("🔙 В меню"))
    return kb

def back_menu():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(KeyboardButton("🔙 В меню"))
    return kb

def admin_menu():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(KeyboardButton("💰 Выдать $"))
    kb.row(KeyboardButton("📢 Рассылка"))
    kb.row(KeyboardButton("🚫 Забанить"), KeyboardButton("✅ Разбанить"))
    kb.row(KeyboardButton("🔙 В меню"))
    return kb

# ---------- /start ----------
@bot.message_handler(commands=["start"])
def start(message):
    global ADMIN_ID
    uid = message.from_user.id

    if message.from_user.username and message.from_user.username.lower() == ADMIN_USERNAME.lower():
        ADMIN_ID = uid

    create_user(uid, message.from_user.username, message.from_user.first_name)

    if is_banned(uid):
        bot.send_message(uid, "🚫 Вы забанены и не можете пользоваться ботом.")
        return

    bot.send_message(
        uid,
        f"Привет, {message.from_user.first_name}!\n\n"
        "Это долларовый кликер 💵\n"
        "Жми «💰 Играть» и зарабатывай!",
        reply_markup=main_menu(uid)
    )

# ---------- 💰 ИГРАТЬ ----------
@bot.message_handler(func=lambda m: m.text == "💰 Играть")
def play(message):
    uid = message.from_user.id
    if is_banned(uid):
        bot.send_message(uid, "🚫 Вы забанены.")
        return
    u = get_user(uid)
    bot.send_message(
        uid,
        f"💵 Баланс: ${u[3]}\n\nЖми кнопку и зарабатывай!",
        reply_markup=clicker_kb()
    )

@bot.message_handler(func=lambda m: m.text == "💵 Кликнуть (+$1)")
def click(message):
    uid = message.from_user.id
    if is_banned(uid):
        return
    add_click(uid)
    u = get_user(uid)
    bot.send_message(uid, f"💵 +$1\nБаланс: ${u[3]}")

# ---------- 🎭 ДОКС ----------
@bot.message_handler(func=lambda m: m.text == "🎭 Докс за $500")
def doks(message):
    uid = message.from_user.id
    if is_banned(uid):
        return
    u = get_user(uid)
    if u[3] < 500:
        bot.send_message(uid, f"❌ Нужно $500. У тебя: ${u[3]}")
        return
    add_balance(uid, -500)

    names = ["Алексей", "Дмитрий", "Иван", "Максим", "Артём", "Кирилл"]
    cities = ["Москва", "Питер", "Казань", "Сочи", "Омск", "Тверь"]
    years = random.randint(1990, 2005)
    months = random.randint(1, 12)
    days = random.randint(1, 28)
    fake_uid = random.randint(100000000, 999999999)

    text = (
        "🎭 <b>Фейковый докс</b> (вымышленные данные)\n\n"
        f"👤 Имя: {random.choice(names)}\n"
        f"🎂 Дата рождения: {days:02d}.{months:02d}.{years}\n"
        f"🏙 Город: {random.choice(cities)}\n"
        f"🆔 ID: {fake_uid}\n"
        f"📱 Телефон: +7 9{random.randint(10,99)} {random.randint(100,999)}-{random.randint(10,99)}-{random.randint(10,99)}\n\n"
        "⚠️ Все данные случайны и не относятся к реальным людям."
    )
    bot.send_message(uid, text, parse_mode="HTML")
    bot.send_message(uid, "✅ С баланса списано $500.")

# ---------- 👤 ПРОФИЛЬ ----------
@bot.message_handler(func=lambda m: m.text == "👤 Мой профиль")
def profile(message):
    uid = message.from_user.id
    u = get_user(uid)
    if not u:
        bot.send_message(uid, "Сначала /start")
        return
    uname = f"@{u[1]}" if u[1] else "—"
    status = "🚫 Забанен" if u[5] else "✅ Активен"
    bot.send_message(
        uid,
        f"👤 <b>Профиль</b>\n\n"
        f"Имя: {u[2]}\n"
        f"Юзернейм: {uname}\n"
        f"ID: <code>{uid}</code>\n"
        f"Баланс: ${u[3]}\n"
        f"Всего накликано: {u[4]}\n"
        f"Статус: {status}",
        parse_mode="HTML"
    )

# ---------- 🏆 ТОП ----------
@bot.message_handler(func=lambda m: m.text == "🏆 Топ кликеров")
def top(message):
    rows = get_top(10)
    if not rows:
        bot.send_message(message.chat.id, "Пока никого нет.")
        return
    text = "🏆 <b>Топ-10 кликеров</b>\n\n"
    for i, (name, uname, clicks) in enumerate(rows, 1):
        u = f"@{uname}" if uname else name
        text += f"{i}. {u} — {clicks} кликов\n"
    bot.send_message(message.chat.id, text, parse_mode="HTML")

# ---------- 💵 ПОПОЛНИТЬ ----------
@bot.message_handler(func=lambda m: m.text == "💵 Пополнить $")
def top_up(message):
    text = (
        "💵 <b>Пополнение баланса</b>\n\n"
        "$1 — 10₽\n"
        "Максимум за 1 раз: $10000\n\n"
        f"Чтобы купить — напишите: @{ADMIN_USERNAME}"
    )
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton(f"✍️ Написать @{ADMIN_USERNAME}", url=f"https://t.me/{ADMIN_USERNAME}"))
    bot.send_message(message.chat.id, text, parse_mode="HTML", reply_markup=kb)

# ---------- 🆘 ПОДДЕРЖКА ----------
@bot.message_handler(func=lambda m: m.text == "🆘 Поддержка")
def support(message):
    bot.send_message(
        message.chat.id,
        "📨 Напишите свою жалобу или вопрос:",
        reply_markup=back_menu()
    )
    bot.register_next_step_handler(message, send_support)

def send_support(message):
    if message.text == "🔙 В меню":
        bot.send_message(message.chat.id, "Главное меню:", reply_markup=main_menu(message.from_user.id))
        return
    if not ADMIN_ID:
        bot.send_message(message.chat.id, f"Напишите напрямую: @{ADMIN_USERNAME}")
        return
    uname = f"@{message.from_user.username}" if message.from_user.username else "—"
    text = (
        f"🆘 <b>Обращение в поддержку</b>\n\n"
        f"От: {uname} (ID: <code>{message.from_user.id}</code>)\n"
        f"Имя: {message.from_user.first_name}\n\n"
        f"Сообщение:\n{message.text}"
    )
    bot.send_message(ADMIN_ID, text, parse_mode="HTML")
    bot.send_message(message.chat.id, "✅ Отправлено администратору.", reply_markup=main_menu(message.from_user.id))

# ---------- 🔙 В МЕНЮ ----------
@bot.message_handler(func=lambda m: m.text == "🔙 В меню")
def back(message):
    bot.send_message(message.chat.id, "Главное меню:", reply_markup=main_menu(message.from_user.id))

# ---------- 🔧 АДМИН-ПАНЕЛЬ ----------
@bot.message_handler(func=lambda m: m.text == "🔧 Админ-панель")
def admin(message):
    if message.from_user.id != ADMIN_ID:
        return
    bot.send_message(message.chat.id, "🔧 Админ-панель", reply_markup=admin_menu())

@bot.message_handler(func=lambda m: m.text == "💰 Выдать $")
def give_money(message):
    if message.from_user.id != ADMIN_ID:
        return
    bot.send_message(message.chat.id, "Введи юзернейм (без @):", reply_markup=back_menu())
    bot.register_next_step_handler(message, give_money_step1)

def give_money_step1(message):
    if message.text == "🔙 В меню":
        bot.send_message(message.chat.id, "Меню:", reply_markup=main_menu(message.from_user.id))
        return
    target = find_by_username(message.text)
    if not target:
        bot.send_message(message.chat.id, "❌ Пользователь не найден.", reply_markup=admin_menu())
        return
    bot.send_message(message.chat.id, "Введи сумму от 1 до 500000:")
    bot.register_next_step_handler(message, lambda m: give_money_step2(m, target))

def give_money_step2(message, target):
    try:
        amount = int(message.text)
    except:
        bot.send_message(message.chat.id, "❌ Введи число.", reply_markup=admin_menu())
        return
    if amount < 1 or amount > 500000:
        bot.send_message(message.chat.id, "❌ Сумма от 1 до 500000.", reply_markup=admin_menu())
        return
    add_balance(target, amount)
    bot.send_message(message.chat.id, f"✅ Выдано ${amount} пользователю ID {target}", reply_markup=admin_menu())
    try:
        bot.send_message(target, f"💰 Вам выдано ${amount}")
    except:
        pass

@bot.message_handler(func=lambda m: m.text == "📢 Рассылка")
def broadcast(message):
    if message.from_user.id != ADMIN_ID:
        return
    bot.send_message(message.chat.id, "Введи текст рассылки:", reply_markup=back_menu())
    bot.register_next_step_handler(message, broadcast_step)

def broadcast_step(message):
    if message.text == "🔙 В меню":
        bot.send_message(message.chat.id, "Меню:", reply_markup=main_menu(message.from_user.id))
        return
    users = get_all_users()
    ok = 0
    for uid in users:
        try:
            bot.send_message(uid, f"📢 {message.text}")
            ok += 1
        except:
            pass
    bot.send_message(message.chat.id, f"✅ Разослано {ok} пользователям.", reply_markup=admin_menu())

@bot.message_handler(func=lambda m: m.text == "🚫 Забанить")
def ban(message):
    if message.from_user.id != ADMIN_ID:
        return
    bot.send_message(message.chat.id, "Введи юзернейм (без @):", reply_markup=back_menu())
    bot.register_next_step_handler(message, ban_step)

def ban_step(message):
    if message.text == "🔙 В меню":
        bot.send_message(message.chat.id, "Меню:", reply_markup=main_menu(message.from_user.id))
        return
    target = find_by_username(message.text)
    if not target:
        bot.send_message(message.chat.id, "❌ Не найден.", reply_markup=admin_menu())
        return
    set_ban(target, 1)
    bot.send_message(message.chat.id, f"🚫 Забанен ID {target}", reply_markup=admin_menu())
    try:
        bot.send_message(target, "🚫 Вы забанены.")
    except:
        pass

@bot.message_handler(func=lambda m: m.text == "✅ Разбанить")
def unban(message):
    if message.from_user.id != ADMIN_ID:
        return
    bot.send_message(message.chat.id, "Введи юзернейм (без @):", reply_markup=back_menu())
    bot.register_next_step_handler(message, unban_step)

def unban_step(message):
    if message.text == "🔙 В меню":
        bot.send_message(message.chat.id, "Меню:", reply_markup=main_menu(message.from_user.id))
        return
    target = find_by_username(message.text)
    if not target:
        bot.send_message(message.chat.id, "❌ Не найден.", reply_markup=admin_menu())
        return
    set_ban(target, 0)
    bot.send_message(message.chat.id, f"✅ Разбанен ID {target}", reply_markup=admin_menu())
    try:
        bot.send_message(target, "✅ Вы разбанены.")
    except:
        pass

# ---------- ЗАПУСК ----------
print("Бот запущен...")
bot.infinity_polling()