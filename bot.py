import os
import time
import logging
import telebot

TOKEN = os.environ["TELEGRAM_TOKEN"]
ADMIN_TELEGRAM_ID = os.getenv("ADMIN_TELEGRAM_ID", "").strip()
BRAND = "European Workers Union"
bot = telebot.TeleBot(TOKEN)

def notify_admin(text):
    if ADMIN_TELEGRAM_ID:
        try:
            bot.send_message(int(ADMIN_TELEGRAM_ID), text)
        except Exception:
            logging.exception("Admin notification failed")

@bot.message_handler(commands=["start"])
def start(message):
    kb = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    for label in [
        "👷 I’m looking for work",
        "🏢 I’m looking for workers",
        "📄 Legalization and documents",
        "ℹ️ About EWU",
        "📞 Contact coordinator",
    ]:
        kb.add(telebot.types.KeyboardButton(label))
    bot.send_message(
        message.chat.id,
        "Welcome to European Workers Union (EWU).\n\n"
        "We connect workers with employers across Poland and Europe. "
        "Choose an option below:",
        reply_markup=kb,
    )

@bot.message_handler(func=lambda m: True)
def handle(message):
    text = (message.text or "").strip()
    responses = {
        "ℹ️ About EWU": "European Workers Union (EWU) connects workers and employers across Poland and Europe.",
        "📞 Contact coordinator": "Please send your name, phone number and a short description of your request.",
        "👷 I’m looking for work": "Please send your full name, current city, phone number and the type of work you are looking for.",
        "🏢 I’m looking for workers": "Please send your company name, location, required number of workers and contact details.",
        "📄 Legalization and documents": "Please describe what document or legalization support you need and the country where you are currently located.",
    }
    bot.send_message(message.chat.id, responses.get(text, "Thank you. Your message has been received. Use /start to open the EWU menu."))
    if text not in responses:
        notify_admin(f"EWU message from {message.from_user.id}: {text}")

def run():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        bot.set_my_name(BRAND)
    except Exception:
        logging.exception("Could not update Telegram display name")
    while True:
        try:
            bot.remove_webhook()
            logging.info("European Workers Union bot polling started")
            bot.infinity_polling(timeout=60, long_polling_timeout=60, skip_pending=False)
        except Exception:
            logging.exception("Polling error; restarting in 10 seconds")
            time.sleep(10)

if __name__ == "__main__":
    run()
