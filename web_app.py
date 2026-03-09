from flask import Flask, render_template, send_file, request, redirect, url_for
import sqlite3
import matplotlib.pyplot as plt
from io import BytesIO
import matplotlib
import pandas as pd

matplotlib.use('Agg')
app = Flask(__name__)

def get_db_connection():
    conn = sqlite3.connect('finance.db')
    conn.row_factory = sqlite3.Row
    return conn

# Общий шаблон HEAD для всех страниц, чтобы тема работала везде одинаково
def get_head_html(title):
    return f"""
    <head>
        <meta charset="utf-8">
        <title>{title}</title>
        <style>
            :root {{
                --bg: #f0f4f8;
                --card-bg: #ffffff;
                --text: #2c3e50;
                --text-muted: #7f8c8d;
                --border: #dce4ec;
                --input-bg: #ffffff;
                --accent: #4CAF50;
            }}
            [data-theme="dark"] {{
                --bg: #0f172a;
                --card-bg: #1e293b;
                --text: #f1f5f9;
                --text-muted: #94a3b8;
                --border: #334155;
                --input-bg: #0f172a;
                --accent: #10b981;
            }}
            body {{ font-family: 'Segoe UI', sans-serif; background: var(--bg); color: var(--text); transition: 0.3s; margin: 0; padding: 20px; }}
            .card {{ background: var(--card-bg); padding: 25px; border-radius: 15px; box-shadow: 0 10px 25px rgba(0,0,0,0.1); border: 1px solid var(--border); }}
            input {{ width: 100%; padding: 12px; margin: 8px 0; border: 1px solid var(--border); border-radius: 8px; box-sizing: border-box; background: var(--input-bg); color: var(--text); }}
            .btn {{ width: 100%; padding: 12px; border: none; border-radius: 8px; cursor: pointer; font-weight: bold; transition: 0.3s; text-decoration: none; display: block; text-align: center; }}
            .btn-add {{ background: var(--accent); color: white; }}
            .btn-blue {{ background: #2196F3; color: white; }}
            .container {{ display: grid; grid-template-columns: 1fr 1.5fr; gap: 20px; max-width: 1000px; margin: 0 auto; }}
            .transaction-item {{ background: var(--input-bg); padding: 12px; border-radius: 8px; margin-bottom: 10px; border-left: 4px solid var(--accent); display: flex; justify-content: space-between; align-items: center; border: 1px solid var(--border); }}
            .text-muted {{ color: var(--text-muted); font-size: 0.8em; }}
            .scroll-area {{ max-height: 400px; overflow-y: auto; padding-right: 10px; }}
            .theme-toggle {{ position: fixed; top: 20px; right: 20px; padding: 10px 15px; border-radius: 50px; cursor: pointer; background: var(--card-bg); border: 1px solid var(--border); color: var(--text); font-weight: bold; }}
        </style>
        <script>
            (function() {{
                const savedTheme = localStorage.getItem('theme');
                if (savedTheme === 'dark') {{
                    document.documentElement.setAttribute('data-theme', 'dark');
                }}
            }})();
            function toggleTheme() {{
                const html = document.documentElement;
                let newTheme = html.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
                if (newTheme === 'dark') {{ html.setAttribute('data-theme', 'dark'); }}
                else {{ html.removeAttribute('data-theme'); }}
                localStorage.setItem('theme', newTheme);
            }}
        </script>
    </head>"""

@app.route('/', methods=['GET', 'POST'])
def index():
    conn = get_db_connection()
    if request.method == 'POST':
        amount = request.form.get('amount')
        main_cat = request.form.get('main_category')
        sub_cat = request.form.get('sub_category')
        if amount and main_cat:
            conn.execute('INSERT INTO expenses (user_id, amount, main_category, sub_category, date) VALUES (?, ?, ?, ?, date("now"))', (12345, amount, main_cat, sub_cat))
            conn.commit()
            return redirect(url_for('index'))

    total = conn.execute('SELECT SUM(amount) FROM expenses').fetchone()[0] or 0
    latest = conn.execute('SELECT id, sub_category, amount, date FROM expenses ORDER BY id DESC').fetchall()
    conn.close()
    
    list_html = ""
    for row in latest:
        list_html += f"""
        <div class="transaction-item">
            <div><small class="text-muted">{row['date']}</small><br><strong>{row['sub_category']}</strong></div>
            <div style="text-align: right;"><span style="font-weight:bold;">{row['amount']}₽</span><br>
                <a href="/edit/{row['id']}" style="text-decoration:none;">📝</a>
                <a href="/delete/{row['id']}" style="text-decoration:none;">❌</a>
            </div>
        </div>"""

    return f"""
    <html>
        {get_head_html("Finance Dashboard 2026")}
        <body>
            <button class="theme-toggle" onclick="toggleTheme()">🌓 Тема</button>
            <h1 style="text-align: center; margin-bottom: 30px;">📊 Мои Финансы</h1>
            <div class="container">
                <div class="column">
                    <div class="card" style="margin-bottom: 20px;">
                        <h3>➕ Добавить</h3>
                        <form method="POST">
                            <input type="number" name="amount" placeholder="Сумма" required>
                            <input type="text" name="main_category" placeholder="Категория" required>
                            <input type="text" name="sub_category" placeholder="Описание">
                            <button type="submit" class="btn btn-add">Сохранить</button>
                        </form>
                    </div>
                    <div class="card" style="text-align: center;">
                        <h3>Итого: {total} ₽</h3>
                        <a href="/download_excel" class="btn btn-blue" style="margin-top:10px;">📥 Excel</a>
                    </div>
                </div>
                <div class="column">
                    <div class="card" style="margin-bottom: 20px; text-align: center;">
                        <img src="/chart.png" style="width: 100%; max-width: 350px;">
                    </div>
                    <div class="card">
                        <h3>📜 История</h3>
                        <div class="scroll-area">{list_html}</div>
                    </div>
                </div>
            </div>
        </body>
    </html>"""

@app.route('/edit/<int:item_id>', methods=['GET', 'POST'])
def edit_item(item_id):
    conn = get_db_connection()
    if request.method == 'POST':
        amount = request.form.get('amount')
        main_cat = request.form.get('main_category')
        sub_cat = request.form.get('sub_category')
        conn.execute('UPDATE expenses SET amount = ?, main_category = ?, sub_category = ? WHERE id = ?', (amount, main_cat, sub_cat, item_id))
        conn.commit()
        conn.close()
        return redirect(url_for('index'))
    
    item = conn.execute('SELECT * FROM expenses WHERE id = ?', (item_id,)).fetchone()
    conn.close()
    
    return f"""
    <html>
        {get_head_html("Редактирование")}
        <body style="display:flex; justify-content:center; align-items:center; height:100vh; padding:0;">
            <div class="card" style="width:320px;">
                <h3 style="margin-top:0;">📝 Редактировать</h3>
                <form method="POST">
                    <input type="number" name="amount" value="{item['amount']}">
                    <input type="text" name="main_category" value="{item['main_category']}">
                    <input type="text" name="sub_category" value="{item['sub_category']}">
                    <button type="submit" class="btn btn-blue">Сохранить изменения</button>
                </form>
                <a href="/" style="display:block; text-align:center; margin-top:15px; color:var(--text-muted); text-decoration:none;">Отмена</a>
            </div>
        </body>
    </html>"""

@app.route('/delete/<int:item_id>')
def delete_item(item_id):
    conn = get_db_connection()
    conn.execute('DELETE FROM expenses WHERE id = ?', (item_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('index'))

@app.route('/chart.png')
def chart():
    conn = get_db_connection()
    rows = conn.execute('SELECT main_category, SUM(amount) FROM expenses GROUP BY main_category').fetchall()
    conn.close()
    if not rows: return send_file(BytesIO(), mimetype='image/png')
    plt.figure(figsize=(5, 4))
    plt.pie([row[1] for row in rows], labels=[row[0] for row in rows], autopct='%1.1f%%', colors=['#4CAF50', '#FFC107', '#00BCD4', '#F44336', '#9C27B0'], textprops={'color': "#333", 'weight': 'bold'})
    plt.tight_layout()
    img = BytesIO()
    plt.savefig(img, format='png', transparent=True)
    img.seek(0)
    plt.close()
    return send_file(img, mimetype='image/png')

@app.route('/download_excel')
def download_excel():
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT amount, main_category, sub_category, date FROM expenses", conn)
    conn.close()
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Отчет')
    output.seek(0)
    return send_file(output, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', as_attachment=True, download_name='report.xlsx')

if __name__ == '__main__':
    app.run(debug=True, port=5000)