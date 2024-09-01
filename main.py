import os
import re
import signal
import subprocess
import logging
import asyncio
import sqlite3
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.memory import MemoryStorage
from utils import *
from config import *

# Завершение всех процессов с именем python или python3
def kill_existing_processes():
    try:
        result = subprocess.run(['pgrep', '-f', 'python'], capture_output=True, text=True)
        pids = result.stdout.split()
        for pid in pids:
            os.kill(int(pid), signal.SIGKILL)
        print("Existing processes killed successfully.")
    except Exception as e:
        print(f"Failed to kill existing processes: {e}")

# Вызов функции перед запуском нового экземпляра бота
kill_existing_processes()

logging.basicConfig(level=logging.INFO)

# Загрузка учетных данных из JSON файла
credentials = service_account.Credentials.from_service_account_file('absentee-table-bot-f075bfc93f13.json', scopes=SCOPES)
# Создание сервиса для работы с Google Sheets
service = build('sheets', 'v4', credentials=credentials)
sheet = service.spreadsheets()

bot = Bot(TOKEN)
storage = MemoryStorage()
dp = Dispatcher()

# Создаем соединение с базой данных SQLite
conn = sqlite3.connect('user_data.db')
cursor = conn.cursor()

# Создаем таблицу, если она не существует
cursor.execute('''
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    default_class TEXT,
    reminder_time TEXT
)
''')
conn.commit()

class UserState(StatesGroup):
    waiting_for_class = State()
    waiting_for_time = State()
    waiting_for_sheet = State()
    waiting_for_absentees = State()
    waiting_for_confirmation = State()
    initial_setup_done = State()

@dp.message(CommandStart())
async def send_welcome(message: types.Message, state: FSMContext):
    cursor.execute("SELECT default_class, reminder_time FROM users WHERE user_id=?", (message.from_user.id,))
    user_data = cursor.fetchone()

    if user_data:
        await message.reply(
            "Привет еще раз! Вы выбрали уже класс и время напоминания.\nЧтобы изменить класс, выберите команду /change_class.\nЧтобы изменить время, выберите команду /set_reminder\nЧтобы посмотреть информацию интересующей даты, выберите команду /read"
        )
    else:
        await state.set_state(UserState.waiting_for_class)
        await message.reply(
            "Привет! Я ваш менеджер отсутствующих в классе!\nПожалуйста, выберите класс по умолчанию."
        )

@dp.message(UserState.waiting_for_class)
async def set_default_class(message: types.Message, state: FSMContext):
    await state.update_data(default_class=message.text.lower())
    logging.info(f"Default class set to: {message.text.lower()}")

    cursor.execute("INSERT OR REPLACE INTO users (user_id, username, default_class) VALUES (?, ?, ?)", 
                   (message.from_user.id, message.from_user.username, message.text.lower()))
    conn.commit()
    logging.info("Database updated with default class")

    await message.reply(f"Класс по умолчанию установлен на: {message.text.lower()}")
    await state.set_state(UserState.waiting_for_time)
    sent_message = await message.reply("Пожалуйста, выберите время для напоминания или введите свое в формате ЧЧ:ММ.", reply_markup=get_time_keyboard())
    await state.update_data(keyboard_message_id=sent_message.message_id)

@dp.message(Command(commands=['change_class']))
async def change_class(message: types.Message, state: FSMContext):
    await state.set_state(UserState.waiting_for_class)
    await message.reply("Пожалуйста, введите новый класс по умолчанию.")

@dp.message(Command(commands=['set_reminder']))
async def set_reminder(message: types.Message, state: FSMContext):
    await state.set_state(UserState.waiting_for_time)
    sent_message = await message.reply("Пожалуйста, выберите время для напоминания или введите свое в формате ЧЧ:ММ.", reply_markup=get_time_keyboard())
    await state.update_data(keyboard_message_id=sent_message.message_id)

@dp.callback_query(UserState.waiting_for_time)
async def choose_time(callback_query: types.CallbackQuery, state: FSMContext):
    reminder_time = callback_query.data

    cursor.execute("SELECT default_class FROM users WHERE user_id=?", (callback_query.from_user.id,))
    result = cursor.fetchone()
    default_class = result[0] if result else None

    if default_class is None:
        await callback_query.message.answer("Класс по умолчанию не установлен. Пожалуйста, установите класс.")
        return

    cursor.execute("INSERT OR REPLACE INTO users (user_id, username, default_class, reminder_time) VALUES (?, ?, ?, ?)", 
                   (callback_query.from_user.id, callback_query.from_user.username, default_class, reminder_time))
    conn.commit()

    await callback_query.message.answer(f"Напоминание установлено на {reminder_time}")
    await state.clear()

    await bot.edit_message_reply_markup(callback_query.message.chat.id, callback_query.message.message_id, reply_markup=None)

@dp.message(UserState.waiting_for_time)
async def set_custom_time(message: types.Message, state: FSMContext):
    try:
        # Проверка формата времени
        reminder_time = datetime.strptime(message.text, "%H:%M").time()
        logging.info(f"Valid time format: {reminder_time}")

        # Получение данных из состояния
        user_data = await state.get_data()
        default_class = user_data.get('default_class')
        logging.info(f"Default class from state: {default_class}")

        if not default_class:
            cursor.execute("SELECT default_class FROM users WHERE user_id=?", (message.from_user.id,))
            result = cursor.fetchone()
            default_class = result[0] if result else None
            logging.info(f"Default class from database: {default_class}")

            if not default_class:
                await message.reply("Класс по умолчанию не установлен. Пожалуйста, установите класс.")
                return

        # Обновление данных в базе данных
        cursor.execute("INSERT OR REPLACE INTO users (user_id, username, default_class, reminder_time) VALUES (?, ?, ?, ?)", 
                       (message.from_user.id, message.from_user.username, default_class, message.text))
        conn.commit()
        logging.info("Database updated successfully")

        # Удаление клавиатуры после установки времени
        data = await state.get_data()
        keyboard_message_id = data.get('keyboard_message_id')
        if keyboard_message_id:
            await bot.edit_message_reply_markup(chat_id=message.chat.id, message_id=keyboard_message_id, reply_markup=None)

        await message.reply(f"Напоминание установлено на {message.text}")
        await state.clear()
    except ValueError:
        await message.reply("Неверный формат времени. Пожалуйста, введите время в формате ЧЧ:ММ.")
        logging.error("Invalid time format entered")
    except Exception as e:
        await message.reply(f"Произошла ошибка: {str(e)}")
        logging.error(f"Error setting custom time: {str(e)}")

async def check_reminders():
    while True:
        now = datetime.now().strftime("%H:%M")
        cursor.execute("SELECT user_id, reminder_time FROM users")
        for row in cursor.fetchall():
            user_id, reminder_time = row
            if reminder_time == now:
                await bot.send_message(user_id, "Вы сегодня отмечали отсутствующих?", reply_markup=get_confirmation_keyboard())
        await asyncio.sleep(60)

@dp.callback_query(lambda c: c.data and c.data == 'yes' or c.data == 'no' or c.data == 'Да' or c.data == 'Нет')
async def handle_confirmation(callback_query: types.CallbackQuery, state: FSMContext):
    print(f'FROM handle_confirmation {callback_query.data}')
    if callback_query.data == "yes":
        await callback_query.message.answer("Спасибо! Хорошего дня!")
    elif callback_query.data == "no":
        await state.set_state(UserState.waiting_for_sheet)
        current_state = await state.get_state()
        logging.info(f"Current state after setting: {current_state}")
        sheets = await list_sheets()
        await callback_query.message.answer("Выберите лист:", reply_markup=get_sheet_keyboard_for_add_students(sheets))

@dp.callback_query(UserState.waiting_for_sheet)
async def choose_sheet(callback_query: types.CallbackQuery, state: FSMContext):
    logging.info(f"Sheet selected: {callback_query.data}")  # Лог выбранного листа
    await state.update_data(selected_sheet=callback_query.data)
    await callback_query.message.answer(f"Вы выбрали лист: {callback_query.data}. Теперь введите отсутствующих через пробел (ОРВИ, Ковид, Грипп, Другое заболевание, Другая причина (Ув., Неув.)).")
    await state.set_state(UserState.waiting_for_absentees)

@dp.message(UserState.waiting_for_absentees)
async def handle_absentees(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    
    # Retrieve the selected sheet and the user's default class from the database
    selected_sheet = user_data.get('selected_sheet')
    selected_sheet = re.findall("\d+\.\d+", selected_sheet)[0]
    cursor.execute("SELECT default_class FROM users WHERE user_id=?", (message.from_user.id,))
    result = cursor.fetchone()
    default_class = result[0] if result else None

    if not selected_sheet:
        await message.reply("Лист не выбран. Пожалуйста, выберите лист.")
        return

    if not default_class:
        await message.reply("Класс не найден в базе данных. Пожалуйста, установите класс по умолчанию.")
        return

    try:
        # Retrieve the first column data from the selected sheet
        range_name = f"{selected_sheet}!A:A"  # First column (A) of the selected sheet
        result = sheet.values().get(spreadsheetId=SPREADSHEET_ID, range=range_name).execute()
        values = result.get('values', [])

        # Find the row index where the first column matches the default_class
        row_index = None
        for i, row in enumerate(values):
            if row and row[0] == default_class:  # Check if the class matches
                row_index = i + 1  # Google Sheets index starts from 1
                break

        if row_index is None:
            await message.reply(f"Класс '{default_class}' не найден в листе.")
            return

        # Prepare the absentees data for the specified row
        absentees = message.text.split(' ')
        range_name = f"{selected_sheet}!B{row_index}:G{row_index}"  # Columns B to G for the matched row

        # Update the Google Sheet with the absentees data
        sheet.values().update(
            spreadsheetId=SPREADSHEET_ID,
            range=range_name,
            valueInputOption="RAW",
            body={"values": [absentees]}
        ).execute()

        await message.reply("Спасибо, данные записаны.")
        await state.clear()  # Finish the state
    except Exception as e:
        await message.reply(f"Ошибка при записи в таблицу: {str(e)}")
        logging.error(f"Error updating Google Sheet: {str(e)}")

@dp.message(Command(commands=['read']))
async def choose_sheet(message: types.Message, state: FSMContext):
    cursor.execute("SELECT default_class FROM users WHERE user_id=?", (message.from_user.id,))
    user_data = cursor.fetchone()

    if user_data:
        default_class = user_data[0]
    else:
        default_class = 'Не установлен'

    list_read = await list_sheets()
    buttons = [[InlineKeyboardButton(text=name, callback_data=name)] for name in list_read]
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.reply(f"Выберите лист (Класс по умолчанию: {default_class}):", reply_markup=keyboard)

@dp.callback_query(lambda c: c.data and not c.data.startswith("yes") and not c.data.startswith("no"))
async def read_data(callback_query: types.CallbackQuery, state: FSMContext):
    print(f'FROM READ DATA {callback_query.data}')
    sheet_name = callback_query.data
    range_name = f"{sheet_name}!A1:G32"
    try:
        result = sheet.values().get(spreadsheetId=SPREADSHEET_ID, range=range_name).execute()
        values = result.get('values', [])
        if not values:
            await callback_query.message.answer("No data found.")
        else:
            response = f"Данные из листа {sheet_name}:\n\n"
            for i, row in enumerate(values, start=1):
                response += f"{i}. " + ", ".join(row) + "\n"
            await callback_query.message.answer(response)
    except Exception as e:
        await callback_query.message.answer(f"Error: {str(e)}")

async def main() -> None:
    asyncio.create_task(check_reminders())
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())