# bot.py

import telebot
from telebot import types
import os
from dotenv import load_dotenv
import datetime
from db_manager import DatabaseManager

# --- Инициализация ---
load_dotenv()

# Напрямую читаем токен и имя БД из .env файла
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
DB_FILE = os.getenv('DATABASE_FILE', 'helpdesk.db')

print(f"🚀 Бот запущен. Используется БД: {DB_FILE}")

if not TOKEN:
    print("❌ Ошибка: TELEGRAM_BOT_TOKEN не найден в .env файле!")
    exit()

bot = telebot.TeleBot(TOKEN)
db = DatabaseManager(DB_FILE)
user_data = {}

# --- Обработчики команд ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    text = "Привет! 👋\nЧтобы оставить заявку на ремонт, введите /report"
    bot.send_message(message.chat.id, text)

@bot.message_handler(commands=['report'])
def start_report(message):
    user_id = message.from_user.id
    user_data[user_id] = {}
    
    buildings = db.get_items('buildings')
    if not buildings:
        bot.send_message(user_id, "Система еще не настроена. Обратитесь к администратору.")
        return

    markup = types.InlineKeyboardMarkup(row_width=1)
    buttons = [types.InlineKeyboardButton(text=b['name'], callback_data=f"b_{b['id']}") for b in buildings]
    markup.add(*buttons)
    bot.send_message(user_id, "Шаг 1: Выберите корпус", reply_markup=markup)

# --- Обработчики инлайн-кнопок ---
@bot.callback_query_handler(func=lambda call: call.data.startswith('b_'))
def handle_building_choice(call):
    user_id = call.from_user.id
    building_id = int(call.data.split('_')[1])
    user_data[user_id]['building_id'] = building_id

    rooms = db.get_items('rooms', building_id=building_id)
    if not rooms:
        bot.answer_callback_query(call.id, "В этом корпусе нет помещений.", show_alert=True)
        return

    markup = types.InlineKeyboardMarkup(row_width=1)
    buttons = [types.InlineKeyboardButton(text=r['name'], callback_data=f"r_{r['id']}") for r in rooms]
    markup.add(*buttons)
    bot.edit_message_text("Шаг 2: Выберите помещение", call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('r_'))
def handle_room_choice(call):
    user_id = call.from_user.id
    room_id = int(call.data.split('_')[1])
    user_data[user_id]['room_id'] = room_id

    problems = db.get_items('problem_types', room_id=room_id)
    if not problems:
        bot.answer_callback_query(call.id, "Для этого помещения не заданы типы проблем.", show_alert=True)
        return

    markup = types.InlineKeyboardMarkup(row_width=1)
    buttons = [types.InlineKeyboardButton(text=p['name'], callback_data=f"p_{p['id']}") for p in problems]
    markup.add(*buttons)
    bot.edit_message_text("Шаг 3: Выберите тип проблемы", call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('p_'))
def handle_problem_choice(call):
    user_id = call.from_user.id
    problem_id = int(call.data.split('_')[1])
    user_data[user_id]['problem_type_id'] = problem_id
    
    bot.edit_message_text("Шаг 4: Опишите проблему подробнее (или напишите 'нет')", call.message.chat.id, call.message.message_id)
    bot.register_next_step_handler(call.message, get_problem_details)

# --- Сбор текстовых данных ---
def get_problem_details(message):
    user_id = message.from_user.id
    user_data[user_id]['problem_details'] = message.text
    msg = bot.send_message(user_id, "Шаг 5: Ваше ФИО:")
    bot.register_next_step_handler(msg, get_name)

def get_name(message):
    user_id = message.from_user.id
    user_data[user_id]['name'] = message.text
    msg = bot.send_message(user_id, "Шаг 6: Ваша должность (Преподаватель, Студент и т.д.):")
    bot.register_next_step_handler(msg, get_position)

def get_position(message):
    user_id = message.from_user.id
    user_data[user_id]['position'] = message.text
    
    user_data[user_id].update({
        'user_id': user_id,
        'timestamp': datetime.datetime.now().strftime('%d.%m.%Y %H:%M:%S')
    })
    
    try:
        db.add_request(user_data[user_id])
        bot.send_message(user_id, "✅ Заявка успешно принята!")
    except Exception as e:
        print(f"Ошибка сохранения заявки: {e}")
        bot.send_message(user_id, "❌ Произошла ошибка при сохранении.")
    finally:
        if user_id in user_data:
            del user_data[user_id]

# --- Запуск бота ---
if __name__ == '__main__':
    print("Бот запущен...")
    bot.polling(none_stop=True)