import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
YANDEXGPT_API_KEY = os.getenv("YANDEXGPT_API_KEY")
YANDEX_FOLDER_ID = os.getenv("YANDEX_FOLDER_ID")
ADMIN_ID = os.getenv("ADMIN_ID")
PAYMENT_DETAILS = os.getenv("PAYMENT_DETAILS", "Свяжитесь с администратором для пополнения баланса.")
PRICE_PER_DESCRIPTION = int(os.getenv("PRICE_PER_DESCRIPTION", "50"))
DISCOUNT_PACKAGE_SIZE = int(os.getenv("DISCOUNT_PACKAGE_SIZE", "50"))
DISCOUNT_PERCENT = int(os.getenv("DISCOUNT_PERCENT", "20"))

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не найден. Проверьте файл .env")

if not YANDEXGPT_API_KEY:
    raise ValueError("YANDEXGPT_API_KEY не найден. Проверьте файл .env")

if not YANDEX_FOLDER_ID or YANDEX_FOLDER_ID == "your_folder_id_here":
    raise ValueError("YANDEX_FOLDER_ID не найден или не заполнен. Проверьте файл .env")

if not ADMIN_ID:
    raise ValueError("ADMIN_ID не найден. Проверьте файл .env")
