"""Short button-based journey. No outbound chat messages unless the candidate acts."""
import time
import re
import telebot
from .core import Refused,Forbidden,STATUS_LABELS,SAFE_REQUIREMENTS,source_tag

SKILLS={'polish_basic':'Базова польська','power_tools':'Робота з електроінструментами','scanner':'Робота зі сканером','physical_work':'Готовність до фізичної роботи','warehouse_certificate':'Сертифікат на складський візок'}
class CandidateFlow:
    def __init__(self,bot,radar):self.bot=bot;self.radar=radar;self.sessions={}
    def state(self,user):
        current=time.monotonic();self.sessions={u:s for u,s in self.sessions.items() if current-s['at']<1200}
        if user not in self.sessions:
            if len(self.sessions)>10000:self.sessions.pop(next(iter(self.sessions)))
            self.sessions[user]={'source':'direct','answers':{'city':'any','schedule':'any','start':'any','skills':{},'min_pay':None},'selected':[],'at':current,'step':''}
        self.sessions[user]['at']=current;return self.sessions[user]
    def keyboard(self,rows):
        kb=telebot.types.InlineKeyboardMarkup()
        for row in rows:kb.row(*[telebot.types.InlineKeyboardButton(label,callback_data=data) for label,data in row])
        return kb
    def send(self,user,text,rows=None,markup=None):
        for offset in range(0,max(1,len(text)),3500):self.bot.send_message(user,text[offset:offset+3500],reply_markup=markup if markup is not None else self.keyboard(rows) if rows else None,disable_web_page_preview=True)
    def start(self,user,payload=''):
        old=self.state(user);source=source_tag(payload[4:] if payload.startswith('src_') else '')
        self.sessions.pop(user,None);s=self.state(user);s['source']=source
        self.radar.record_visit(user,source)
        self.send(user,'Кандидатний радар EWU\nЗа кілька коротких кроків підберемо роботу. Відповіді підбору зберігаються лише на час розмови. Телефон запитаємо тільки після окремого ознайомлення й згоди.\nНе надсилайте документи, резюме або файли.',[[('Підібрати роботу','begin')],[('Усі активні вакансії','list')],[('Мої заявки','own')]])
    def question(self,user,step):
        s=self.state(user);s['step']=step
        if step=='city':
            cities=sorted({j['city'] for j in self.radar.jobs()});s['cities']=cities
            self.send(user,'1/5. У якому місті шукаєте роботу?',[[ (city,'city:'+str(i)) ] for i,city in enumerate(cities)]+[[('Будь-яке місто','city:any')]])
        elif step=='schedule':self.send(user,'2/5. Який графік підходить?',[[('Денний','schedule:day'),('Нічний','schedule:night')],[('Змінний','schedule:shifts'),('Будь-який','schedule:any')]])
        elif step=='start':self.send(user,'3/5. Коли можете почати?',[[('Протягом 2 днів','start:now'),('За тиждень','start:week')],[('Протягом місяця','start:month'),('Поки не знаю','start:any')]])
        elif step=='skills':
            required=sorted({r for j in self.radar.jobs() for r in j.get('requirements',[])})
            s['skill_queue']=required
            self.skill_question(user)
        elif step=='pay':self.send(user,'5/5. Побажання щодо ставки нетто за годину?',[[('Від 26 zł','pay:26'),('Від 28 zł','pay:28')],[('Від 30 zł','pay:30'),('Без обмеження','pay:any')]])
    def skill_question(self,user):
        s=self.state(user)
        if not s['skill_queue']:self.question(user,'pay');return
        key=s['skill_queue'][0]
        self.send(user,'4/5. '+SKILLS[key]+'?',[[('Так','skill:yes'),('Ні','skill:no'),('Не знаю','skill:unknown')]])
    def listing(self,user):
        s=self.state(user);jobs=self.radar.match(s['answers'])
        if not jobs:self.send(user,'Зараз немає підтверджених активних вакансій за цими критеріями. Можна змінити побажання або повернутися пізніше.',[[('Змінити побажання','begin')],[('Скинути фільтри','all')]]);return
        self.send(user,'Варіанти за вашими побажаннями:',[[(j['title']+' · '+j['city'],'job:'+j['id'])] for j in jobs]+[[('Подати вибрані заявки ('+str(len(s['selected']))+')','submit')],[('Змінити побажання','begin')]])
    def card(self,user,jid):
        s=self.state(user);job=next((j for j in self.radar.match(s['answers']) if j['id']==jid),None)
        if not job:self.send(user,'Вакансія вже недоступна за цими критеріями.');return
        lines=[job['title'],job['city'],job['description'],'Оплата: '+job['pay'].split(';',1)[-1].strip(),'Графік: '+re.sub(r'^(day|night|shifts|any):\s*','',job['schedule'])]
        for key,label in [('hours','Годин'),('housing','Житло'),('transport','Транспорт'),('bonuses','Премії'),('places','Місць'),('start_date','Початок')]:
            if key in job:lines.append(label+': '+str(job[key]))
        lines.append('Чому рекомендовано: '+ '; '.join(job['reasons']))
        self.send(user,'\n\n'.join(lines),[[('Додати до заявок','select:'+jid)],[('Попросити зв’язатися','callback:'+jid)],[('Інші вакансії','list')]])
    def prepare(self,user):
        s=self.state(user)
        if not s['selected']:self.send(user,'Спочатку оберіть хоча б одну вакансію.');return
        if not self.radar.settings.ready:self.send(user,'Подання контактів поки вимкнено: триває перевірка порядку обробки даних. Не надсилайте телефон або документи.');return
        s['step']='consent'
        self.send(user,self.radar.settings.notice(),[[('Ознайомився і погоджуюсь','consent:'+self.radar.settings.policy_revision[:20])],[('Не погоджуюсь','decline')]])
    def message(self,m):
        if m.chat.type!='private' or m.from_user.is_bot or m.chat.id!=m.from_user.id:return
        user=m.from_user.id;s=self.state(user);raw=(m.text or '').strip();cmd=raw.split(maxsplit=1)[0].split('@')[0] if raw else ''
        if cmd=='/start':self.start(user,raw.split(maxsplit=1)[1] if len(raw.split(maxsplit=1))>1 else '');return
        if cmd in ('/withdraw','/delete_data'):
            self.radar.withdraw(user,cmd=='/delete_data');self.sessions.pop(user,None)
            self.send(user,'Заявки відкликано. Нове опрацювання зупинено.' if cmd=='/withdraw' else 'Запит на видалення отримано, заявки відкликано. Рекрутер опрацює видалення за повідомленою процедурою.');return
        if cmd in ('/my_data','/applications'):
            self.send(user,'\n'.join(j['vacancy_id']+' — '+STATUS_LABELS[j['status']] for j in self.radar.own(user)) or 'Заявок немає.');return
        if cmd in ('/cancel','/reset'):
            source=s['source'];self.sessions.pop(user,None);self.start(user,'src_'+source);return
        if cmd=='/privacy':self.send(user,self.radar.settings.notice() if self.radar.settings.ready else 'Збір контактів вимкнений. /withdraw та /delete_data залишаються доступними.');return
        contact=getattr(m,'contact',None)
        if contact is not None:
            if s['step']!='phone' or getattr(contact,'user_id',None)!=user:self.send(user,'Приймається лише ваш власний контакт після згоди.');return
            try:
                result=self.radar.submit(user,s['selected'],contact.phone_number,s['answers'],s['source'])
                self.sessions.pop(user,None)
                count=sum(not a['duplicate'] for a in result)
                self.send(user,f'Отримано нових заявок: {count}. Повторні заявки не створено. Це не підтвердження працевлаштування. Рекрутер перегляне звернення.',markup=telebot.types.ReplyKeyboardRemove())
            except (Refused,Forbidden) as error:self.send(user,str(error),markup=telebot.types.ReplyKeyboardRemove())
            return
        self.send(user,'Оберіть дію кнопками. Текст і файли не зберігаються. /start — почати; /applications — заявки.')
    def callback(self,c):
        if not c.message or c.message.chat.type!='private' or c.message.chat.id!=c.from_user.id:return
        self.bot.answer_callback_query(c.id);user=c.from_user.id;s=self.state(user);data=c.data or ''
        if data=='begin':self.question(user,'city')
        elif data=='all':s['answers']={'city':'any','schedule':'any','start':'any','skills':{},'min_pay':None};self.listing(user)
        elif data=='list':self.listing(user)
        elif data=='own':self.send(user,'\n'.join(j['vacancy_id']+' — '+STATUS_LABELS[j['status']] for j in self.radar.own(user)) or 'Заявок немає.')
        elif data.startswith('city:') and s['step']=='city':
            choice=data[5:]
            if choice=='any':s['answers']['city']='any'
            elif choice.isdigit() and int(choice)<len(s.get('cities',[])):s['answers']['city']=s['cities'][int(choice)]
            else:return
            self.question(user,'schedule')
        elif data.startswith('schedule:') and s['step']=='schedule':
            value=data[9:]
            if value not in ('day','night','shifts','any'):return
            s['answers']['schedule']=value;self.question(user,'start')
        elif data.startswith('start:') and s['step']=='start':
            value=data[6:]
            if value not in ('now','week','month','any'):return
            s['answers']['start']=value;self.question(user,'skills')
        elif data.startswith('skill:') and s['step']=='skills' and s.get('skill_queue'):
            value=data[6:]
            if value not in ('yes','no','unknown'):return
            s['answers']['skills'][s['skill_queue'].pop(0)]=value;self.skill_question(user)
        elif data.startswith('pay:') and s['step']=='pay':
            value=data[4:]
            if value not in ('26','28','30','any'):return
            s['answers']['min_pay']=None if value=='any' else int(value);s['step']='list';self.listing(user)
        elif data.startswith('job:'):self.card(user,data[4:])
        elif data.startswith(('select:','callback:')):
            jid=data.split(':',1)[1]
            if jid not in {j['id'] for j in self.radar.match(s['answers'])}:self.send(user,'Вакансія вже недоступна.');return
            if jid not in s['selected']:s['selected'].append(jid)
            if data.startswith('callback:'):self.prepare(user)
            else:self.send(user,'Вакансію додано. Можна обрати ще або подати заявку.',[[('Інші вакансії','list')],[('Подати заявки','submit')]])
        elif data=='submit':self.prepare(user)
        elif data=='decline':s['step']='list';self.send(user,'Контакт не зберігався. Можна продовжити перегляд.',[[('До вакансій','list')]])
        elif data.startswith('consent:') and s['step']=='consent':
            if not self.radar.settings.ready or data[8:]!=self.radar.settings.policy_revision[:20]:self.send(user,'Умови оновлено. Потрібно ознайомитися ще раз.');return
            try:self.radar.consent(user)
            except Forbidden as error:self.send(user,str(error));return
            s['step']='phone'
            kb=telebot.types.ReplyKeyboardMarkup(resize_keyboard=True,one_time_keyboard=True);kb.add(telebot.types.KeyboardButton('Поділитися моїм номером',request_contact=True))
            self.send(user,'Надішліть власний номер кнопкою Telegram. Не надсилайте документи або чужі контакти.',markup=kb)

def create_bot(radar,bot_client=None):
    bot=bot_client or telebot.TeleBot(radar.settings.telegram_token,threaded=False)
    flow=CandidateFlow(bot,radar)
    bot.message_handler(func=lambda m:True,content_types=['text','contact','photo','document','voice','video','audio','location','sticker'])(flow.message)
    bot.callback_query_handler(func=lambda c:True)(flow.callback)
    bot.radar_flow=flow;return bot
