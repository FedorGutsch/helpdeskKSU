# webapp.py

from flask import Flask, render_template, redirect, url_for, flash, request
from db_manager import DatabaseManager
import os
from dotenv import load_dotenv

# --- Инициализация ---
load_dotenv()
app = Flask(__name__)
app.secret_key = 'super-secret-key-for-dev' 

# Напрямую читаем имя БД из .env. Если там не указано, по умолчанию будет 'helpdesk.db'
DB_FILE = os.getenv('DATABASE_FILE', 'helpdesk.db')
print(f"🚀 Веб-интерфейс использует БД: {DB_FILE}")

db = DatabaseManager(DB_FILE)

# --- Маршруты заявок ---
@app.route('/')
def index():
    active_requests = db.get_requests(status='active')
    return render_template('index.html', requests=active_requests, title="Активные заявки")

@app.route('/archive')
def archive_page():
    archived_requests = db.get_requests(status='archived')
    return render_template('index.html', requests=archived_requests, title="Архив заявок")

# --- Маршруты настроек ---
@app.route('/settings')
def settings():
    buildings = db.get_items('buildings')
    return render_template('settings.html', buildings=buildings)

@app.route('/settings/building/<int:building_id>')
def building_details(building_id):
    building = db.get_item_by_id('buildings', building_id)
    rooms = db.get_items('rooms', building_id=building_id)
    return render_template('rooms.html', rooms=rooms, building=building)

@app.route('/settings/room/<int:room_id>')
def room_details(room_id):
    room = db.get_item_by_id('rooms', room_id)
    building = db.get_item_by_id('buildings', room['building_id'])
    problems = db.get_items('problem_types', room_id=room_id)
    return render_template('problems.html', problems=problems, room=room, building=building)

# --- Маршруты действий ---
@app.route('/add/<string:table_name>', methods=['POST'])
def add_item(table_name):
    name = request.form.get('name')
    if name:
        data = {'name': name}
        if table_name == 'rooms':
            data['building_id'] = request.form.get('building_id')
        elif table_name == 'problem_types':
            data['room_id'] = request.form.get('room_id')
        db.add_item(table_name, **data)
        flash(f"Запись '{name}' успешно добавлена.", "success")
    return redirect(request.referrer or url_for('settings'))

@app.route('/delete/<string:table_name>/<int:item_id>', methods=['POST'])
def delete_item(table_name, item_id):
    db.delete_item_by_id(table_name, item_id)
    flash(f"Запись #{item_id} удалена.", "success")
    return redirect(request.referrer or url_for('settings'))

@app.route('/archive/<int:request_id>', methods=['POST'])
def archive_one(request_id):
    if db.archive_request_by_id(request_id):
        flash(f"Заявка #{request_id} успешно перенесена в архив.", "success")
    else:
        flash(f"Ошибка: не удалось архивировать заявку #{request_id}.", "danger")
    return redirect(url_for('index'))

@app.route('/archive_all', methods=['POST'])
def archive_all():
    count = db.archive_all_active()
    flash(f"{count} заявок было успешно перенесено в архив.", "success")
    return redirect(url_for('index'))

# --- Запуск приложения ---
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)