import telebot
import sqlite3
from datetime import datetime
from telebot import types

# 1. ВСТАВЬ СВОЙ ТОКЕН НИЖЕ
TOKEN = '8297041586:AAH_ZEM-GYpNFhsEospP2JGpgqszm6LL_cA'
bot = telebot.TeleBot(TOKEN)

def init_db():
    conn = sqlite3.connect('finance.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount REAL,
            category TEXT,
            date TEXT
        )
    ''')
    conn.commit()
    conn.close()

# Создаем кнопки
def main_keyboard():
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    btn1 = types.KeyboardButton('📊 Статистика')
    btn2 = types.KeyboardButton('❓ Помощь')
    markup.add(btn1, btn2)
    return markup

@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, 
                 "Привет! Я твой финансовый помощник.\n\n"
                 "Чтобы записать трату, просто напиши: **Сумма Категория**\n"
                 "Например: `300 Кофе`", 
                 parse_mode="Markdown",
                 reply_markup=main_keyboard())

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    # Если нажата кнопка Статистика
    if message.text == '📊 Статистика':
        conn = sqlite3.connect('finance.db')
        cursor = conn.cursor()
        cursor.execute('SELECT SUM(amount) FROM expenses WHERE user_id = ?', (message.from_user.id,))
        total = cursor.fetchone()[0]
        conn.close()
        
        total = total if total else 0
        bot.send_message(message.chat.id, f"💰 Твои общие траты: **{total} руб.**", parse_mode="Markdown")
        return

    # Если нажата кнопка Помощь
    if message.text == '❓ Помощь':
        bot.send_message(message.chat.id, "Пример записи: `1500 Продукты`.\nСначала число, потом текст через пробел.")
        return

    # Логика записи траты
    try:
        parts = message.text.split(maxsplit=1)
        amount = float(parts[0].replace(',', '.')) # Заменяем запятую на точку, если ввел 50,5
        category = parts[1] if len(parts) > 1 else "Разное"
        
        conn = sqlite3.connect('finance.db')
        cursor = conn.cursor()
        cursor.execute('INSERT INTO expenses (user_id, amount, category, date) VALUES (?, ?, ?, ?)',
                       (message.from_user.id, amount, category, datetime.now().strftime("%Y-%m-%d %H:%M")))
        conn.commit()
        conn.close()

        bot.send_message(message.chat.id, f"✅ Записал: {amount} руб. на '{category}'")
    except (ValueError, IndexError):
        bot.send_message(message.chat.id, "⚠️ Не понял тебя. Введи сумму цифрами. Пример: `500 Обед`")

if __name__ == '__main__':
    init_db()
    print("Бот успешно запущен и ждет сообщений...")
    bot.infinity_polling()