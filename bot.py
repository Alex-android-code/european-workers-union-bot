"""Railway entrypoint. Importing this module never starts or authenticates a bot."""
import logging
import os
import re
import time

import telebot
from privacy.onboarding import UI, Store, load_policy, render, revision

MENU = {
    '👷 I’m looking for work': 'candidate',
    '🏢 I’m looking for workers': 'employer',
    '📄 Legalization and documents': 'legal',
    'ℹ️ About EWU': 'about',
    '📞 Contact coordinator': 'contact',
}
FLOWS = {
    'candidate': [('name', 'Your name?'), ('city', 'Your current city?'),
                  ('phone', 'Your contact phone with country code?'), ('profession', 'What work are you looking for?')],
    'employer': [('company', 'Company name?'), ('location', 'Work location?'),
                 ('requirements', 'Describe staffing requirements without other people’s personal data.'), ('phone', 'Contact phone with country code?')],
    'legal': [('country', 'Which country does your question concern?'),
              ('question', 'General question only. Do not send documents, PESEL or medical data.'), ('phone', 'Contact phone with country code?')],
}


def create_bot(token, policy_path, database_path, bot_client=None, backend=None):
    bot = bot_client or telebot.TeleBot(token, threaded=False)
    state = {'store': None}

    def policy():
        try:
            current = load_policy(policy_path)
            if state['store'] is None:
                state['store'] = Store(database_path, current)
            state['store'].policy = current
            return current
        except (OSError, ValueError, TypeError, KeyError):
            # Never log exception text: it may contain a path, secret or user data.
            logging.warning('privacy_configuration_unavailable')
            return None

    def notice(chat_id, current):
        for lang, ui in UI.items():
            if current is None:
                bot.send_message(chat_id, ui['unavailable'], reply_markup=telebot.types.ReplyKeyboardRemove())
                continue
            kb = telebot.types.InlineKeyboardMarkup()
            key = revision(current)
            kb.row(telebot.types.InlineKeyboardButton(ui['continue'], callback_data=f'p:{key}:{lang}:yes'),
                   telebot.types.InlineKeyboardButton(ui['decline'], callback_data=f'p:{key}:{lang}:no'))
            bot.send_message(chat_id, render(current, lang), reply_markup=kb, disable_web_page_preview=True)

    def menu(chat_id):
        kb = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
        for label in MENU:
            kb.add(telebot.types.KeyboardButton(label))
        bot.send_message(chat_id, 'EWU — choose an option. /privacy /withdraw /delete_data', reply_markup=kb)

    @bot.message_handler(func=lambda m: True, content_types=['text', 'photo', 'document', 'contact', 'voice', 'video', 'audio', 'location', 'sticker'])
    def handle(message):
        if message.chat.type != 'private' or message.from_user.is_bot:
            return
        if backend is not None:
            return backend.message(message, bot)
        current = policy()
        if current is None:
            notice(message.chat.id, None)
            return
        store = state['store']
        user_id = message.from_user.id
        lang = message.from_user.language_code or 'uk'
        lang = lang if lang in UI else 'uk'
        text = (message.text or '').strip()
        command = text.split(maxsplit=1)[0].split('@')[0] if text else ''
        if command in ('/withdraw', '/delete_data'):
            action = 'withdrawn' if command == '/withdraw' else 'deletion_requested'
            store.record(user_id, action, lang)
            answer = UI[lang]['stopped'] if action == 'withdrawn' else UI[lang]['deleted'] + current['notices'][lang]['contact']
            bot.send_message(message.chat.id, answer, reply_markup=telebot.types.ReplyKeyboardRemove())
            return
        if command in ('/start', '/reset', '/privacy') or not store.allowed(user_id):
            notice(message.chat.id, current)
            return
        selection = MENU.get(text)
        if selection in FLOWS:
            store.begin_intake(user_id, selection)
            bot.send_message(message.chat.id, FLOWS[selection][0][1] + '\nDo not send identity documents or sensitive data.')
            return
        if selection in ('about', 'contact'):
            bot.send_message(message.chat.id, 'European Workers Union. Contact: ' + current['notices'][lang]['contact'])
            return
        intake = store.intake(user_id)
        if intake and text:
            kind, answers = intake
            steps = FLOWS[kind]
            field, _ = steps[len(answers)]
            if field == 'phone' and not re.fullmatch(r'\+?[0-9][0-9 ()-]{7,18}[0-9]', text):
                bot.send_message(message.chat.id, 'Please enter a phone number with country code.')
                return
            completed = len(answers) + 1 == len(steps)
            store.save_answer(user_id, field, text, completed)
            if completed:
                bot.send_message(message.chat.id, 'Your request has been saved. /privacy /withdraw /delete_data')
                menu(message.chat.id)
            else:
                bot.send_message(message.chat.id, steps[len(answers) + 1][1])
        else:
            bot.send_message(message.chat.id, 'No application has been saved or forwarded. Choose a menu option or use the contact in /privacy.')

    @bot.callback_query_handler(func=lambda c: c.data and c.data.startswith(('p:', 'v2:')))
    def callback(call):
        if backend is not None:
            return backend.callback(call, bot)
        if not call.message or call.message.chat.type != 'private' or call.message.chat.id != call.from_user.id:
            return
        bot.answer_callback_query(call.id)
        current = policy()
        parts = call.data.split(':')
        if current is None or len(parts) != 4 or parts[1] != revision(current) or parts[2] not in UI or parts[3] not in ('yes', 'no'):
            notice(call.message.chat.id, current)
            return
        lang, action = parts[2], parts[3]
        store = state['store']
        store.record(call.from_user.id, 'acknowledged' if action == 'yes' else 'declined', lang)
        if action == 'yes' and store.allowed(call.from_user.id):
            menu(call.message.chat.id)
        else:
            bot.send_message(call.message.chat.id, UI[lang]['stopped'], reply_markup=telebot.types.ReplyKeyboardRemove())

    return bot


def run():
    # SDK exception logs can include Telegram URLs containing the token.
    telebot.logger.disabled = True
    from ewu.config import configured_backend
    backend = configured_backend()
    bot = create_bot(os.environ['TELEGRAM_TOKEN'], os.environ.get('PRIVACY_CONFIG_FILE', ''),
                     os.environ.get('PRIVACY_DB_PATH', '/data/ewu/privacy.sqlite3'), backend=backend)
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    import signal
    stopping = False
    def stop(signum, frame):
        nonlocal stopping
        stopping = True
        bot.stop_polling()
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    while not stopping:
        try:
            bot.infinity_polling(timeout=60, long_polling_timeout=60, skip_pending=False)
        except Exception:
            logging.error('polling_failed')
            if not stopping:
                time.sleep(10)
    if backend is not None:
        backend.service.db.close()


if __name__ == '__main__':
    try:
        run()
    except Exception:
        logging.error('startup_failed')
        raise SystemExit(1) from None
