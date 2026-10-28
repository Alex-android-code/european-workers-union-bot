"""Adapter for the existing EWU bot, activated only by explicit reviewed configuration."""
import json
import hashlib
from .domain import Actor, Denied
from .ai import RecruitmentAI
from privacy.onboarding import UI, render, revision

LANGUAGES={'uk':'Українська','pl':'Polski','ru':'Русский','en':'English','uz':'O‘zbekcha'}
TEXT={
 'uk':{'language':'Оберіть мову','profile':'Анкета: /profile','name':'Як вас звати?','city':'Ваше місто?','profession':'Яку роботу шукаєте?','phone':'Телефон із кодом країни?','saved':'Картку збережено. Candidate ID: ','vacancies':'Перевірені вакансії: /vacancies','rights':'Мої дані: /my_data /rectify /copy_data /delete_data /withdraw /object /restrict','request':'Запит зареєстровано для оператора: ','empty':'Немає підтверджених вакансій. Передано оператору.','stale':'Потрібне актуальне ознайомлення. /start','error':'Дію не виконано. Перевірте права, стан заявки та /privacy.'},
 'pl':{'language':'Wybierz język','profile':'Formularz: /profile','name':'Jak się nazywasz?','city':'Twoje miasto?','profession':'Jakiej pracy szukasz?','phone':'Telefon z kodem kraju?','saved':'Karta zapisana. Candidate ID: ','vacancies':'Potwierdzone oferty: /vacancies','rights':'Moje dane: /my_data /rectify /copy_data /delete_data /withdraw /object /restrict','request':'Wniosek zarejestrowany dla operatora: ','empty':'Brak potwierdzonych ofert. Przekazano operatorowi.','stale':'Wymagana aktualna informacja. /start','error':'Nie wykonano. Sprawdź uprawnienia, status i /privacy.'},
 'ru':{'language':'Выберите язык','profile':'Анкета: /profile','name':'Как вас зовут?','city':'Ваш город?','profession':'Какую работу ищете?','phone':'Телефон с кодом страны?','saved':'Карточка сохранена. Candidate ID: ','vacancies':'Подтверждённые вакансии: /vacancies','rights':'Мои данные: /my_data /rectify /copy_data /delete_data /withdraw /object /restrict','request':'Запрос зарегистрирован для оператора: ','empty':'Нет подтверждённых вакансий. Передано оператору.','stale':'Нужно актуальное ознакомление. /start','error':'Действие не выполнено. Проверьте права, статус и /privacy.'},
 'en':{'language':'Choose a language','profile':'Profile: /profile','name':'Your name?','city':'Your city?','profession':'What work are you looking for?','phone':'Phone with country code?','saved':'Profile saved. Candidate ID: ','vacancies':'Confirmed vacancies: /vacancies','rights':'My data: /my_data /rectify /copy_data /delete_data /withdraw /object /restrict','request':'Request registered for operator review: ','empty':'No confirmed vacancies. Handed to an operator.','stale':'Current notice required. /start','error':'Action not completed. Check permissions, application status and /privacy.'},
 'uz':{'language':'Tilni tanlang','profile':'Anketa: /profile','name':'Ismingiz?','city':'Shahringiz?','profession':'Qanday ish qidiryapsiz?','phone':'Mamlakat kodi bilan telefon?','saved':'Karta saqlandi. Candidate ID: ','vacancies':'Tasdiqlangan ishlar: /vacancies','rights':'Mening ma’lumotlarim: /my_data /rectify /copy_data /delete_data /withdraw /object /restrict','request':'Operator uchun so‘rov ro‘yxatga olindi: ','empty':'Tasdiqlangan ish yo‘q. Operatorga yuborildi.','stale':'Amaldagi ma’lumot bilan tanishing. /start','error':'Amal bajarilmadi. Ruxsat, holat va /privacy ni tekshiring.'},
}


class TelegramRecruitment:
    def __init__(self,service,ai=None,policy_loader=None):
        self.service=service
        self.policy_loader=policy_loader
        self.ai=ai or RecruitmentAI(service)

    def refresh_policy(self):
        if self.policy_loader is not None:
            try:
                self.service.policy=self.policy_loader()
            except (OSError,ValueError,KeyError,TypeError):
                self.service.policy={**self.service.policy,'legal_review_approved':False}

    def session(self,user_id):
        row=self.service.db.one('SELECT data FROM ewu2_sessions WHERE user_id=?',(str(user_id),))
        return json.loads(row['data']) if row else {}

    def save_session(self,user_id,data):
        self.service.db.execute('INSERT INTO ewu2_sessions VALUES(?,?) ON CONFLICT(user_id) DO UPDATE SET data=excluded.data',(str(user_id),json.dumps(data)))

    def message(self,message,bot):
        if message.chat.type!='private' or message.from_user.is_bot:return
        self.refresh_policy()
        actor=Actor(str(message.from_user.id))
        identifier=f'm:{message.chat.id}:{message.message_id}'
        try:
            responses=self.service.process_update(identifier,lambda:self.handle(actor,message.text or '',message.from_user.language_code or 'uk'))
        except (Denied,ValueError,KeyError,TypeError):
            lang=self.session(actor.id).get('lang','uk')
            responses=[{'text':TEXT[lang]['error']}]
        self.send(bot,message.chat.id,responses)

    def callback(self,call,bot):
        if not call.message or call.message.chat.type!='private' or call.message.chat.id!=call.from_user.id:return
        self.refresh_policy()
        actor=Actor(str(call.from_user.id))
        try:
            responses=self.service.process_update('c:'+call.id,lambda:self.handle_callback(actor,call.data))
        except (Denied,ValueError,KeyError,TypeError):
            lang=self.session(actor.id).get('lang','uk')
            responses=[{'text':TEXT[lang]['error']}]
        bot.answer_callback_query(call.id)
        self.send(bot,call.message.chat.id,responses)

    @staticmethod
    def send(bot,chat_id,responses):
        for item in responses or []:
            bot.send_message(chat_id,item['text'],reply_markup=item.get('reply_markup'),disable_web_page_preview=True)

    def language_screen(self):
        return [{'text':'Оберіть мову / Wybierz język / Выберите язык / Choose a language / Tilni tanlang',
                 'reply_markup':{'inline_keyboard':[[{'text':label,'callback_data':'v2:lang:'+lang}] for lang,label in LANGUAGES.items()]}}]

    def notice(self,lang):
        self.service.legal()
        return [{'text':render(self.service.policy,lang),'reply_markup':{'inline_keyboard':[[
            {'text':UI[lang]['continue'],'callback_data':f'v2:ack:{lang}:{revision(self.service.policy)}'},
            {'text':UI[lang]['decline'],'callback_data':f'v2:no:{lang}:{revision(self.service.policy)}'}]]}}]

    def handle_callback(self,actor,data):
        parts=data.split(':')
        if len(parts)==3 and parts[:2]==['v2','lang'] and parts[2] in LANGUAGES:
            self.save_session(actor.id,{'lang':parts[2]})
            return self.notice(parts[2])
        if len(parts)==6 and parts[:2]==['v2','opt']:
            _,_,slug,choice,lang,key=parts
            if lang not in LANGUAGES or self.session(actor.id).get('lang')!=lang or choice not in ('yes','no','withdraw'):
                raise Denied('Invalid consent action')
            purposes=self.service.policy.get('optional_consents',{})
            purpose=next((p for p in purposes if hashlib.sha256(p.encode()).hexdigest()[:8]==slug),None)
            if purpose is None:raise Denied('Unknown purpose')
            if key!=revision(self.service.policy):return self.notice(lang)
            action={'yes':'consent_granted','no':'consent_refused','withdraw':'consent_withdrawn'}[choice]
            self.service.privacy(actor,lang,action,key,purpose)
            return [{'text':TEXT[lang]['profile']+'\n'+TEXT[lang]['rights']}]
        if len(parts)==4 and parts[0]=='v2' and parts[1] in ('ack','no'):
            lang=parts[2]
            if self.session(actor.id).get('lang')!=lang:
                return self.language_screen()
            if parts[3]!=revision(self.service.policy):return self.notice(lang)
            allowed=self.service.privacy(actor,lang,'acknowledged' if parts[1]=='ack' else 'declined',parts[3])
            self.save_session(actor.id,{'lang':lang})
            return [{'text':TEXT[lang]['profile']+'\n'+TEXT[lang]['rights'] if allowed else UI[lang]['stopped']}]
        raise Denied('Invalid callback')

    def handle(self,actor,text,language):
        session=self.session(actor.id)
        lang=session.get('lang',language if language in LANGUAGES else 'uk')
        ui=TEXT[lang]
        command=text.strip().split(maxsplit=1)[0].split('@')[0] if text.strip() else ''
        args=text.strip().split(maxsplit=1)[1] if len(text.strip().split(maxsplit=1))>1 else ''
        if command in ('/start','/reset'):
            self.save_session(actor.id,{})
            return self.language_screen()
        if command=='/privacy':return self.notice(lang)
        rights={'/my_data':'view','/rectify':'rectify','/copy_data':'copy','/delete_data':'delete','/withdraw':'withdraw','/object':'object','/restrict':'restrict'}
        if command in rights:
            result=self.service.rights(actor,rights[command])
            if rights[command]=='view':
                return [{'text':json.dumps(result,ensure_ascii=False)[:3500]}]
            return [{'text':ui['request']+result+'\n'+self.service.policy['notices'][lang]['contact']}]
        if command=='/consent':
            screens=[]
            for purpose,definition in self.service.policy.get('optional_consents',{}).items():
                if not definition.get('legal_review_approved') or not all(definition.get('texts',{}).get(l) for l in LANGUAGES):continue
                slug=hashlib.sha256(purpose.encode()).hexdigest()[:8]
                screens.append({'text':definition['texts'][lang],'reply_markup':{'inline_keyboard':[[
                    {'text':UI[lang]['grant'],'callback_data':f'v2:opt:{slug}:yes:{lang}:{revision(self.service.policy)}'},
                    {'text':UI[lang]['refuse'],'callback_data':f'v2:opt:{slug}:no:{lang}:{revision(self.service.policy)}'}],
                    [{'text':UI[lang]['withdraw_consent'],'callback_data':f'v2:opt:{slug}:withdraw:{lang}:{revision(self.service.policy)}'}]]}})
            return screens or [{'text':'Optional consent-based features are disabled; core service remains available.'}]
        if command=='/stop_reminders':
            self.service.notification_preference(actor,False)
            return [{'text':'Reminders disabled; core service remains available.'}]
        if not self.service.allowed(actor.id):return self.notice(lang)
        if command=='/profile':
            self.service.begin_profile(actor,lang)
            self.save_session(actor.id,{'lang':lang,'profile':{},'step':0})
            return [{'text':ui['name']}]
        if command=='/vacancies':
            result=self.ai.choose(actor,'telegram:'+self.service.uid())
            if not result['vacancies']:
                self.service.enqueue('operator',self.service.candidate(actor.id)['id'],'no-matches:'+str(actor.id)+':'+self.service.now())
                return [{'text':ui['empty']}]
            return [{'text':json.dumps({'Vacancy ID':v['id'],**v['data']},ensure_ascii=False)+'\n/apply '+v['id']} for v in result['vacancies'][:5]]
        if command=='/alternatives':
            matches=self.service.alternatives(actor,args)
            return [{'text':json.dumps({'Vacancy ID':v['id'],**v['data']},ensure_ascii=False)+'\n/apply '+v['id']} for v in matches[:5]] or [{'text':ui['empty']}]
        if command=='/apply':
            return [{'text':'Application ID: '+self.service.apply(actor,args)}]
        if command=='/arrived':
            row=self.service.transition(actor,args,'ARRIVED')
            return [{'text':row['status']+' — awaiting authorized confirmation'}]
        if command=='/on_the_way':
            return [{'text':self.service.transition(actor,args,'ON_THE_WAY')['status']}]
        if command=='/resume':
            return [{'text':self.service.transition(actor,args,'INTERESTED')['status']}]
        if command=='/ai_off':
            self.service.ai_switch(actor,False)
            return [{'text':'AI disabled; core workflow remains available.'}]
        if command=='/dashboard':
            return [{'text':json.dumps(self.service.dashboard(actor),ensure_ascii=False)[:3500]}]
        if command=='/quality':
            app,*answers=args.split()
            if len(answers)!=4 or any(v not in ('yes','no') for v in answers):raise Denied('Four yes/no answers required')
            report=dict(zip(('conditions_match','rate_match','housing_match','needs_help'),(v=='yes' for v in answers)))
            return [{'text':'Operator review: '+self.service.quality(actor,app,report)}]
        if command=='/instructions':
            app,raw=args.split(maxsplit=1)
            self.service.instructions(actor,app,json.loads(raw))
            return [{'text':'Verified instructions recorded.'}]
        if command=='/partner':
            data=json.loads(args)
            if set(data)!={'name','contact'}:raise Denied('Partner fields required')
            return [{'text':'Partner ID: '+self.service.partner(actor,**data)}]
        if command=='/vacancy':
            data=json.loads(args)
            if set(data)!={'partner_id','external_id','data','expires_at'}:raise Denied('Vacancy fields required')
            return [{'text':'Vacancy ID: '+self.service.vacancy(actor,**data)}]
        if command=='/commission':
            data=json.loads(args)
            if set(data)!={'application_id','model','rate_minor','units','currency','contract_ref','period'}:raise Denied('Commission fields required')
            return [{'text':'Commission ID: '+self.service.commission(actor,**data)}]
        if command=='/confirm':
            application_id,target=args.split(maxsplit=1)
            return [{'text':self.service.transition(actor,application_id,target)['status']}]
        if 'step' in session and text and not command.startswith('/'):
            fields=['name','city','profession','phone']
            step=session['step']
            if len(text)>500:raise Denied('Answer too long')
            session['profile'][fields[step]]=text
            if step==3:
                profile=session['profile'];phone=profile.pop('phone')
                candidate_id=self.service.register(actor,lang,profile,phone)
                self.save_session(actor.id,{'lang':lang})
                return [{'text':ui['saved']+candidate_id+'\n'+ui['vacancies']}]
            session['step']+=1
            self.save_session(actor.id,session)
            return [{'text':ui[fields[step+1]]}]
        return [{'text':ui['profile']+'\n'+ui['vacancies']+'\n'+ui['rights']}]
