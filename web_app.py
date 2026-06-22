import sqlite3
import pandas as pd
import matplotlib
import matplotlib.pyplot as plt
from io import BytesIO
from flask import Flask, render_template, send_file, request, redirect, url_for
from datetime import datetime
from g4f.client import Client
from fpdf import FPDF
import requests
import matplotlib.patheffects as path_effects
import os
from dotenv import load_dotenv
from openai import OpenAI
from matplotlib.colors import LinearSegmentedColormap

matplotlib.use('Agg')
matplotlib.rcParams['font.family'] = 'Arial'

app = Flask(__name__)

# Загружаем переменные окружения из файла .env
load_dotenv()

# Инициализируем официальный клиент DeepSeek 
client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com"
)

def get_db_connection():
    conn = sqlite3.connect('finance.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    conn.execute('''CREATE TABLE IF NOT EXISTS expenses 
                    (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                     amount REAL, main_category TEXT, sub_category TEXT, date TEXT)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS budgets 
                    (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                     amount REAL, start_date TEXT, end_date TEXT)''')
    conn.commit()
    conn.close()

init_db()

@app.route('/get_advice')
def get_advice():
    conn = get_db_connection()
    expenses = conn.execute('SELECT amount, main_category, sub_category, date FROM expenses ORDER BY id DESC LIMIT 20').fetchall()
    budget_row = conn.execute('SELECT amount, start_date, end_date FROM budgets LIMIT 1').fetchone()
    
    now = datetime.now()

    days_in_month = pd.Period(now.strftime('%Y-%m')).days_in_month
    days_left = days_in_month - now.day + 1
    
    total_spent = 0
    if budget_row:
        total_spent = conn.execute('SELECT SUM(amount) FROM expenses WHERE date BETWEEN ? AND ?', 
                                   (budget_row['start_date'], budget_row['end_date'])).fetchone()[0] or 0

    data_summary = [f"- {e['main_category']} ({e['sub_category'] or 'без описания'}): {e['amount']}р" for e in expenses]
    expenses_str = "\n".join(data_summary)
    
    budget_context = f"""
    - Сегодняшняя дата: {now.strftime('%Y-%m-%d')}
    - До конца лимитного периода осталось: {days_left} дн.
    - Установленный лимит: {budget_row['amount'] if budget_row else 'Не задан'} р.
    - Уже потрачено: {total_spent} р.
    - Свободный остаток: {(budget_row['amount'] - total_spent) if budget_row else '—'} р.
    """

    prompt = f"""
    Ты — строгий финансовый ревизор. Твой язык общения — ТОЛЬКО РУССКИЙ.
    КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО использовать английский язык, латиницу или дублировать фразы на английском.
    ДАННЫЕ:
    {budget_context}
    ПОСЛЕДНИЕ ТРАТЫ:
    {expenses_str}

    ЗАДАЧА:
    1. Проанализируй категории. Дай коментарии по поводу самих категорий и их описаний, если описания нет, то дай коментарий по категории.
    2. Рассчитай "Дневной бюджет": (остаток / кол-во оставшихся дней). Скажи пользователю, сколько он может тратить в день, чтобы не уйти в минус.
    3. Дай одну конкретную рекомендацию.
    ПИШИ КРАТКО. БЕЗ ВВОДНЫХ СЛОВ.
    """

    # --- ЛОГИКА ПЕРЕКЛЮЧЕНИЯ КАНАЛОВ ---
    try:
        # Отправляем запрос в официальный DeepSeek (модель V3)
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            timeout=8 
        )
        conn.close()
        return response.choices[0].message.content

    except Exception:
        try:
            res = requests.post("http://localhost:11434/api/generate", 
                                json={"model": "llama3", "prompt": prompt, "stream": False}, 
                                timeout=15)
            advice = res.json().get("response")
            conn.close()
            return f"[РЕЗЕРВНЫЙ КАНАЛ]:\n\n{advice}"
        except:
            conn.close()
            return "❌ Ошибка: Оба канала связи (Дипсик и Ollama) недоступны."

@app.route('/set_budget', methods=['POST'])
def set_budget():
    amount = request.form.get('amount')
    budget_date = request.form.get('budget_date')
    if amount and budget_date:
        conn = get_db_connection()
        dt = datetime.strptime(budget_date, '%Y-%m-%d')
        start_date = dt.strftime('%Y-%m-01')
        end_date = dt.strftime('%Y-%m-31')
        conn.execute('DELETE FROM budgets')
        conn.execute('INSERT INTO budgets (amount, start_date, end_date) VALUES (?, ?, ?)', 
                     (amount, start_date, end_date))
        conn.commit()
        conn.close()
    return redirect(url_for('index'))

@app.route('/export')
def export_data():
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT * FROM expenses", conn)
    conn.close()
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Расходы')
    output.seek(0)
    return send_file(output, download_name="finance_report.xlsx", as_attachment=True)

def get_head_html(title):
    return f"""
    <head>
        <meta charset="utf-8">
        <title>{title}</title>
        <script>
            (function() {{
                const savedTheme = localStorage.getItem('theme') || 'dark';
                if (savedTheme === 'dark') document.documentElement.setAttribute('data-theme', 'dark');
            }})();
        </script>
<style>
    :root {{ --bg: #f0f4f8; --card-bg: #ffffff; --text: #2c3e50; --border: #dce4ec; --accent: #10b981; --text-muted: #7f8c8d; }}
    [data-theme="dark"] {{ --bg: #0f172a; --card-bg: #1e293b; --text: #f8fafc; --border: #334155; --accent: #10b981; --text-muted: #cbd5e1; }}

    a {{ text-decoration: none; }}

    body {{ font-family: 'Segoe UI', sans-serif; background: var(--bg); color: var(--text); transition: 0.3s; margin: 0; padding: 20px; }}
    .container {{ display: grid; grid-template-columns: 1fr 1.5fr; gap: 20px; max-width: 1100px; margin: 0 auto; }}
    .card {{ background: var(--card-bg); padding: 20px; border-radius: 15px; border: 1px solid var(--border); margin-bottom: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }}
    
    input {{ width: 100%; padding: 12px; margin: 8px 0; border: 1px solid var(--border); border-radius: 8px; background: var(--bg); color: var(--text); box-sizing: border-box; }}
    .btn {{ width: 100%; padding: 12px; border: none; border-radius: 8px; cursor: pointer; font-weight: bold; color: white; transition: 0.2s; }}
    .btn-add {{ background: var(--accent); }}
    .btn-ai {{ background: #9c27b0; margin-bottom: 10px; }}
    
    /* 1. Кнопки экспорта теперь вертикальные */
    .reports-grid {{ 
        display: grid; 
        grid-template-columns: 1fr; 
        gap: 10px; 
        margin-top: 15px; 
        border-top: 1px solid var(--border); 
        padding-top: 15px; 
    }}
    .btn-export-small {{ padding: 10px 5px; font-size: 0.85rem; text-decoration: none; display: flex; align-items: center; justify-content: center; border-radius: 8px; color: white; font-weight: bold; }}
    .bg-excel {{ background: #ff9800; }}
    .bg-pdf {{ background: #e91e63; }}

    #adviceContainer {{ 
        white-space: pre-wrap; 
        line-height: 1.4; 
        padding: 10px; 
        
        /* ЖЕСТКАЯ ФИКСАЦИЯ */
        height: 150px;           /* Фиксированная высота */
        min-height: 100px;       /* Запрещаем сжиматься */
        max-height: 100px;       /* Запрещаем расширяться */
        
        margin-top: 15px; 
        margin-bottom: 15px;
        overflow-y: auto;        /* Прокрутка внутри */
        
        background: rgba(0,0,0,0.03); 
        border-radius: 8px;
        border: 1px solid var(--border);
        box-sizing: border-box;  /* Важно: padding не увеличивает высоту */
        display: block;          /* Гарантируем блочное поведение */
    }}

    /* Красивый скроллбар для блока советов */
    #adviceContainer::-webkit-scrollbar {{ width: 6px; }}
    #adviceContainer::-webkit-scrollbar-thumb {{ background: var(--accent); border-radius: 10px; }}

    .theme-toggle {{ position: fixed; top: 20px; right: 20px; cursor: pointer; padding: 10px; border-radius: 50px; background: var(--card-bg); border: 1px solid var(--border); color: var(--text); }}
    .transaction-item {{ background: var(--card-bg); padding: 12px; border-radius: 8px; margin-bottom: 10px; display: flex; justify-content: space-between; align-items: center; border: 1px solid var(--border); border-left: 4px solid var(--accent); }}
    
    .transaction-item a {{ margin-left: 10px; font-size: 1.1rem; }}
    .transaction-item a:hover {{ opacity: 0.7; }}

    /* МОБИЛЬНАЯ АДАПТАЦИЯ */
    @media (max-width: 768px) {{
        body {{
            padding: 10px; /* Уменьшаем отступы по краям */
        }}
        
        .container {{
            display: flex;
            flex-direction: column; /* Складываем колонки друг под друга */
            gap: 15px;
        }}
        
        .card {{
            padding: 15px; /* Чуть меньше падинги внутри карточек */
        }}

        .theme-toggle {{
            top: 10px;
            right: 10px;
            padding: 8px;
        }}

        /* Делаем кнопки экспорта в ряд на мобилках, если хочешь сэкономить место, 
           либо оставь 1fr, если хочешь их во всю ширину */
        .reports-grid {{
            grid-template-columns: 1fr; 
        }}
    }}

    #financeChart {{
       transition: opacity 0.3s ease-in-out;
       opacity: 1;
    }}
    .chart-loading {{
       opacity: 0.5;
    }}
</style>
        <script>
            function toggleTheme() {{
                const h = document.documentElement;
                let t = h.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
                h.setAttribute('data-theme', t);
                localStorage.setItem('theme', t);
            }}

            async function getAIAdvice() {{
    const btn = document.querySelector('.btn-ai');
    const adviceBox = document.getElementById('adviceContainer');
    
    btn.disabled = true;
    adviceBox.innerHTML = 'Запрос к основному ИИ...';
    
    try {{
        const r = await fetch('/get_advice');
        const text = await r.text();
        
        // Если в тексте есть пометка о резерве, можем выделить её цветом
        if (text.includes('[РЕЗЕРВНЫЙ КАНАЛ]')) {{
            adviceBox.style.border = "1px solid #ff9800"; // Оранжевая рамка при резерве
        }} else {{
            adviceBox.style.border = "1px solid var(--border)";
        }}
        
        adviceBox.innerHTML = text;
    }} catch (e) {{
        adviceBox.innerHTML = " Ошибка системы.";
    }} finally {{
        btn.disabled = false;
    }}
 }}

 
        </script>
    </head>"""

@app.route('/', methods=['GET', 'POST'])
def index():
    conn = get_db_connection()
    today = datetime.now().strftime('%Y-%m-%d')
    search_query = request.args.get('search', '')
    
    edit_id = request.args.get('edit')
    edit_item = conn.execute('SELECT * FROM expenses WHERE id = ?', (edit_id,)).fetchone() if edit_id else None

    if request.method == 'POST':
        if 'amount' in request.form:
            amt, cat, sub = request.form['amount'], request.form['main_category'], request.form['sub_category']
            date = request.form.get('date') or today
            
            if request.form.get('id_to_edit'):
                conn.execute('UPDATE expenses SET amount=?, main_category=?, sub_category=?, date=? WHERE id=?',
                             (amt, cat, sub, date, request.form.get('id_to_edit')))
            else:
                conn.execute('INSERT INTO expenses (amount, main_category, sub_category, date) VALUES (?,?,?,?)',
                             (amt, cat, sub, date))
            conn.commit()
            conn.close()
            return redirect(url_for('index'))

    if search_query:
        latest = conn.execute('SELECT * FROM expenses WHERE main_category LIKE ? ORDER BY date DESC, id DESC', ('%' + search_query + '%',)).fetchall()
    else:
        latest = conn.execute('SELECT * FROM expenses ORDER BY date DESC, id DESC LIMIT 15').fetchall()

    total = conn.execute('SELECT SUM(amount) FROM expenses').fetchone()[0] or 0
    budget = conn.execute('SELECT * FROM budgets LIMIT 1').fetchone()
    
    budget_html = ""
    if budget:
        spent = conn.execute('SELECT SUM(amount) FROM expenses WHERE date BETWEEN ? AND ?', (budget['start_date'], budget['end_date'])).fetchone()[0] or 0
        perc = min((spent / budget['amount']) * 100, 100)
        budget_html = f'''<div class="card"><h3>Бюджет до {budget["end_date"]}</h3><p>{spent} / {budget["amount"]} р</p><div style="background:var(--border); height:10px; border-radius:5px; overflow:hidden;"><div style="background:var(--accent); width:{perc}%; height:100%;"></div></div></div>'''
    
    limit_form_html = f"""
    <div class="card">
        <h3>Установить лимит</h3>
        <form action="/set_budget" method="POST" style="display:flex; flex-direction:column; gap:5px;">
            <input type="number" name="amount" placeholder="Сумма" required>
            <div style="display:flex; gap:5px;">
                <input type="date" name="budget_date" value="{today}" style="margin:0;">
                <button type="submit" class="btn btn-add" style="width:60px;">OK</button>
            </div>
        </form>
    </div>
    """

    list_html = "".join([f"""<div class="transaction-item"><div><strong>{r['main_category']}</strong><br><small>{r['date']}</small></div><div><b>{r['amount']} р</b> <a href="/?edit={r['id']}">✏️</a> <a href="/delete/{r['id']}">🗑️</a></div></div>""" for r in latest])
    
    conn.close()
    
    return f"""<html>{get_head_html("Финансовый Аналитик")}<body><button class="theme-toggle" onclick="toggleTheme()">🌓</button>
    <div class="container">
        <div class="column">
<div class="card">
    <h3>ИИ Анализ</h3>
    <button class="btn btn-ai" onclick="getAIAdvice()">Получить совет</button>
    
    <!-- Контейнер для текста совета -->
    <div id="adviceContainer">Нажмите для анализа...</div>
    
    <!-- Кнопки теперь в отдельном блоке СНАРУЖИ -->
    <div class="reports-grid">
        <a href="/export" class="btn-export-small bg-excel">Excel</a>
        <a href="/export_pdf" class="btn-export-small bg-pdf">PDF</a>
    </div>
</div>
            {limit_form_html}
            <div class="card">
                <h3>{'Правка' if edit_item else 'Запись'}</h3>
                <form method="POST">
                    <input type="hidden" name="id_to_edit" value="{edit_item['id'] if edit_item else ''}">
                    <input type="number" step="0.01" name="amount" placeholder="Сумма" value="{edit_item['amount'] if edit_item else ''}" required>
                    <input type="text" name="main_category" placeholder="Категория" value="{edit_item['main_category'] if edit_item else ''}" required>
                    <input type="text" name="sub_category" placeholder="Описание" value="{edit_item['sub_category'] if edit_item else ''}">
                    <input type="date" name="date" value="{edit_item['date'] if edit_item else today}">
                    <button type="submit" class="btn btn-add">OK</button>
                </form>
            </div>
        </div>
        <div class="column">
            <div class="card" style="text-align:center;"><h3>Всего: {total} р</h3><img src="/chart.png" style="width:100%; max-width:280px;"></div>
            {budget_html}
            <div class="card">
                <h3>Операции</h3>
                <div style="max-height: 400px; overflow-y: auto;">{list_html}</div>
            </div>
        </div>
    </div></body></html>"""

@app.route('/delete/<int:item_id>')
def delete_item(item_id):
    conn = get_db_connection()
    conn.execute('DELETE FROM expenses WHERE id = ?', (item_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('index'))

import matplotlib.patheffects as path_effects

from matplotlib.colors import LinearSegmentedColormap
import matplotlib.patheffects as path_effects

@app.route('/chart.png')
def chart():
    conn = get_db_connection()
    rows = conn.execute('SELECT main_category, SUM(amount) FROM expenses GROUP BY main_category').fetchall()
    conn.close()
    
    if not rows:
        return send_file(BytesIO(), mimetype='image/png')
    
    labels = [r[0] for r in rows]
    sizes = [r[1] for r in rows]
    
    # ★ ГРАДИЕНТНАЯ ПАЛИТРА ★
    cmap = LinearSegmentedColormap.from_list('grad', ['#2E86AB', '#2E86AB', '#6DB1BF', '#A2D5C6'])
    gradient_colors = [cmap(i / max(len(sizes)-1, 1)) for i in range(len(sizes))]
    
    explode = [0.05] * len(sizes)
    
    plt.figure(figsize=(3.5, 3.5))
    
    patches, texts, autotexts = plt.pie(
        sizes,
        labels=labels,
        colors=gradient_colors,   
        explode=explode,
        autopct='%1.1f%%',
        startangle=90,
        shadow=True,
        textprops={'fontsize': 10, 'weight': 'bold'},
        wedgeprops={'edgecolor': 'white', 'linewidth': 1.5}
    )
    
    #  ОБВОДКА ДЛЯ ВНЕШНИХ ПОДПИСЕЙ 
    for text in texts:
        text.set_path_effects([
            path_effects.Stroke(linewidth=3, foreground='white'),
            path_effects.Normal()
        ])
    
    # Проценты внутри
    for text in autotexts:
        text.set_color('white')
        text.set_fontsize(11)
        text.set_weight('bold')
    
    plt.axis('equal')
    
    img = BytesIO()
    plt.savefig(img, format='png', transparent=True, bbox_inches='tight')
    img.seek(0)
    plt.close()
    return send_file(img, mimetype='image/png')

@app.route('/export_pdf')
def export_pdf():
    conn = get_db_connection()
    expenses = conn.execute('SELECT * FROM expenses ORDER BY date DESC').fetchall()
    conn.close()
    
    pdf = FPDF()
    pdf.add_page()
    
    # Используем ARIAL.TTF и
    try:
        # Важно: имя файла должно точно совпадать 
        pdf.add_font('CustomArial', '', 'ARIAL.TTF', uni=True)
        pdf.set_font('CustomArial', size=12)
    except Exception as e:
        print(f"Ошибка загрузки шрифта: {e}")
        pdf.set_font('Arial', size=12)

    # Теперь пишем текст
    pdf.cell(200, 10, txt="Финансовый отчет", ln=True, align='C')
    pdf.ln(10)
    
    for row in expenses:
        # Формируем строку: Дата | Категория | Сумма
        line = f"{row['date']} | {row['main_category']} | {row['amount']} р."
        pdf.cell(200, 10, txt=line, ln=True)

    output = BytesIO()
    # dest='S' возвращает байтовую строку в fpdf2
    pdf_content = pdf.output(dest='S')
    
    # Обработка вывода, чтобы не было конфликтов типов данных
    if isinstance(pdf_content, str):
        output.write(pdf_content.encode('latin1', errors='replace'))
    else:
        output.write(pdf_content)
        
    output.seek(0)
    return send_file(output, download_name="report.pdf", as_attachment=True)

if __name__ == '__main__':
    app.run(debug=True)