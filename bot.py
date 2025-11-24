import telebot
from telebot import types
from telebot.types import BotCommand, BotCommandScopeDefault, BotCommandScopeChat
import sqlite3
import pandas as pd
import os
import datetime
from dotenv import load_dotenv
import threading  # Для защиты логов от гонки потоков

# --- Инициализация ---
load_dotenv()
telegram_key = os.getenv('TELEGRAM_BOT_TOKEN')

if not telegram_key:
    print("❌ Ошибка: Токен не найден в файле .env")
    exit()

bot = telebot.TeleBot(telegram_key)

# Файлы
DB_FILE = 'helpdesk.db'
ADMIN_IDS_FILE = 'admin_ids.txt'
LOG_FILE = 'bot_logs.txt'

# Константы кнопок
BTN_EXCEL = "📥 Текущие заявки"
BTN_ARCHIVE = "🗄 Архив заявок"
BTN_CLEAR = "🗑 Очистить список"

# Глобальные переменные
users_step = {}
admin_ids = set()

# Категории проблем (Эмодзи остаются здесь для красоты кнопок)
CATEGORIES = ["⚡ Электрика", "🚽 Сантехника/Тепло", "🪑 Мебель/Двери", "💻 Компьютеры/Проекторы", "📦 Прочее"]

# Объект блокировки для потокобезопасной записи логов
log_lock = threading.Lock()

# --- ФУНКЦИЯ ЛОГИРОВАНИЯ (Thread-safe) ---
def save_user_log(message):
    """
    Записывает ID пользователя.
    Использует Lock, чтобы избежать гонки потоков.
    Очищает файл, если наступил новый день.
    """
    user = message.from_user
    now = datetime.datetime.now()
    today_str = now.strftime('%Y-%m-%d')
    time_str = now.strftime('%H:%M:%S')
    
    log_entry = f"[{time_str}] ID: {user.id} | @{user.username} | {user.first_name}\n"
    
    # Блокируем доступ к файлу для других потоков
    with log_lock:
        mode = 'a' # По умолчанию - дописываем
        
        # Проверяем дату изменения файла
        if os.path.exists(LOG_FILE):
            try:
                file_time = os.path.getmtime(LOG_FILE)
                file_date = datetime.datetime.fromtimestamp(file_time).strftime('%Y-%m-%d')
                
                # Если файл вчерашний (или старше) - перезаписываем ('w')
                if file_date != today_str:
                    mode = 'w'
            except OSError:
                # Если файл удалили или ошибка доступа - создаем новый
                mode = 'w'
        
        try:
            with open(LOG_FILE, mode, encoding='utf-8') as f:
                f.write(log_entry)
        except Exception as e:
            print(f"Ошибка записи лога: {e}")

# --- Загрузка Админов ---
def load_admin_ids():
    ids = set()
    if os.path.exists(ADMIN_IDS_FILE):
        with open(ADMIN_IDS_FILE, 'r') as f:
            for line in f:
                line = line.strip()
                if line.isdigit():
                    ids.add(int(line))
    return ids

# --- Работа с Базой Данных ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            corp TEXT,
            cab TEXT,
            category TEXT,
            problem TEXT,
            name TEXT,
            position TEXT,
            status TEXT DEFAULT 'active'
        )
    ''')
    conn.commit()
    conn.close()

def add_request_to_db(data):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    timestamp = datetime.datetime.now().strftime('%d.%m.%Y %H:%M:%S')
    cursor.execute('''
        INSERT INTO requests (timestamp, corp, cab, category, problem, name, position)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (timestamp, data['corp'], data['cab'], data['category'], data['problem'], data['name'], data['position']))
    conn.commit()
    conn.close()

def get_active_requests_count():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM requests WHERE status='active'")
    try:
        count = cursor.fetchone()[0]
    except TypeError:
        count = 0
    conn.close()
    return count

def archive_all_active():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("UPDATE requests SET status='archived' WHERE status='active'")
    changes = conn.total_changes
    conn.commit()
    conn.close()
    return changes

# --- Генерация Excel ---
def generate_excel_report():
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql_query("SELECT * FROM requests WHERE status='active'", conn)
    conn.close()

    if df.empty: return None

    now_str = datetime.datetime.now().strftime('%d.%m.%Y_%H-%M')
    filename = f"{now_str}_Активные.xlsx"

    df.columns = ['ID', 'Время', 'Корпус', 'Кабинет', 'Категория', 'Проблема', 'ФИО', 'Должность', 'Статус']
    df = df.sort_values(by='ID')
    df.to_excel(filename, index=False)
    return filename

def generate_archive_report():
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql_query("SELECT * FROM requests WHERE status='archived'", conn)
    conn.close()

    if df.empty: return None

    now_str = datetime.datetime.now().strftime('%d.%m.%Y_%H-%M')
    filename = f"{now_str}_Архив.xlsx"

    df.columns = ['ID', 'Время', 'Корпус', 'Кабинет', 'Категория', 'Проблема', 'ФИО', 'Должность', 'Статус']
    df = df.sort_values(by='ID', ascending=False)
    df.to_excel(filename, index=False)
    return filename

# --- Вспомогательные функции ---

def create_category_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    buttons = [types.KeyboardButton(cat) for cat in CATEGORIES]
    markup.add(*buttons)
    return markup

def create_main_keyboard(user_id):
    """
    Админ -> Клавиатура с ТЕКСТОВЫМИ кнопками.
    Студент -> Удаление клавиатуры.
    """
    if user_id in admin_ids:
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.row(types.KeyboardButton(BTN_EXCEL), types.KeyboardButton(BTN_ARCHIVE))
        markup.row(types.KeyboardButton(BTN_CLEAR))
        return markup
    else:
        return types.ReplyKeyboardRemove()

def check_cancel(message):
    """
    Перехват команд ИЛИ нажатий на кнопки админа во время опроса.
    """
    if message.content_type != 'text': return False
    
    text = message.text
    is_command = text.startswith('/')
    is_admin_btn = text in [BTN_EXCEL, BTN_ARCHIVE, BTN_CLEAR]

    if is_command or is_admin_btn:
        chat_id = message.chat.id
        if chat_id in users_step:
            del users_step[chat_id]
        
        # Обработка команд и кнопок
        if text == '/start': send_welcome(message)
        elif text == '/report': start_report(message)
        
        # Обработка админских кнопок (или команд, если введут вручную)
        elif text == BTN_EXCEL or text == '/get_excel': send_excel(message)
        elif text == BTN_ARCHIVE or text == '/get_archive': send_archive(message)
        elif text == BTN_CLEAR or text == '/clear_active': ask_clear(message)
        
        else: send_welcome(message)
            
        return True
    return False

# --- Обработчики команд ---

@bot.message_handler(commands=['start'])
def send_welcome(message):
    global admin_ids
    admin_ids = load_admin_ids()
    
    if not os.path.exists(DB_FILE): init_db()
    
    # --- ЗАПИСЬ В ЛОГ ---
    save_user_log(message)
    # --------------------
    
    text = "Привет! 👋\nЧтобы оставить заявку на ремонт, нажмите на кнопку **Меню** слева внизу или введите /report"
    bot.send_message(message.chat.id, text, parse_mode='Markdown', reply_markup=create_main_keyboard(message.chat.id))

# --- АДМИН: Скачать Активные ---
@bot.message_handler(func=lambda message: message.text == BTN_EXCEL)
def send_excel(message):
    if message.chat.id not in admin_ids: return

    count = get_active_requests_count()
    if count == 0:
        bot.send_message(message.chat.id, "📂 Активных заявок нет.")
        return

    file_path = generate_excel_report()
    if file_path:
        try:
            with open(file_path, 'rb') as f:
                bot.send_document(message.chat.id, f, caption=f"📊 Активные заявки: {count} шт.")
        finally:
            if os.path.exists(file_path): os.remove(file_path)
    else:
        bot.send_message(message.chat.id, "Ошибка генерации файла.")

# --- АДМИН: Скачать Архив ---
@bot.message_handler(func=lambda message: message.text == BTN_ARCHIVE)
def send_archive(message):
    if message.chat.id not in admin_ids: return

    file_path = generate_archive_report()
    if file_path:
        try:
            with open(file_path, 'rb') as f:
                bot.send_document(message.chat.id, f, caption="🗄 Полный архив выполненных заявок.")
        finally:
            if os.path.exists(file_path): os.remove(file_path)
    else:
        bot.send_message(message.chat.id, "📂 Архив пуст.")

# --- АДМИН: Очистка ---
@bot.message_handler(func=lambda message: message.text == BTN_CLEAR)
def ask_clear(message):
    if message.chat.id not in admin_ids: return
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("Да, перенести в архив", callback_data="confirm_clear"))
    markup.add(types.InlineKeyboardButton("Отмена", callback_data="cancel_clear"))
    
    bot.send_message(message.chat.id, "⚠️ Выполнили все работы?\nЭта кнопка перенесет текущие заявки в **Архив** и очистит список.", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data in ['confirm_clear', 'cancel_clear'])
def handle_clear_callback(call):
    if call.data == "confirm_clear":
        count = archive_all_active()
        bot.edit_message_text(f"✅ Готово. {count} заявок перенесено в архив.", call.message.chat.id, call.message.message_id)
    else:
        bot.edit_message_text("Операция отменена.", call.message.chat.id, call.message.message_id)

# --- Сценарий создания заявки ---

@bot.message_handler(commands=['report'])
def start_report(message):
    users_step[message.chat.id] = {}
    msg = bot.send_message(message.chat.id, "1. Введите номер корпуса:", reply_markup=types.ReplyKeyboardRemove())
    bot.register_next_step_handler(msg, get_corp)

def get_corp(message):
    if check_cancel(message): return
    users_step[message.chat.id]['corp'] = message.text
    msg = bot.send_message(message.chat.id, "2. Введите номер кабинета:")
    bot.register_next_step_handler(msg, get_cab)

def get_cab(message):
    if check_cancel(message): return
    users_step[message.chat.id]['cab'] = message.text
    msg = bot.send_message(message.chat.id, "3. Выберите категорию проблемы:", reply_markup=create_category_keyboard())
    bot.register_next_step_handler(msg, get_category)

def get_category(message):
    if check_cancel(message): return
    
    category_raw = message.text
    if category_raw not in CATEGORIES:
        msg = bot.send_message(message.chat.id, "Пожалуйста, выберите категорию из кнопок ниже.", reply_markup=create_category_keyboard())
        bot.register_next_step_handler(msg, get_category)
        return

    # --- ИЗМЕНЕНИЕ: Очистка от эмодзи ---
    # "⚡ Электрика" -> split(' ', 1) -> ["⚡", "Электрика"] -> берем [1]
    try:
        category_clean = category_raw.split(' ', 1)[1]
    except IndexError:
        # На случай, если пробела нет (хотя в кнопках он есть)
        category_clean = category_raw

    users_step[message.chat.id]['category'] = category_clean
    
    msg = bot.send_message(message.chat.id, "4. Опишите проблему подробнее:", reply_markup=types.ReplyKeyboardRemove())
    bot.register_next_step_handler(msg, get_problem)

def get_problem(message):
    if check_cancel(message): return
    users_step[message.chat.id]['problem'] = message.text
    msg = bot.send_message(message.chat.id, "5. Ваше ФИО:")
    bot.register_next_step_handler(msg, get_name)

def get_name(message):
    if check_cancel(message): return
    users_step[message.chat.id]['name'] = message.text
    msg = bot.send_message(message.chat.id, "6. Ваша должность (Преподаватель, Студент, Сотрудник):")
    bot.register_next_step_handler(msg, get_position)

def get_position(message):
    if check_cancel(message): return
    chat_id = message.chat.id
    users_step[chat_id]['position'] = message.text
    
    try:
        add_request_to_db(users_step[chat_id])
        bot.send_message(chat_id, "✅ Заявка успешно принята!", reply_markup=create_main_keyboard(chat_id))
    except Exception as e:
        print(f"Error: {e}")
        bot.send_message(chat_id, "❌ Произошла ошибка при сохранении.")
    
    if chat_id in users_step:
        del users_step[chat_id]

# --- Запуск и настройка Меню ---
if __name__ == '__main__':
    admin_ids = load_admin_ids()
    init_db()

    print("Настраиваю меню команд...")
    
    # Меню одинаковое для всех (только пользовательские команды)
    common_commands = [
        BotCommand("start", "🔄 Перезапустить"),
        BotCommand("report", "📝 Оставить заявку")
    ]

    bot.set_my_commands(common_commands, scope=BotCommandScopeDefault())
    
    # Очистка старых меню админов (чтобы убрать лишние команды из меню)
    for admin_id in admin_ids:
        try:
            bot.delete_my_commands(scope=BotCommandScopeChat(admin_id))
        except Exception:
            pass

    print("Бот запущен...")
    bot.polling(none_stop=True)