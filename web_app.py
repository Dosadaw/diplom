import sqlite3
import matplotlib.pyplot as plt
from io import BytesIO
import matplotlib
from flask import Flask, render_template, send_file, request, redirect, url_for
from datetime import datetime, timedelta
import g4f
from g4f.client import Client

matplotlib.use('Agg')
app = Flask(__name__)

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
    budget = conn.execute('SELECT * FROM budgets LIMIT 1').fetchone()
    expenses = conn.execute('SELECT * FROM expenses ORDER BY id DESC LIMIT 10').fetchall()
    
    history_text = "\n".join([f"- {e['main_category']}: {e['amount']}р" for e in expenses])
    budget_status = "Лимит пока не задан."
    if budget:
        spent = conn.execute('SELECT SUM(amount) FROM expenses WHERE date BETWEEN ? AND ?', 
                             (budget['start_date'], budget['end_date'])).fetchone()[0] or 0
        budget_status = f"Лимит {budget['amount']}р. Потрачено {spent}р. До конца периода осталось {budget['end_date']}."

    try:
        client = Client()
        # Ускоряем ответ и убираем странные слова
        prompt = f"""
        Ты — профессиональный финансовый консультант. Проанализируй данные:
        {budget_status}
        Последние траты: {history_text}
        
        Дай один конкретный и полезный совет на русском языке. 
        Используй только общепринятые финансовые термины (никакого сленга вроде 'бахтачка').
        Пиши просто, понятно и вежливо. НЕ используй Markdown (** или #).
        Максимум 3 предложения.
        """
        
        response = client.chat.completions.create(
            model="", 
            messages=[{"role": "user", "content": prompt}]
        )
        advice = response.choices[0].message.content
    except Exception:
        advice = "🤖 Сейчас я не могу проанализировать траты, но статистика выше поможет вам сориентироваться самостоятельно. Попробуйте обновить через минуту!"
    
    conn.close()
    return advice

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
            :root {{ --bg: #f0f4f8; --card-bg: #ffffff; --text: #2c3e50; --border: #dce4ec; --accent: #4CAF50; --text-muted: #7f8c8d; }}
            [data-theme="dark"] {{ --bg: #0f172a; --card-bg: #1e293b; --text: #f1f5f9; --border: #334155; --accent: #10b981; --text-muted: #94a3b8; }}
            body {{ font-family: 'Segoe UI', sans-serif; background: var(--bg); color: var(--text); transition: 0.3s; margin: 0; padding: 20px; }}
            .card {{ background: var(--card-bg); padding: 20px; border-radius: 15px; border: 1px solid var(--border); margin-bottom: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }}
            input {{ width: 100%; padding: 10px; margin: 8px 0; border: 1px solid var(--border); border-radius: 8px; background: var(--bg); color: var(--text); }}
            .btn {{ width: 100%; padding: 12px; border: none; border-radius: 8px; cursor: pointer; font-weight: bold; color: white; display: block; text-align: center; text-decoration: none; transition: 0.2s; }}
            .btn:active {{ transform: scale(0.98); }}
            .btn-add {{ background: var(--accent); }}
            .btn-blue {{ background: #2196F3; margin-top: 5px; }}
            .btn-ai {{ background: #9c27b0; margin-bottom: 10px; }}
            .container {{ display: grid; grid-template-columns: 1fr 1.5fr; gap: 20px; max-width: 1100px; margin: 0 auto; }}
            .transaction-item {{ background: var(--card-bg); padding: 12px; border-radius: 8px; margin-bottom: 10px; border-left: 4px solid var(--accent); display: flex; justify-content: space-between; align-items: center; border: 1px solid var(--border); }}
            .theme-toggle {{ position: fixed; top: 20px; right: 20px; cursor: pointer; padding: 10px; border-radius: 50px; background: var(--card-bg); color: var(--text); border: 1px solid var(--border); z-index: 100; }}
            #aiModal {{ display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.7); z-index: 1000; }}
            .modal-content {{ background: var(--card-bg); width: 400px; margin: 12% auto; padding: 30px; border-radius: 20px; text-align: center; border: 2px solid var(--accent); box-shadow: 0 20px 40px rgba(0,0,0,0.4); }}
            #adviceText {{ line-height: 1.6; text-align: left; font-size: 1.05em; }}
        </style>
        <script>
            function toggleTheme() {{
                const h = document.documentElement;
                let t = h.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
                h.setAttribute('data-theme', t);
                localStorage.setItem('theme', t);
            }}
            async function showAI() {{
                const b = document.querySelector('.btn-ai'); 
                const old = b.innerText;
                b.innerText = "⏳ Анализирую...";
                try {{
                    const r = await fetch('/get_advice');
                    const t = await r.text();
                    // Заменяем переносы строк на теги <br> для красоты
                    document.getElementById('adviceText').innerHTML = t.replace(/\\n/g, '<br>');
                    document.getElementById('aiModal').style.display = 'block';
                }} finally {{
                    b.innerText = old;
                }}
            }}
        </script>
    </head>"""

@app.route('/', methods=['GET', 'POST'])
def index():
    conn = get_db_connection()
    edit_id = request.args.get('edit')
    edit_item = None
    if edit_id:
        edit_item = conn.execute('SELECT * FROM expenses WHERE id = ?', (edit_id,)).fetchone()

    if request.method == 'POST':
        if 'amount' in request.form:
            if request.form.get('id_to_edit'):
                conn.execute('UPDATE expenses SET amount=?, main_category=?, sub_category=? WHERE id=?',
                             (request.form['amount'], request.form['main_category'], request.form['sub_category'], request.form.get('id_to_edit')))
            else:
                conn.execute('INSERT INTO expenses (amount, main_category, sub_category, date) VALUES (?,?,?,date("now"))',
                             (request.form['amount'], request.form['main_category'], request.form['sub_category']))
        elif 'budget_amount' in request.form:
            end = (datetime.now() + timedelta(days=int(request.form['budget_days']))).strftime('%Y-%m-%d')
            conn.execute('DELETE FROM budgets')
            conn.execute('INSERT INTO budgets (amount, start_date, end_date) VALUES (?, date("now"), ?)', (request.form['budget_amount'], end))
        conn.commit()
        conn.close()
        return redirect(url_for('index'))

    total = conn.execute('SELECT SUM(amount) FROM expenses').fetchone()[0] or 0
    latest = conn.execute('SELECT * FROM expenses ORDER BY id DESC LIMIT 15').fetchall()
    budget = conn.execute('SELECT * FROM budgets LIMIT 1').fetchone()
    
    budget_html = ""
    if budget:
        spent = conn.execute('SELECT SUM(amount) FROM expenses WHERE date BETWEEN ? AND ?', (budget['start_date'], budget['end_date'])).fetchone()[0] or 0
        perc = min((spent / budget['amount']) * 100, 100)
        budget_html = f'<div class="card"><h3>🎯 Бюджет до {budget["end_date"]}</h3><p>{spent} / {budget["amount"]} р</p><div style="background:#eee; height:12px; border-radius:6px; overflow:hidden;"><div style="background:var(--accent); width:{perc}%; height:100%;"></div></div></div>'

    list_html = "".join([f"""
        <div class="transaction-item">
            <div><small style="color:var(--text-muted)">{r['date']}</small><br><strong>{r['sub_category'] or r['main_category']}</strong></div>
            <div style="text-align:right;">
                <b>{r['amount']} р</b><br>
                <a href="/?edit={r['id']}" style="text-decoration:none; margin-right:12px; filter: grayscale(1);">📝</a> 
                <a href="/delete/{r['id']}" style="text-decoration:none;">❌</a>
            </div>
        </div>""" for r in latest])
    
    conn.close()
    return f"""
    <html>{get_head_html("Личный Финансовый Помощник")}<body>
        <button class="theme-toggle" onclick="toggleTheme()">🌓</button>
        <div id="aiModal"><div class="modal-content"><h3>🧠 Совет от ИИ</h3><hr style="border:0; border-top:1px solid var(--border); margin:15px 0;"><p id="adviceText"></p><br><button class="btn btn-blue" onclick="document.getElementById('aiModal').style.display='none'">Понятно</button></div></div>
        <div class="container">
            <div class="column">
                <div class="card"><h3>🤖 Аналитика</h3><button class="btn btn-ai" onclick="showAI()">✨ Получить совет ИИ</button></div>
                <div class="card">
                    <h3>{'📝 Изменить' if edit_item else '➕ Новый'} расход</h3>
                    <form method="POST">
                        <input type="hidden" name="id_to_edit" value="{edit_item['id'] if edit_item else ''}">
                        <input type="number" step="0.01" name="amount" placeholder="Сумма" value="{edit_item['amount'] if edit_item else ''}" required>
                        <input type="text" name="main_category" placeholder="Категория" value="{edit_item['main_category'] if edit_item else ''}" required>
                        <input type="text" name="sub_category" placeholder="Описание" value="{edit_item['sub_category'] if edit_item else ''}">
                        <button type="submit" class="btn btn-add">{'Обновить' if edit_item else 'Добавить'}</button>
                    </form>
                </div>
                <div class="card">
                    <h3>⏲️ Настройка лимита</h3>
                    <form method="POST">
                        <input type="number" name="budget_amount" placeholder="Сумма лимита" required>
                        <input type="number" name="budget_days" placeholder="Кол-во дней" required>
                        <button class="btn btn-blue">Установить бюджет</button>
                    </form>
                </div>
            </div>
            <div class="column">
                <div class="card" style="text-align:center;"><h3>Всего затрат: {total} р</h3><img src="/chart.png" style="width:100%; max-width:280px;"></div>
                {budget_html}
                <div class="card"><h3>📜 Последние операции</h3><div style="max-height: 480px; overflow-y: auto; padding-right:5px;">{list_html}</div></div>
            </div>
        </div></body></html>"""

@app.route('/delete/<int:item_id>')
def delete_item(item_id):
    conn = get_db_connection(); conn.execute('DELETE FROM expenses WHERE id = ?', (item_id,)); conn.commit(); conn.close()
    return redirect(url_for('index'))

@app.route('/chart.png')
def chart():
    conn = get_db_connection()
    rows = conn.execute('SELECT main_category, SUM(amount) FROM expenses GROUP BY main_category').fetchall()
    conn.close()
    if not rows: return send_file(BytesIO(), mimetype='image/png')
    plt.figure(figsize=(3, 3))
    plt.pie([r[1] for r in rows], labels=[r[0] for r in rows], autopct='%1.1f%%', textprops={'color':"gray"})
    img = BytesIO(); plt.savefig(img, format='png', transparent=True); img.seek(0); plt.close()
    return send_file(img, mimetype='image/png')

if __name__ == '__main__':
    app.run(debug=True)