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
        cursor.execute('''CREATE TABLE IF NOT EXISTS expenses 
                          (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, 
                          amount REAL, main_category TEXT, sub_category TEXT, date TEXT)''')
        # Обновленная таблица лимитов с типом периода
        cursor.execute('''CREATE TABLE IF NOT EXISTS budgets 
                          (user_id INTEGER PRIMARY KEY, monthly_limit REAL, period_type TEXT DEFAULT 'month')''')
        conn.commit()

def get_stats_for_period(user_id, period='day'):
    with sqlite3.connect('finance.db') as conn:
        cursor = conn.cursor()
        now = datetime.now()
        if period == 'day':
            start_date = now.strftime("%Y-%m-%d 00:00")
        elif period == 'week':
            start_date = (now - timedelta(days=now.weekday())).strftime("%Y-%m-%d 00:00")
        else: # month
            start_date = now.replace(day=1).strftime("%Y-%m-%d 00:00")
            
        cursor.execute('''SELECT main_category, SUM(amount) FROM expenses 
                          WHERE user_id = ? AND date >= ? 
                          GROUP BY main_category''', (user_id, start_date))
        return cursor.fetchall()

# --- БЛОК КЛАВИАТУР ---
def main_categories_kb():
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    category_btns = [types.KeyboardButton(k) for k in CATEGORIES.keys()]
    markup.add(*category_btns)
    markup.row(types.KeyboardButton('📊 Статистика'), types.KeyboardButton('📥 Экспорт в Excel'))
    markup.row(types.KeyboardButton('🤖 Совет ИИ'), types.KeyboardButton('✏️ Исправить последнюю'))
    markup.row(types.KeyboardButton('⚙️ Установить лимит'), types.KeyboardButton('❓ Помощь'))
    return markup

def sub_categories_kb(main_cat):
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    btns = [types.KeyboardButton(sub) for sub in CATEGORIES[main_cat]]
    markup.add(*btns)
    markup.add(types.KeyboardButton('⬅️ Назад'))
    return markup

# --- НОВАЯ ФУНКЦИЯ ПРОВЕРКИ ЛИМИТА ---
def check_budget(user_id, chat_id):
    with sqlite3.connect('finance.db') as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT monthly_limit, period_type FROM budgets WHERE user_id = ?", (user_id,))
        data = cursor.fetchone()
        
        if not data: return
        limit, period_type = data
        
        now = datetime.now()
        if period_type == 'week':
            start_point = (now - timedelta(days=now.weekday())).strftime("%Y-%m-%d")
            p_text = "неделю"
        else:
            start_point = now.replace(day=1).strftime("%Y-%m-%d")
            p_text = "месяц"
            
        cursor.execute("SELECT SUM(amount) FROM expenses WHERE user_id = ? AND date >= ?", (user_id, start_point))
        total_spent = cursor.fetchone()[0] or 0
        
        if total_spent >= limit:
            bot.send_message(chat_id, f"🛑 **ЛИМИТ ПРЕВЫШЕН!**\nПотрачено: {total_spent} из {limit} руб. за {p_text}.")
        elif total_spent >= limit * 0.8:
            bot.send_message(chat_id, f"⚠️ **Осторожно!** Вы израсходовали 80% лимита на {p_text}.\nОсталось: {round(limit - total_spent, 2)} руб.")

# --- ОБРАБОТЧИКИ ---

@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(message.chat.id, "Привет! Введи сумму расхода цифрами:", reply_markup=main_categories_kb())

# Переключатель лимита
@bot.message_handler(func=lambda message: message.text == '⚙️ Установить лимит')
def set_limit_choice(message):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("На неделю", callback_data="set_period_week"))
    markup.add(types.InlineKeyboardButton("На месяц", callback_data="set_period_month"))
    bot.send_message(message.chat.id, "Выберите период для лимита:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("set_period_"))
def process_period_choice(call):
    period = "week" if "week" in call.data else "month"
    period_ru = "неделю" if period == "week" else "месяц"
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, f"Введите сумму лимита на {period_ru}:")
    bot.register_next_step_handler(msg, lambda m: save_limit_with_period(m, period))

def save_limit_with_period(message, period):
    try:
        # 1. Очищаем текст: убираем лишние пробелы и заменяем запятую на точку
        clean_text = message.text.strip().replace(' ', '').replace(',', '.')
        
        # 2. Преобразуем в число
        limit = float(clean_text)
        uid = message.from_user.id
        
        with sqlite3.connect('finance.db') as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO budgets (user_id, monthly_limit, period_type) VALUES (?, ?, ?)", 
                           (uid, limit, period))
            conn.commit()
            
        period_ru = "неделю" if period == "week" else "месяц"
        bot.send_message(message.chat.id, f"✅ Лимит {limit} руб. на {period_ru} установлен!")
        
    except ValueError:
        # Если пользователь ввел буквы или спецсимволы, которые float() не смог проглотить
        bot.send_message(message.chat.id, "❌ Ошибка! Введите корректное число (например: 20000 или 1500.50).")

# Исправление последней записи
@bot.message_handler(func=lambda message: message.text == '✏️ Исправить последнюю')
def edit_last(message):
    uid = message.from_user.id
    with sqlite3.connect('finance.db') as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT amount, sub_category FROM expenses WHERE user_id = ? ORDER BY id DESC LIMIT 1", (uid,))
        last_entry = cursor.fetchone()
        if last_entry:
            amount, cat = last_entry
            cursor.execute("DELETE FROM expenses WHERE id = (SELECT MAX(id) FROM expenses WHERE user_id = ?)", (uid,))
            conn.commit()
            bot.send_message(message.chat.id, f"🗑 Запись `{amount} руб. ({cat})` удалена. Введи правильную сумму:", parse_mode="Markdown")
        else:
            bot.send_message(message.chat.id, "Трат еще нет.")

# Логика записи
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
    if uid not in user_data or 'main_category' not in user_data[uid]: return
    
    amount = user_data[uid]['amount']
    main_cat = user_data[uid]['main_category']
    sub_cat = message.text
    
    with sqlite3.connect('finance.db') as conn:
        cursor = conn.cursor()
        cursor.execute('INSERT INTO expenses (user_id, amount, main_category, sub_category, date) VALUES (?, ?, ?, ?, ?)', 
                       (uid, amount, main_cat, sub_cat, datetime.now().strftime("%Y-%m-%d %H:%M")))
        conn.commit()
    
    check_budget(uid, message.chat.id) # Проверка лимита
    bot.send_message(message.chat.id, f"✅ Записано: {amount} руб. в '{sub_cat}'", reply_markup=main_categories_kb())
    del user_data[uid]

# Статистика, ИИ и Экспорт (остальное без изменений...)
@bot.message_handler(func=lambda message: message.text == '📊 Статистика')
def show_stats_choice(message):
    bot.send_message(message.chat.id, "За какой период показать отчет?", reply_markup=period_keyboard())

def period_keyboard():
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("За день", callback_data="stats_day"),
               types.InlineKeyboardButton("За неделю", callback_data="stats_week"),
               types.InlineKeyboardButton("За месяц", callback_data="stats_month"))
    return markup

@bot.callback_query_handler(func=lambda call: call.data.startswith('stats_'))
def callback_stats(call):
    uid = call.from_user.id
    period = call.data.split('_')[1]
    
    # Создаем словарь для перевода
    periods_ru = {
        'day': 'день',
        'week': 'неделю',
        'month': 'месяц'
    }
    
    rows = get_stats_for_period(uid, period)
    if not rows:
        bot.send_message(call.message.chat.id, f"За {periods_ru.get(period, period)} трат нет.")
        return

    plt.figure(figsize=(6, 5))
    plt.pie([r[1] for r in rows], labels=[r[0] for r in rows], autopct='%1.1f%%')
    
    # Используем перевод в заголовке
    plt.title(f"Траты за {periods_ru.get(period, period)}")
    
    path = f"g_{uid}.png"
    plt.savefig(path)
    plt.close()
    
    with open(path, 'rb') as p:
        # И здесь тоже используем перевод
        bot.send_photo(call.message.chat.id, p, caption=f"📊 Траты за {periods_ru.get(period, period)}")
    
    os.remove(path)
    bot.answer_callback_query(call.id)

@bot.message_handler(func=lambda message: message.text == '🤖 Совет ИИ')
def ai_advice(message):
    uid = message.from_user.id
    
    with sqlite3.connect('finance.db') as conn:
        cursor = conn.cursor()
        # 1. Берем данные о лимите
        cursor.execute("SELECT monthly_limit, period_type FROM budgets WHERE user_id = ?", (uid,))
        budget_data = cursor.fetchone()
        
        # 2. Берем статистику за месяц
        rows = get_stats_for_period(uid, 'month')
    
    if not rows:
        bot.send_message(message.chat.id, "❌ Мне нечего анализировать. Сначала запиши хотя бы пару трат!")
        return

    # Формируем отчет для ИИ
    report = ", ".join([f"{r[0]}: {r[1]} руб." for r in rows])
    total_spent = sum(r[1] for r in rows)
    
    # Добавляем информацию о лимите в промпт, если он есть
    budget_info = "Лимит не установлен."
    if budget_data:
        limit, p_type = budget_data
        period_ru = "неделю" if p_type == "week" else "месяц"
        budget_info = f"Мой лимит на {period_ru}: {limit} руб. Я уже потратил {total_spent} руб."

    bot.send_message(message.chat.id, "🤖 ИИ изучает твои счета...")

    # Новый мощный промпт
    prompt = (
        f"Ты — саркастичный, но гениальный финансовый коуч. Вот мои траты: {report}. "
        f"Контекст: {budget_info}. "
        "Твоя цель: "
        "1. Жестко (но смешно) прокомментируй самую затратную категорию. "
        "2. Если я превышаю лимит — включи режим 'катастрофа'. Если экономлю — похвали, но не расслабляй. "
        "3. Дай один полезный лайфхак, как сократить расходы именно в моей топ-категории. "
        "Пиши на русском, кратко, без воды. Используй эмодзи."
    )

    try:
        response = g4f.ChatCompletion.create(
            model=g4f.models.gpt_4, 
            messages=[{"role": "user", "content": prompt}],
        )
        bot.send_message(message.chat.id, f"💡 **Вердикт ИИ:**\n\n{response}")
    except Exception as e:
        bot.send_message(message.chat.id, "🤖 ИИ сейчас разгребает финаносвый, попробуйте позже.")

@bot.message_handler(func=lambda message: message.text == '📥 Экспорт в Excel')
def export_excel(message):
    uid = message.from_user.id
    with sqlite3.connect('finance.db') as conn:
        df = pd.read_sql_query(f"SELECT * FROM expenses WHERE user_id = {uid}", conn)
    if df.empty: return
    df.to_excel(f"rep_{uid}.xlsx", index=False)
    with open(f"rep_{uid}.xlsx", 'rb') as f:
        bot.send_document(message.chat.id, f)
    os.remove(f"rep_{uid}.xlsx")

@bot.message_handler(func=lambda message: message.text == '❓ Помощь')
def help_msg(message):
    bot.send_message(message.chat.id, "Напиши сумму -> Выбери категорию -> Готово!")

if __name__ == '__main__':
    init_db()
    print("Бот успешно запущен!")
    bot.infinity_polling()