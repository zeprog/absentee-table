from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from google.oauth2 import service_account
from googleapiclient.discovery import build
from config import *

# Загрузка учетных данных из JSON файла
credentials = service_account.Credentials.from_service_account_file('absentee-table-bot-f075bfc93f13.json', scopes=SCOPES)
# Создание сервиса для работы с Google Sheets
service = build('sheets', 'v4', credentials=credentials)
sheet = service.spreadsheets()

def get_confirmation_keyboard():
  buttons = [
    [InlineKeyboardButton(text="Да", callback_data="yes")],
    [InlineKeyboardButton(text="Нет", callback_data="no")],
  ]
  return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_sheet_keyboard(sheets):
  buttons = [[InlineKeyboardButton(text=sheet, callback_data=sheet)] for sheet in sheets]
  return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_sheet_keyboard_for_add_students(sheets):
  buttons = [[InlineKeyboardButton(text=sheet, callback_data=f'list {sheet}')] for sheet in sheets]
  return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_time_keyboard():
  buttons = [
    [InlineKeyboardButton(text="09:00", callback_data="09:00")],
    [InlineKeyboardButton(text="12:00", callback_data="12:00")],
    [InlineKeyboardButton(text="15:00", callback_data="15:00")],
    [InlineKeyboardButton(text="17:00", callback_data="17:00")],
  ]
  keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
  return keyboard

async def list_sheets() -> list:
  try:
    spreadsheet = sheet.get(spreadsheetId=SPREADSHEET_ID).execute()
    sheets = spreadsheet.get('sheets', '')
    sheet_names = [s['properties']['title'] for s in sheets]
    print("Fetched sheet names:", sheet_names)  # Additional debug print
    return sheet_names
  except Exception as e:
    print(f"Error fetching sheets: {str(e)}")  # Debug error print
    return []