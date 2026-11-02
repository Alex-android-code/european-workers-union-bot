"""Railway entrypoint. Importing this module never starts or authenticates a bot."""
import logging
import os
import re
import time

import telebot
from privacy.onboarding import UI, Store, load_policy, render, revision
from recruitment import Journey
from bot_text import TEXT
import json

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


def create_bot(token, policy_path, database_path, bot_client=None, admin_ids=()):
    bot = bot_client or telebot.TeleBot(token, threaded=False)
    state = {'store': None, 'journey': None}

    def policy():
        try:
            current = load_policy(policy_path, os.environ.get('PRIVACY_CONFIG_JSON'))
            if state['store'] is None:
                state['store'] = Store(database_path, current)
                state['journey'] = Journey(state['store'], admin_ids)
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

    def menu(chat_id, lang='uk'):
        words = TEXT.get(lang, TEXT['uk'])
        kb = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
        for key in ('candidate','employer','legal','about','contact'):
            kb.add(telebot.types.KeyboardButton(words[key]))
        bot.send_message(chat_id, words['menu'] + '\n/privacy /my_data /withdraw /delete_data', reply_markup=kb)

    @bot.message_handler(func=lambda m: True, content_types=['text', 'photo', 'document', 'contact', 'voice', 'video', 'audio', 'location', 'sticker'])
    def handle(message):
        if message.chat.type != 'private' or message.from_user.is_bot:
            return
        current = policy()
        if current is None:
            request=(message.text or '').strip().split(maxsplit=1)
            rights=request and request[0].split('@')[0] in ('/my_data','/withdraw','/delete_data')
            if rights and state['store'] is not None:
                current=state['store'].policy  # Last reviewed notice; rights stay available during config errors.
            else:
                notice(message.chat.id, None)
                return
        store = state['store']
        journey = state['journey']
        user_id = message.from_user.id
        lang = (message.from_user.language_code or 'uk').lower().split('-')[0].split('_')[0]
        lang = lang if lang in UI else 'uk'
        selected = store.db.execute('SELECT locale FROM privacy_events WHERE user_id=? ORDER BY id DESC LIMIT 1',(user_id,)).fetchone()
        if selected and selected[0] in TEXT: lang=selected[0]
        words = TEXT.get(lang, TEXT['uk'])
        text = (message.text or '').strip()
        command = text.split(maxsplit=1)[0].split('@')[0] if text else ''
        if command in ('/withdraw', '/delete_data'):
            action = 'withdrawn' if command == '/withdraw' else 'deletion_requested'
            store.record(user_id, action, lang)
            journey.pause(user_id)
            answer = UI[lang]['stopped'] if action == 'withdrawn' else UI[lang]['deleted'] + current['notices'][lang]['contact']
            bot.send_message(message.chat.id, answer, reply_markup=telebot.types.ReplyKeyboardRemove())
            return
        if command == '/my_data':
            body=json.dumps(journey.export_own(user_id),ensure_ascii=False,indent=2)
            for begin in range(0,len(body),3500): bot.send_message(message.chat.id,body[begin:begin+3500])
            return
        if command == '/start' and store.allowed(user_id):
            saved=store.intake(user_id)
            if saved:
                kind,answers=saved
                bot.send_message(message.chat.id,words['progress']+' '+str(len(answers)+1)+'/'+str(len(FLOWS[kind]))+': '+words[kind+'_q'][len(answers)])
            else: menu(message.chat.id,lang)
            return
        if command in ('/start', '/reset', '/privacy') or not store.allowed(user_id):
            notice(message.chat.id, current)
            return
        if command == '/status':
            rows=journey.own(user_id)
            bot.send_message(message.chat.id,'\n'.join(f"{r['id']} | {r['status']} | v{r['revision']}" for r in rows) or words['no_apps'])
            return
        if command == '/arrival':
            plan=next((plan for row in journey.own(user_id) if (plan:=journey.arrival(user_id,row['id']))),None)
            bot.send_message(message.chat.id,'\n'.join(plan.values()) if plan else words['no_plan'])
            return
        if command == '/admin_status':
            try:
                _,aid,new_status,number=text.split()
                result=journey.transition(user_id,aid,new_status,int(number))
                bot.send_message(message.chat.id,json.dumps(result))
            except (PermissionError,ValueError):
                bot.send_message(message.chat.id,'Status update refused: check permissions, current revision and transition.')
            return
        if command == '/admin_arrival':
            try:
                _,aid,number,body=text.split(maxsplit=3)
                result=journey.set_plan(user_id,aid,json.loads(body),int(number))
                bot.send_message(message.chat.id,json.dumps(result))
            except (PermissionError,ValueError,TypeError):
                bot.send_message(message.chat.id,'Arrival plan refused: check permissions, revision and required fields.')
            return
        aliases={value:key for group in TEXT.values() for key,value in group.items() if key in ('candidate','employer','legal','about','contact')}
        selection = MENU.get(text) or aliases.get(text)
        if selection in FLOWS:
            store.begin_intake(user_id, selection)
            bot.send_message(message.chat.id, words['progress']+' 1/'+str(len(FLOWS[selection]))+': '+words[selection+'_q'][0])
            return
        if selection in ('about', 'contact'):
            bot.send_message(message.chat.id, 'European Workers Union. ' + UI[lang]['contact'] + ': ' + current['notices'][lang]['contact'])
            return
        intake = store.intake(user_id)
        if intake and text:
            kind, answers = intake
            steps = FLOWS[kind]
            field, _ = steps[len(answers)]
            if field == 'phone' and not re.fullmatch(r'\+?[0-9][0-9 ()-]{7,18}[0-9]', text):
                bot.send_message(message.chat.id, words['phone'])
                return
            completed = len(answers) + 1 == len(steps)
            application_id=store.save_answer(user_id, field, text, completed)
            if completed: journey.register(application_id,lang)
            if completed:
                bot.send_message(message.chat.id, words['saved'])
                menu(message.chat.id,lang)
            else:
                bot.send_message(message.chat.id, words['progress']+' '+str(len(answers)+2)+'/'+str(len(steps))+': '+words[kind+'_q'][len(answers)+1])
        else:
            bot.send_message(message.chat.id, words['unknown'])

    @bot.callback_query_handler(func=lambda c: c.data and c.data.startswith('p:'))
    def callback(call):
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
            menu(call.message.chat.id,lang)
        else:
            bot.send_message(call.message.chat.id, UI[lang]['stopped'], reply_markup=telebot.types.ReplyKeyboardRemove())

    return bot


def run():
    if os.environ.get('EWU_START_ALLOWED') != '1' or os.environ.get('EWU_MAINTENANCE', '1') != '0':
        raise RuntimeError('EWU polling is locked')
    load_policy(os.environ.get('PRIVACY_CONFIG_FILE',''),os.environ.get('PRIVACY_CONFIG_JSON'))
    # SDK exception logs can include Telegram URLs containing the token.
    telebot.logger.disabled = True
    bot = create_bot(os.environ['TELEGRAM_TOKEN'], os.environ.get('PRIVACY_CONFIG_FILE', ''),
                     os.environ.get('PRIVACY_DB_PATH', '/data/ewu/privacy.sqlite3'),
                     admin_ids=[x.strip() for x in os.environ.get('EWU_ADMIN_IDS','').split(',') if x.strip()])
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    while True:
        try:
            bot.infinity_polling(timeout=60, long_polling_timeout=60, skip_pending=False)
        except Exception:
            logging.error('polling_failed')
            time.sleep(10)


if __name__ == '__main__':
    run()

