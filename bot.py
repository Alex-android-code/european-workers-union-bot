"""Railway entrypoint. Importing this module never starts or authenticates a bot."""
import logging
import os
import re
import time

import telebot
from privacy.onboarding import UI, Store, load_policy, render, revision
from recruitment import Journey
from bot_text import TEXT, RIGHTS
import json
from pathlib import Path
from statuses import label

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
    selected_languages = {}
    cached_policy=Path(database_path).with_name('last-reviewed-policy.json')

    def policy():
        try:
            current = load_policy(policy_path, os.environ.get('PRIVACY_CONFIG_JSON'))
            if state['store'] is None:
                state['store'] = Store(database_path, current)
                state['journey'] = Journey(state['store'], admin_ids)
            state['store'].policy = current
            # A private last-known reviewed policy keeps rights available after
            # a restart during configuration loss. It never enables new intake.
            cached_policy.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
            raw=json.dumps(current,ensure_ascii=False)
            if not cached_policy.exists() or cached_policy.read_text(encoding='utf-8')!=raw:
                temporary=cached_policy.with_suffix('.partial')
                fd=os.open(temporary,os.O_CREAT|os.O_TRUNC|os.O_WRONLY,0o600)
                with os.fdopen(fd,'w',encoding='utf-8') as stream:stream.write(raw)
                os.replace(temporary,cached_policy)
            return current
        except (OSError, ValueError, TypeError, KeyError):
            # Never log exception text: it may contain a path, secret or user data.
            logging.warning('privacy_configuration_unavailable')
            if state['store'] is None and cached_policy.is_file():
                try:
                    previous=load_policy(cached_policy)
                    state['store']=Store(database_path,previous)
                    state['journey']=Journey(state['store'],admin_ids)
                except (OSError,ValueError,TypeError,KeyError):pass
            return None

    def language_picker(chat_id, lang='uk'):
        kb=telebot.types.InlineKeyboardMarkup(row_width=2)
        for code,label in [('uk','Українська'),('pl','Polski'),('ru','Русский'),('en','English'),('de','Deutsch'),('es','Español'),('pt','Português')]:
            kb.add(telebot.types.InlineKeyboardButton(label,callback_data='lang:'+code))
        bot.send_message(chat_id,RIGHTS[lang][2],reply_markup=kb)

    def notice(chat_id, current, lang=None):
        lang=lang or selected_languages.get(chat_id,'uk')
        ui=UI[lang]
        if current is None:
            bot.send_message(chat_id,ui['unavailable'],reply_markup=telebot.types.ReplyKeyboardRemove())
            return
        kb=telebot.types.InlineKeyboardMarkup()
        key=revision(current)
        kb.row(telebot.types.InlineKeyboardButton(ui['continue'],callback_data=f'p:{key}:{lang}:yes'),
               telebot.types.InlineKeyboardButton(ui['decline'],callback_data=f'p:{key}:{lang}:no'))
        bot.send_message(chat_id,render(current,lang),reply_markup=kb,disable_web_page_preview=True)
        # Record delivery after Telegram accepts the send, not on button click.
        state['store'].record(chat_id,'presented',lang)

    def menu(chat_id, lang='uk'):
        words = TEXT.get(lang, TEXT['uk'])
        kb = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
        for key in ('candidate','employer','legal','about','contact'):
            kb.add(telebot.types.KeyboardButton(words[key]))
        bot.send_message(chat_id, words['menu'] + '\n/privacy /my_data /status /withdraw /delete_data\n/correct /restrict /export_data /object', reply_markup=kb)

    @bot.message_handler(func=lambda m: True, content_types=['text', 'photo', 'document', 'contact', 'voice', 'video', 'audio', 'location', 'sticker'])
    def handle(message):
        if message.chat.type != 'private' or message.from_user.is_bot:
            return
        user_id=message.from_user.id
        device=(message.from_user.language_code or 'uk').lower().split('-')[0].split('_')[0]
        fallback=device if device in UI else 'uk'
        current = policy()
        if current is None:
            request=(message.text or '').strip().split(maxsplit=1)
            rights=request and request[0].split('@')[0] in ('/my_data','/status','/withdraw','/delete_data','/correct','/restrict','/export_data','/object')
            if rights and state['store'] is not None:
                current=state['store'].policy  # Last reviewed notice; rights stay available during config errors.
            else:
                if request and request[0].split('@')[0]=='/start':language_picker(message.chat.id,fallback)
                else:notice(message.chat.id, None,selected_languages.get(user_id,fallback))
                return
        store = state['store']
        journey = state['journey']
        lang = (message.from_user.language_code or 'uk').lower().split('-')[0].split('_')[0]
        lang = lang if lang in UI else 'uk'
        selected = store.db.execute('SELECT locale FROM privacy_events WHERE user_id=? ORDER BY id DESC LIMIT 1',(user_id,)).fetchone()
        if selected and selected[0] in TEXT: lang=selected[0]
        lang=selected_languages.get(user_id,store.locale(user_id) or lang)
        words = TEXT.get(lang, TEXT['uk'])
        text = (message.text or '').strip()
        command = text.split(maxsplit=1)[0].split('@')[0] if text else ''
        if command in ('/withdraw', '/delete_data', '/restrict', '/object'):
            action = 'withdrawn' if command == '/withdraw' else 'deletion_requested'
            if command in ('/restrict','/object'):action='restricted'
            store.record(user_id, action, lang)
            journey.pause(user_id)
            kind={'/withdraw':'objection','/delete_data':'erasure','/restrict':'restriction','/object':'objection'}[command]
            request_id=store.request(user_id,kind)
            answer = UI[lang]['stopped'] if action == 'withdrawn' else UI[lang]['deleted'] + current['notices'][lang]['contact']
            if action=='restricted':answer=RIGHTS[lang][0]+request_id
            bot.send_message(message.chat.id, answer, reply_markup=telebot.types.ReplyKeyboardRemove())
            return
        if command == '/correct':
            parts=text.split(maxsplit=2)
            if len(parts)!=3 or parts[1] not in ('name','city','phone','profession') or len(parts[2])>1000:
                bot.send_message(message.chat.id,RIGHTS[lang][1]);return
            request_id=store.request(user_id,'rectification',dict(field=parts[1],value=parts[2]))
            bot.send_message(message.chat.id,RIGHTS[lang][0]+request_id);return
        if command in ('/my_data','/export_data'):
            if command=='/export_data':store.request(user_id,'portability')
            body=json.dumps(journey.export_own(user_id),ensure_ascii=False,indent=2)
            for begin in range(0,len(body),3500): bot.send_message(message.chat.id,body[begin:begin+3500])
            return
        if command in ('/start','/language'):
            language_picker(message.chat.id,lang)
            return
        if command == '/status':
            rows=journey.own(user_id)
            bot.send_message(message.chat.id,'\n'.join(f"{r['id']} | {label(r['status'],lang)} | v{r['revision']}" for r in rows) or words['no_apps'])
            return
        if command in ('/reset','/privacy') or not store.allowed(user_id):
            notice(message.chat.id,current,lang)
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

    @bot.callback_query_handler(func=lambda c: c.data and c.data.startswith(('p:','lang:')))
    def callback(call):
        if not call.message or call.message.chat.type != 'private' or call.message.chat.id != call.from_user.id:
            return
        bot.answer_callback_query(call.id)
        current = policy()
        parts = call.data.split(':')
        if len(parts)==2 and parts[0]=='lang' and parts[1] in UI:
            lang=parts[1];selected_languages[call.from_user.id]=lang
            if current is not None:state['store'].set_locale(call.from_user.id,lang)
            if current is not None and state['store'].allowed(call.from_user.id):
                saved=state['store'].intake(call.from_user.id)
                if saved:
                    kind,answers=saved
                    bot.send_message(call.message.chat.id,TEXT[lang]['progress']+' '+str(len(answers)+1)+'/'+str(len(FLOWS[kind]))+': '+TEXT[lang][kind+'_q'][len(answers)])
                else:menu(call.message.chat.id,lang)
            else:notice(call.message.chat.id,current,lang)
            return
        if current is None or len(parts) != 4 or parts[1] != revision(current) or parts[2] not in UI or parts[3] not in ('yes', 'no'):
            notice(call.message.chat.id, current)
            return
        lang, action = parts[2], parts[3]
        store = state['store']
        shown=store.db.execute("SELECT 1 FROM privacy_events WHERE user_id=? AND revision=? AND locale=? AND action='presented'",(call.from_user.id,revision(current),lang)).fetchone()
        if not shown:
            notice(call.message.chat.id,current,lang);return
        store.record(call.from_user.id, 'acknowledged' if action == 'yes' else 'declined', lang)
        if action == 'yes' and store.allowed(call.from_user.id):
            menu(call.message.chat.id,lang)
        else:
            bot.send_message(call.message.chat.id, UI[lang]['stopped'], reply_markup=telebot.types.ReplyKeyboardRemove())

    return bot


def run():
    if os.environ.get('EWU_START_ALLOWED') != '1' or os.environ.get('EWU_MAINTENANCE', '1') != '0':
        raise RuntimeError('EWU polling is locked')
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

