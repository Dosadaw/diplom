import telebot
import sqlite3
import os
import pandas as pd
import matplotlib
matplotlib.use('Agg') # Чтобы графики рисовались в файл
import matplotlib.pyplot as plt
import g4f
from datetime import datetime, timedelta
from telebot import types

# 1. ТОКЕН (Вставь свой!)
TOKEN = '8297041586:AAH_ZEM-GYpNFhsEospP2JGpgqszm6LL_cA'
bot = telebot.TeleBot(TOKEN)

# Временное хранилище для процесса записи
user_data = {}

# Настройки категорий
CATEGORIES = {
    '🍔 Еда': ['🛒 Продукты', '🍕 Рестораны/Кафе', '☕ Кофе'],
    '🚕 Транспорт': ['⛽ Топливо', '🚕 Такси', '🚌 Автобус/Метро'],
    '🏠 Дом': ['🧺 Хозтовары', '💡 Коммуналка', '🛋 Мебель'],
    '🎮 Досуг': ['🎮 Игры', '🍿 Кино/Сервисы', '💃 Хобби'],
    '🎁 Другое': ['💊 Здоровье', '👕 Одежда', '🎈 Подарки']
}

# --- БЛОК БАЗЫ ДАННЫХ ---
def init_db():
    with sqlite3.connect('finance.db') as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount REAL,
                main_category TEXT,
                sub_category TEXT,
                date TEXT
            )
        ''')
        conn.commit()

def get_stats_for_period(user_id, period='day'):
    with sqlite3.connect('finance.db') as conn:
        cursor = conn.cursor()
        now = datetime.now()
        if period == 'day':
            start_date = now.strftime("%Y-%m-%d 00:00")
        elif period == 'week':
            start_date = (now - timedelta(days=7)).strftime("%Y-%m-%d 00:00")
        else: # month
            start_date = (now - timedelta(days=30)).strftime("%Y-%m-%d 00:00")
            
        cursor.execute('''SELECT main_category, SUM(amount) FROM expenses 
                          WHERE user_id = ? AND date >= ? 
                          GROUP BY main_category''', (user_id, start_date))
        return cursor.fetchall()

# --- БЛОК КЛАВИАТУР ---
def main_categories_kb():
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    btns = [types.KeyboardButton(k) for k in CATEGORIES.keys()]
    markup.add(*btns)
    markup.add(types.KeyboardButton('📊 Статистика'), types.KeyboardButton('📥 Экспорт в Excel'))
    markup.add(types.KeyboardButton('🤖 Совет ИИ'), types.KeyboardButton('❓ Помощь'))
    return markup

def sub_categories_kb(main_cat):
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    btns = [types.KeyboardButton(sub) for sub in CATEGORIES[main_cat]]
    markup.add(*btns)
    markup.add(types.KeyboardButton('⬅️ Назад'))
    return markup

def period_keyboard():
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("За день", callback_data="stats_day"))
    markup.add(types.InlineKeyboardButton("За неделю", callback_data="stats_week"))
    markup.add(types.InlineKeyboardButton("За месяц", callback_data="stats_month"))
    return markup

# --- ОБРАБОТЧИКИ КОМАНД ---
@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(message.chat.id, "Привет! Введи сумму расхода цифрами:", reply_markup=main_categories_kb())

@bot.message_handler(func=lambda message: message.text == '📊 Статистика')
def show_stats_choice(message):
    bot.send_message(message.chat.id, "За какой период показать отчет?", reply_markup=period_keyboard())

@bot.message_handler(func=lambda message: message.text == '❓ Помощь')
def help_msg(message):
    bot.send_message(message.chat.id, "Напиши сумму -> Выбери категорию -> Готово!")

# --- ЛОГИКА ЗАПИСИ ТРАТ ---
@bot.message_handler(func=lambda message: message.text.replace(',', '.').replace('.', '', 1).isdigit())
def process_amount(message):
    amount = float(message.text.replace(',', '.'))
    user_data[message.from_user.id] = {'amount': amount}
    bot.send_message(message.chat.id, f"Сумма: {amount} руб. Выбери категорию:", reply_markup=main_categories_kb())

@bot.message_handler(func=lambda message: message.text in CATEGORIES.keys())
def process_main_cat(message):
    uid = message.from_user.id
    if uid not in user_data:
        bot.send_message(message.chat.id, "Сначала введи сумму!")
        return
    user_data[uid]['main_category'] = message.text
    bot.send_message(message.chat.id, "Уточни подкатегорию:", reply_markup=sub_categories_kb(message.text))

@bot.message_handler(func=lambda message: any(message.text in v for v in CATEGORIES.values()))
def process_sub_cat(message):
    uid = message.from_user.id
    if uid not in user_data or 'main_category' not in user_data[uid]:
        bot.send_message(message.chat.id, "Ошибка сессии. Введи сумму заново.")
        return
    
    amount = user_data[uid]['amount']
    main_cat = user_data[uid]['main_category']
    sub_cat = message.text
    
    with sqlite3.connect('finance.db') as conn:
        cursor = conn.cursor()
        cursor.execute('INSERT INTO expenses (user_id, amount, main_category, sub_category, date) VALUES (?, ?, ?, ?, ?)', 
                       (uid, amount, main_cat, sub_cat, datetime.now().strftime("%Y-%m-%d %H:%M")))
    
    del user_data[uid]
    bot.send_message(message.chat.id, f"✅ Записано: {amount} руб. в '{sub_cat}'", reply_markup=main_categories_kb())

# --- ЭКСПОРТ И АНАЛИТИКА ---
@bot.message_handler(func=lambda message: message.text == '📥 Экспорт в Excel')
def export_excel(message):
    uid = message.from_user.id
    try:
        with sqlite3.connect('finance.db') as conn:
            df = pd.read_sql_query(f"SELECT date, amount, main_category, sub_category FROM expenses WHERE user_id = {uid}", conn)
        if df.empty:
            bot.send_message(message.chat.id, "Трат еще нет!")
            return
        path = f"report_{uid}.xlsx"
        df.to_excel(path, index=False)
        with open(path, 'rb') as f:
            bot.send_document(message.chat.id, f, caption="Твой Excel-отчет")
        os.remove(path)
    except Exception as e:
        bot.send_message(message.chat.id, f"Ошибка экспорта: {e}")

@bot.message_handler(func=lambda message: message.text == '🤖 Совет ИИ')
def ai_advice(message):
    uid = message.from_user.id
    rows = get_stats_for_period(uid, 'month')
    
    if not rows:
        bot.send_message(message.chat.id, "❌ Мало данных для анализа. Сначала запиши хотя бы одну трату!")
        return

    report = ", ".join([f"{r[0]}: {r[1]} руб." for r in rows])
    bot.send_message(message.chat.id, "🤖 Связываюсь с финансовым экспертом (ИИ)...")

    # Формируем "живой" промпт
    prompt = (
        f"У меня есть список трат за месяц: {report}. "
        "Представь, что ты — остроумный финансовый эксперт с чувством юмора. "
        "Проанализируй эти траты и дай один совет. "
        "Твой ответ должен быть разнообразным (не только про экономию), "
        "иногда с долей иронии по поводу моих трат. "
        "Пиши на русском языке, не более 3 предложений."
    )

    try:
        response = g4f.ChatCompletion.create(
            model=g4f.models.gpt_4, 
            messages=[{"role": "user", "content": prompt}],
        )
        
        if response:
            bot.send_message(message.chat.id, f"💡 **Совет от ИИ:**\n\n{response}")
        else:
            raise Exception("Пустой ответ")

    except Exception as e:
        print(f"Ошибка ИИ: {e}")
        bot.send_message(message.chat.id, "🤖 Сейчас на линии перегрузка, нейроны отдыхают. Но помни: если тратить меньше, чем зарабатываешь — это уже успех!")

@bot.callback_query_handler(func=lambda call: call.data.startswith('stats_'))
def callback_stats(call):
    uid = call.from_user.id
    period = call.data.split('_')[1]
    periods_ru = {'day': 'день', 'week': 'неделю', 'month': 'месяц'}
    rows = get_stats_for_period(uid, period)
    
    if not rows:
        bot.send_message(call.message.chat.id, f"За {periods_ru[period]} трат нет.")
        return

    try:
        plt.figure(figsize=(8, 6))
        plt.pie([r[1] for r in rows], labels=[r[0] for r in rows], autopct='%1.1f%%')
        plt.title(f"Траты за {periods_ru[period]}")
        path = f"g_{uid}_{period}.png"
        plt.savefig(path)
        plt.close()
        
        text = f"📊 **Итог за {periods_ru[period]}:**\n" + "\n".join([f"• {r[0]}: {r[1]}р" for r in rows])
        with open(path, 'rb') as p:
            bot.send_photo(call.message.chat.id, p, caption=text, parse_mode="Markdown")
        os.remove(path)
    except Exception as e:
        bot.send_message(call.message.chat.id, f"Ошибка графика: {e}")
    bot.answer_callback_query(call.id)

if __name__ == '__main__':
    init_db()
    print("Бот успешно запущен!")
    bot.infinity_polling()