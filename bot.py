import os
import random
import sqlite3
import telebot
from telebot.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton
)

TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_USERNAME = "flaybbe"
ADMIN_ID = int(os.environ.get("ADMIN_ID", 0))
ADMIN_ID2 = int(os.environ.get("ADMIN_ID2", 0))

ADMINS = [x for x in [ADMIN_ID, ADMIN_ID2] if x]

def is_admin(uid):
    return uid in ADMINS

bot = telebot.TeleBot(TOKEN)

# ---------- УЛУЧШЕНИЯ ----------
# name: (множитель, цена)
UPGRADES = {
    "x2":  {"mult": 2,  "price": 500,      "emoji": "⚡"},
    "x5":  {"mult": 5,  "price": 5_000,    "emoji": "🔥"},
    "x10": {"mult": 10, "price": 50_000,   "emoji": "💥"},
    "x50": {"mult": 50, "price": 500_000,  "emoji": "💎"},
}

# ---------- БАЗА (SQLite) ----------
conn = sqlite3.connect("clicker.db", check_same_thread=False)
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    balance INTEGER DEFAULT 0,
    total_clicks INTEGER DEFAULT 0,
    banned INTEGER DEFAULT 0,
    click_mult INTEGER DEFAULT 1
)
""")
cur.execute("""
CREATE TABLE IF NOT EXISTS user_upgrades (
    user_id INTEGER,
    upgrade_key TEXT,
    PRIMARY KEY (user_id, upgrade_key)
)
""")
cur.execute("""
CREATE TABLE IF NOT EXISTS promos (
    code TEXT PRIMARY KEY,
    amount INTEGER,
    max_uses INTEGER,
    uses INTEGER DEFAULT 0
)
""")
cur.execute("""
CREATE TABLE IF NOT EXISTS promo_used (
    code TEXT,
    user_id INTEGER,
    PRIMARY KEY (code, user_id)
)
""")
conn.commit()

# ---------- ЮЗЕРЫ ----------
def get_user(uid):
    cur.execute("SELECT user_id, username, first_name, balance, total_clicks, banned, click_mult FROM users WHERE user_id=?", (uid,))
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

def add_clicks(uid, amount):
    cur.execute("UPDATE users SET balance = balance + ?, total_clicks = total_clicks + ? WHERE user_id=?",
                (amount, amount, uid))
    conn.commit()

def add_click(uid):
    """Клик с учётом множителя"""
    u = get_user(uid)
    if not u:
        return 0
    mult = u[6] or 1
    cur.execute("UPDATE users SET balance = balance + ?, total_clicks = total_clicks + 1 WHERE user_id=?",
                (mult, uid))
    conn.commit()
    return mult

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

# ---------- УЛУЧШЕНИЯ (логика) ----------
def has_upgrade(uid, key):
    cur.execute("SELECT 1 FROM user_upgrades WHERE user_id=? AND upgrade_key=?", (uid, key))
    return cur.fetchone() is not None

def buy_upgrade(uid, key):
    if key not in UPGRADES:
        return "❌ Неизвестное улучшение."
    if has_upgrade(uid, key):
        return "❌ У тебя уже есть это улучшение."
    u = get_user(uid)
    price = UPGRADES[key]["price"]
    if u[3] < price:
        return f"❌ Не хватает денег. Нужно ${price}, у тебя ${u[3]}."
    # Списываем деньги
    cur.execute("UPDATE users SET balance = balance - ? WHERE user_id=?", (price, uid))
    # Добавляем улучшение
    cur.execute("INSERT INTO user_upgrades (user_id, upgrade_key) VALUES (?,?)", (uid, key))
    # Пересчитываем множитель (перемножаем все улучшения)
    cur.execute("SELECT upgrade_key FROM user_upgrades WHERE user_id=?", (uid,))
    keys = [r[0] for r in cur.fetchall()]
    mult = 1
    for k in keys:
        mult *= UPGRADES[k]["mult"]
    cur.execute("UPDATE users SET click_mult=? WHERE user_id=?", (mult, uid))
    conn.commit()
    return f"✅ Куплено улучшение! Теперь клик даёт ${mult}."

def upgrades_list(uid):
    return [k for k in UPGRADES if has_upgrade(uid, k)]

# ---------- ПРОМО ----------
def create_promo(code, amount, max_uses):
    try:
        cur.execute("INSERT INTO promos (code, amount, max_uses, uses) VALUES (?,?,?,0)",
                    (code.upper(), amount, max_uses))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False

def get_promo(code):
    cur.execute("SELECT code, amount, max_uses, uses FROM promos WHERE code=?", (code.upper(),))
    return cur.fetchone()

def promo_already_used(code, uid):
    cur.execute("SELECT 1 FROM promo_used WHERE code=? AND user_id=?", (code.upper(), uid))
    return cur.fetchone() is not None

def activate_promo(code, uid):
    p = get_promo(code)
    if not p:
        return "❌ Промокод не найден."
    if p[2] != -1 and p[3] >= p[2]:
        return "❌ Промокод закончился."
    if promo_already_used(code, uid):
        return "❌ Ты уже активировал этот промокод."
    cur.execute("UPDATE promos SET uses = uses + 1 WHERE code=?", (code.upper(),))
    cur.execute("INSERT INTO promo_used (code, user_id) VALUES (?,?)", (code.upper(), uid))
    add_balance(uid, p[1])
    conn.commit()
    return f"✅ Промокод активирован! +${p[1]}"

def delete_promo(code):
    cur.execute("DELETE FROM promos WHERE code=?", (code.upper(),))
    cur.execute("DELETE FROM promo_used WHERE code=?", (code.upper(),))
    conn.commit()

def list_promos():
    cur.execute("SELECT code, amount, max_uses, uses FROM promos")
    return cur.fetchall()

# ---------- КЛАВИАТУРЫ ----------
def main_menu(uid):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(KeyboardButton("💰 Играть"))
    kb.row(KeyboardButton("👤 Мой профиль"), KeyboardButton("🏆 Топ кликеров"))
    kb.row(KeyboardButton("💵 Пополнить $"), KeyboardButton("🎭 Докс"))
    kb.row(KeyboardButton("🎟 Промокод"), KeyboardButton("🆘 Поддержка"))
    if is_admin(uid):
        kb.row(KeyboardButton("🔧 Админ-панель"))
    return kb

def clicker_kb():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(KeyboardButton("💵 Кликнуть"))
    kb.row(KeyboardButton("⚡ Улучшения"))
    kb.row(KeyboardButton("🔙 В меню"))
    return kb

def upgrades_kb(uid):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    for key, info in UPGRADES.items():
        if has_upgrade(uid, key):
            continue
        kb.row(KeyboardButton(f"{info['emoji']} {key} за клик — ${info['price']}"))
    kb.row(KeyboardButton("🔙 Назад"))
    return kb

def back_menu():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(KeyboardButton("🔙 В меню"))
    return kb

def admin_menu():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(KeyboardButton("💰 Выдать $"))
    kb.row(KeyboardButton("🎯 Выдать клики"))
    kb.row(KeyboardButton("📢 Рассылка"))
    kb.row(KeyboardButton("🚫 Забанить"), KeyboardButton("✅ Разбанить"))
    kb.row(KeyboardButton("🎟 Промокоды"))
    kb.row(KeyboardButton("🔙 В меню"))
    return kb

def promos_admin_menu():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(KeyboardButton("➕ Создать промокод"))
    kb.row(KeyboardButton("🗑 Удалить промокод"))
    kb.row(KeyboardButton("📋 Список промокодов"))
    kb.row(KeyboardButton("🔙 Назад"))
    return kb

# ---------- /start ----------
@bot.message_handler(commands=["start"])
def start(message):
    uid = message.from_user.id
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
    mult = u[6] or 1
    bot.send_message(
        uid,
        f"💵 Баланс: ${u[3]}\n"
        f"⚡ Множитель: x{mult}\n\n"
        f"Жми кнопку и зарабатывай!",
        reply_markup=clicker_kb()
    )

@bot.message_handler(func=lambda m: m.text == "💵 Кликнуть")
def click(message):
    uid = message.from_user.id
    if is_banned(uid):
        return
    mult = add_click(uid)
    u = get_user(uid)
    bot.send_message(uid, f"💵 +${mult}\nБаланс: ${u[3]}")

# ---------- ⚡ УЛУЧШЕНИЯ ----------
@bot.message_handler(func=lambda m: m.text == "⚡ Улучшения")
def upgrades_show(message):
    uid = message.from_user.id
    if is_banned(uid):
        return
    u = get_user(uid)
    own = upgrades_list(uid)
    if own:
        own_text = ", ".join(own)
    else:
        own_text = "нет"
    bot.send_message(
        uid,
        f"⚡ <b>Улучшения</b>\n\n"
        f"Твой баланс: ${u[3]}\n"
        f"Твой множитель: x{u[6] or 1}\n"
        f"Куплено: {own_text}\n\n"
        f"Выбери улучшение:",
        parse_mode="HTML",
        reply_markup=upgrades_kb(uid)
    )

@bot.message_handler(func=lambda m: any(m.text and m.text.startswith(f"{info['emoji']} {key} за клик") for key, info in UPGRADES.items()))
def buy_upgrade_handler(message):
    uid = message.from_user.id
    if is_banned(uid):
        return
    # Извлекаем ключ
    key = None
    for k, info in UPGRADES.items():
        if message.text.startswith(f"{info['emoji']} {k} за клик"):
            key = k
            break
    if not key:
        return
    result = buy_upgrade(uid, key)
    u = get_user(uid)
    bot.send_message(uid, result, reply_markup=clicker_kb())

# ---------- 🎭 ДОКС ----------
@bot.message_handler(func=lambda m: m.text == "🎭 Докс")
def doks_self(message):
    uid = message.from_user.id
    if is_banned(uid):
        return

    u = get_user(uid)
    if not u:
        bot.send_message(uid, "Сначала /start")
        return

    tg = message.from_user
    first = tg.first_name or "—"
    last = tg.last_name or ""
    full_name = f"{first} {last}".strip() if last else first
    username = f"@{tg.username}" if tg.username else "—"
    lang = tg.language_code or "—"
    premium = "Да ⭐" if getattr(tg, "is_premium", False) else "Нет"

    cities = ["Москва", "Санкт-Петербург", "Казань", "Сочи", "Омск", "Тверь", "Уфа", "Пермь"]
    streets = ["Ленина", "Пушкина", "Гагарина", "Мира", "Садовая", "Советская", "Центральная"]
    domains = ["mail.ru", "gmail.com", "yandex.ru", "bk.ru"]

    fake_phone = f"+7 9{random.randint(10,99)} {random.randint(100,999)}-{random.randint(10,99)}-{random.randint(10,99)}"
    fake_city = f"{random.choice(cities)}, ул. {random.choice(streets)}, д. {random.randint(1, 120)}"
    fake_card = f"4276 **** **** {random.randint(1000,9999)}"
    fake_pass = f"{random.choice(['qwerty','123456','pass','admin','love'])}{random.randint(10,99)}"
    fake_email = f"{random.choice(['user','admin','mail','test'])}{random.randint(100,999)}@{random.choice(domains)}"

    text = (
        f"🎭 <b>Докс на тебя</b>\n\n"
        f"✅ <b>РЕАЛЬНЫЕ ДАННЫЕ:</b>\n"
        f"👤 Имя: {full_name}\n"
        f"🔗 Юзернейм: {username}\n"
        f"🆔 ID: <code>{uid}</code>\n"
        f"🌐 Язык: {lang}\n"
        f"⭐ Premium: {premium}\n"
        f"💰 Баланс: ${u[3]}\n"
        f"👆 Кликов: {u[4]}\n\n"
        f"🎲 <b>ВЫМЫШЛЕННЫЕ:</b>\n"
        f"📱 Телефон: {fake_phone}\n"
        f"🏙 Адрес: {fake_city}\n"
        f"📧 Email: {fake_email}\n"
        f"💳 Карта: {fake_card}\n"
        f"🔐 Пароль: {fake_pass}\n\n"
        f"⚠️ Всё, что ниже «ВЫМЫШЛЕННЫЕ» — сгенерировано случайно."
    )
    bot.send_message(uid, text, parse_mode="HTML", reply_markup=main_menu(uid))

# ---------- 🎟 ПРОМОКОД ----------
@bot.message_handler(func=lambda m: m.text == "🎟 Промокод")
def promo_enter(message):
    uid = message.from_user.id
    if is_banned(uid):
        return
    bot.send_message(message.chat.id, "🎟 Введи промокод:", reply_markup=back_menu())
    bot.register_next_step_handler(message, promo_activate)

def promo_activate(message):
    if message.text == "🔙 В меню":
        bot.send_message(message.chat.id, "Главное меню:", reply_markup=main_menu(message.from_user.id))
        return
    result = activate_promo(message.text.strip(), message.from_user.id)
    bot.send_message(message.chat.id, result, reply_markup=main_menu(message.from_user.id))

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
        f"Множитель: x{u[6] or 1}\n"
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
    bot.send_message(message.chat.id, "📨 Напишите свою жалобу или вопрос:", reply_markup=back_menu())
    bot.register_next_step_handler(message, send_support)

def send_support(message):
    if message.text == "🔙 В меню":
        bot.send_message(message.chat.id, "Главное меню:", reply_markup=main_menu(message.from_user.id))
        return
    if not ADMINS:
        bot.send_message(message.chat.id, f"Напишите напрямую: @{ADMIN_USERNAME}")
        return
    uname = f"@{message.from_user.username}" if message.from_user.username else "—"
    text = (
        f"🆘 <b>Обращение в поддержку</b>\n\n"
        f"От: {uname} (ID: <code>{message.from_user.id}</code>)\n"
        f"Имя: {message.from_user.first_name}\n\n"
        f"Сообщение:\n{message.text}"
    )
    for adm in ADMINS:
        try:
            bot.send_message(adm, text, parse_mode="HTML")
        except:
            pass
    bot.send_message(message.chat.id, "✅ Отправлено администратору.", reply_markup=main_menu(message.from_user.id))

# ---------- 🔙 НАВИГАЦИЯ ----------
@bot.message_handler(func=lambda m: m.text == "🔙 В меню")
def back(message):
    bot.send_message(message.chat.id, "Главное меню:", reply_markup=main_menu(message.from_user.id))

@bot.message_handler(func=lambda m: m.text == "🔙 Назад")
def back_to_clicker(message):
    uid = message.from_user.id
    if is_admin(uid) and False:
        return
    u = get_user(uid)
    mult = u[6] if u else 1
    bot.send_message(
        uid,
        f"💵 Баланс: ${u[3] if u else 0}\n⚡ Множитель: x{mult}\n\nЖми кнопку и зарабатывай!",
        reply_markup=clicker_kb()
    )

# ---------- 🔧 АДМИН ----------
@bot.message_handler(func=lambda m: m.text == "🔧 Админ-панель")
def admin(message):
    if not is_admin(message.from_user.id):
        return
    bot.send_message(message.chat.id, "🔧 Админ-панель", reply_markup=admin_menu())

@bot.message_handler(func=lambda m: m.text == "💰 Выдать $")
def give_money(message):
    if not is_admin(message.from_user.id):
        return
    bot.send_message(message.chat.id, "Введи юзернейм (без @):", reply_markup=back_menu())
    bot.register_next_step_handler(message, give_money_step1)

def give_money_step1(message):
    if message.text == "🔙 В меню":
        bot.send_message(message.chat.id, "Меню:", reply_markup=main_menu(message.from_user.id))
        return
    target = find_by_username(message.text)
    if not target:
        bot.send_message(message.chat.id, "❌ Не найден.", reply_markup=admin_menu())
        return
    bot.send_message(message.chat.id, "Введи сумму от 1 до 500000:")
    bot.register_next_step_handler(message, lambda m: give_money_step2(m, target))

def give_money_step2(message, target):
    if not is_admin(message.from_user.id):
        return
    try:
        amount = int(message.text)
    except:
        bot.send_message(message.chat.id, "❌ Число.", reply_markup=admin_menu())
        return
    if amount < 1 or amount > 500000:
        bot.send_message(message.chat.id, "❌ 1–500000.", reply_markup=admin_menu())
        return
    add_balance(target, amount)
    bot.send_message(message.chat.id, f"✅ Выдано ${amount}", reply_markup=admin_menu())
    try:
        bot.send_message(target, f"💰 Вам выдано ${amount}")
    except:
        pass

@bot.message_handler(func=lambda m: m.text == "🎯 Выдать клики")
def give_clicks(message):
    if not is_admin(message.from_user.id):
        return
    bot.send_message(message.chat.id, "Введи юзернейм (без @):", reply_markup=back_menu())
    bot.register_next_step_handler(message, give_clicks_step1)

def give_clicks_step1(message):
    if message.text == "🔙 В меню":
        bot.send_message(message.chat.id, "Меню:", reply_markup=main_menu(message.from_user.id))
        return
    target = find_by_username(message.text)
    if not target:
        bot.send_message(message.chat.id, "❌ Не найден.", reply_markup=admin_menu())
        return
    bot.send_message(message.chat.id, "Сколько кликов выдать (1–500000):")
    bot.register_next_step_handler(message, lambda m: give_clicks_step2(m, target))

def give_clicks_step2(message, target):
    if not is_admin(message.from_user.id):
        return
    try:
        amount = int(message.text)
    except:
        bot.send_message(message.chat.id, "❌ Число.", reply_markup=admin_menu())
        return
    if amount < 1 or amount > 500000:
        bot.send_message(message.chat.id, "❌ 1–500000.", reply_markup=admin_menu())
        return
    add_clicks(target, amount)
    bot.send_message(message.chat.id, f"✅ Выдано {amount} кликов", reply_markup=admin_menu())
    try:
        bot.send_message(target, f"🎯 Вам начислено {amount} кликов")
    except:
        pass

@bot.message_handler(func=lambda m: m.text == "🎟 Промокоды")
def promos_admin(message):
    if not is_admin(message.from_user.id):
        return
    bot.send_message(message.chat.id, "🎟 Управление промокодами", reply_markup=promos_admin_menu())

@bot.message_handler(func=lambda m: m.text == "📋 Список промокодов")
def promos_list(message):
    if not is_admin(message.from_user.id):
        return
    rows = list_promos()
    if not rows:
        bot.send_message(message.chat.id, "Промокодов нет.", reply_markup=promos_admin_menu())
        return
    text = "🎟 <b>Промокоды:</b>\n\n"
    for code, amount, max_uses, uses in rows:
        limit = "∞" if max_uses == -1 else max_uses
        text += f"<code>{code}</code> — ${amount} — {uses}/{limit}\n"
    bot.send_message(message.chat.id, text, parse_mode="HTML", reply_markup=promos_admin_menu())

@bot.message_handler(func=lambda m: m.text == "➕ Создать промокод")
def promo_create(message):
    if not is_admin(message.from_user.id):
        return
    bot.send_message(message.chat.id, "Введи название промокода (например: WELCOME):", reply_markup=back_menu())
    bot.register_next_step_handler(message, promo_create_step1)

def promo_create_step1(message):
    if message.text == "🔙 В меню":
        bot.send_message(message.chat.id, "Меню:", reply_markup=main_menu(message.from_user.id))
        return
    code = message.text.strip().upper()
    if get_promo(code):
        bot.send_message(message.chat.id, "❌ Такой промокод уже есть.", reply_markup=promos_admin_menu())
        return
    bot.send_message(message.chat.id, "Сколько $ даёт промокод:")
    bot.register_next_step_handler(message, lambda m: promo_create_step2(m, code))

def promo_create_step2(message, code):
    try:
        amount = int(message.text)
    except:
        bot.send_message(message.chat.id, "❌ Число.", reply_markup=promos_admin_menu())
        return
    bot.send_message(message.chat.id, "Сколько активаций? (число или -1 для бесконечности):")
    bot.register_next_step_handler(message, lambda m: promo_create_step3(m, code, amount))

def promo_create_step3(message, code, amount):
    try:
        max_uses = int(message.text)
    except:
        bot.send_message(message.chat.id, "❌ Число.", reply_markup=promos_admin_menu())
        return
    if max_uses != -1 and max_uses < 1:
        bot.send_message(message.chat.id, "❌ Минимум 1 или -1.", reply_markup=promos_admin_menu())
        return
    create_promo(code, amount, max_uses)
    limit = "∞" if max_uses == -1 else max_uses
    bot.send_message(
        message.chat.id,
        f"✅ Промокод <code>{code}</code> создан.\nСумма: ${amount}\nАктиваций: {limit}",
        parse_mode="HTML", reply_markup=promos_admin_menu()
    )

@bot.message_handler(func=lambda m: m.text == "🗑 Удалить промокод")
def promo_delete(message):
    if not is_admin(message.from_user.id):
        return
    bot.send_message(message.chat.id, "Введи название промокода для удаления:", reply_markup=back_menu())
    bot.register_next_step_handler(message, promo_delete_step)

def promo_delete_step(message):
    if message.text == "🔙 В меню":
        bot.send_message(message.chat.id, "Меню:", reply_markup=main_menu(message.from_user.id))
        return
    code = message.text.strip().upper()
    if not get_promo(code):
        bot.send_message(message.chat.id, "❌ Не найден.", reply_markup=promos_admin_menu())
        return
    delete_promo(code)
    bot.send_message(message.chat.id, f"✅ Промокод <code>{code}</code> удалён.", parse_mode="HTML",
                     reply_markup=promos_admin_menu())

@bot.message_handler(func=lambda m: m.text == "📢 Рассылка")
def broadcast(message):
    if not is_admin(message.from_user.id):
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
    bot.send_message(message.chat.id, f"✅ Разослано {ok}", reply_markup=admin_menu())

@bot.message_handler(func=lambda m: m.text == "🚫 Забанить")
def ban(message):
    if not is_admin(message.from_user.id):
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
    if not is_admin(message.from_user.id):
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

# ---------- FALLBACK ----------
@bot.message_handler(func=lambda m: True, content_types=["text"])
def fallback(message):
    uid = message.from_user.id
    if is_banned(uid):
        return
    bot.send_message(uid, "Выбери действие 👇", reply_markup=main_menu(uid))

# ---------- ЗАПУСК ----------
print("Бот запущен...")
bot.infinity_polling()
