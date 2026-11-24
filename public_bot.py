"""Public EWU catalogue, private admin tools and fail-closed optional simple intake."""
import io
import json
import os
import sqlite3
import time
from pathlib import Path
import telebot
from maxhr import Catalog, generate_ad, safe_url
from maxhr_crm import MaxHRCrm, SimpleForm, STATUSES, DOCUMENTS
from public_text import WORDS, LANGUAGES, TYPES
from privacy.onboarding import Store, load_policy, render, revision, UI
from existing_rights import handle_right

MENU_KEYS=('find','hot','high','housing','couples','apps','employer','contact')


def intake_enabled(env):
    if env.get('MAXHR_INTAKE_ENABLED')!='1' or env.get('MAXHR_PRIVACY_REVIEWED')!='1':return False
    try:load_policy(env.get('PRIVACY_CONFIG_FILE',''),env.get('PRIVACY_CONFIG_JSON'));return True
    except (OSError,ValueError,TypeError,KeyError):return False

class PublicUI:
    def __init__(self,bot,catalog_path,privacy_path,env,admins):
        self.bot=bot;self.catalog=Catalog(catalog_path);self.privacy_path=privacy_path;self.env=env
        self.admins={str(x) for x in admins};self.sessions={}
    def session(self,user,device='uk'):
        now=time.monotonic()
        self.sessions={u:s for u,s in self.sessions.items() if now-s['at']<1800}
        if len(self.sessions)>=10000:self.sessions.pop(next(iter(self.sessions)))
        if user not in self.sessions:self.sessions[user]=dict(lang=device if device in WORDS else 'uk',filters={},at=now)
        self.sessions[user]['at']=now
        return self.sessions[user]
    def send(self,user,text,**kwargs):
        # Plain text throughout; user/source content cannot create HTML/Markdown mentions.
        for offset in range(0,max(1,len(text)),3500):
            self.bot.send_message(user,text[offset:offset+3500],disable_web_page_preview=True,**kwargs)
    def keyboard(self,rows):
        kb=telebot.types.InlineKeyboardMarkup(row_width=2)
        for row in rows:kb.row(*(telebot.types.InlineKeyboardButton(label,**({'url':value} if value.startswith('https://') else {'callback_data':value})) for label,value in row))
        return kb
    def menu(self,user):
        w=WORDS[self.session(user)['lang']]
        kb=telebot.types.ReplyKeyboardMarkup(resize_keyboard=True,row_width=1)
        for key in MENU_KEYS:kb.add(telebot.types.KeyboardButton(w[key]))
        self.send(user,w['menu']+'\n'+w['privacy_note']+'\n/language · /privacy · /cancel',reply_markup=kb)
    def languages(self,user):
        self.send(user,'🌐 EWU',reply_markup=self.keyboard([[(label,'lang:'+lang)] for lang,label in LANGUAGES.items()]))
    def listing(self,user):
        s=self.session(user);w=WORDS[s['lang']];snapshot=self.catalog.read();jobs=self.catalog.select(**s['filters'])
        rows=[[(j['name']+' · '+j['city'],'job:'+j['id'])] for j in jobs]
        rows.append([(w['filters'],'filters'),(w['all'],'all')]);rows.append([(w['back'],'menu')])
        self.send(user,f"🇪🇺 EWU × MaxHR · {len(jobs)}\n{w['updated']}: {snapshot['synced_at'] or w['missing']}\n{w['privacy_note']}",reply_markup=self.keyboard(rows))
    def card(self,user,jid):
        job=self.catalog.job(jid);s=self.session(user);w=WORDS[s['lang']]
        if not job:self.send(user,w['missing']);self.listing(user);return
        lines=[f"🇪🇺 EWU × MaxHR\n{job['name']} — {job['city']}"]
        for label,key in [('description','description'),('salary','salary'),('hours','hours'),('schedule','schedule'),('accommodation','housing'),('transport','transport'),('bonuses','bonuses'),('requirements','requirements'),('places','places')]:
            value=job.get(key)
            lines.append(w[label]+': '+(str(value) if value not in (None,'') else w['missing']))
        for label,key in [('source','description_salary'),('accommodation','housing_details'),('transport','transport_details')]:
            if job.get(key):lines.append(w[label]+': '+job[key])
        if job['issues']:lines.append(w['issues']+': '+w['missing']+'\n'+'\n'.join(job['issues']))
        lines.append(w['updated']+': '+self.catalog.read()['synced_at'])
        lines.append(w['privacy_note'])
        rows=[[(w['apply'],'apply:'+jid)]]
        for key,label in [('description_url','source'),('housing_url','accommodation'),('transport_url','transport')]:
            if safe_url(job.get(key)):rows.append([(w[label],job[key])])
        if self.env.get('MAXHR_CONTACT_VERIFIED')=='1' and safe_url(self.env.get('MAXHR_CONTACT_URL')):
            rows.append([('MaxHR ↗',self.env['MAXHR_CONTACT_URL'])])
        rows.append([(w['back'],'list')])
        self.send(user,'\n\n'.join(lines),reply_markup=self.keyboard(rows))
    def filter_menu(self,user):
        w=WORDS[self.session(user)['lang']]
        self.send(user,w['filters'],reply_markup=self.keyboard([[(w['city'],'filter:city'),(w['pay'],'filter:pay')],[(w['housing'],'filter:housing'),(w['type'],'filter:type')],[(w['all'],'all'),(w['back'],'list')]]))
    def contact(self,user,employer=False):
        w=WORDS[self.session(user)['lang']];url=safe_url(self.env.get('EWU_COORDINATOR_URL'))
        rows=[]
        if url:rows.append([('EWU ↗',url)])
        if self.env.get('MAXHR_CONTACT_VERIFIED')=='1' and safe_url(self.env.get('MAXHR_CONTACT_URL')):rows.append([('MaxHR ↗',self.env['MAXHR_CONTACT_URL'])])
        self.send(user,(w['employer_note'] if employer else w['contact'])+'\n'+w['disabled'],reply_markup=self.keyboard(rows+[[ (w['back'],'menu') ]]))
    def reviewed_store(self):
        p=load_policy(self.env.get('PRIVACY_CONFIG_FILE',''),self.env.get('PRIVACY_CONFIG_JSON'))
        return Store(self.privacy_path,p)
    def apply(self,user,jid):
        s=self.session(user);w=WORDS[s['lang']]
        if not intake_enabled(self.env):self.send(user,w['disabled']);self.contact(user);return
        job=self.catalog.job(jid)
        if not job:self.send(user,w['missing']);return
        store=self.reviewed_store()
        try:
            if not store.allowed(user):
                s['pending_job']=jid;p=store.policy
                self.send(user,render(p,s['lang']),reply_markup=self.keyboard([[(w['yes'],f"consent:{revision(p)}"),(w['no'],'cancel')]]));return
        finally:store.close()
        s['form']=SimpleForm(job);self.question(user)
    def question(self,user):
        s=self.session(user);w=WORDS[s['lang']];f=s['form'].field
        if f in DOCUMENTS:
            self.send(user,f+'?\n'+w['docs_note'],reply_markup=self.keyboard([[(w[k],'answer:'+k) for k in ('yes','no','unsure')]]))
        else:self.send(user,w[f]+'?')
    def answer(self,user,value):
        s=self.session(user);w=WORDS[s['lang']]
        if not intake_enabled(self.env):s.pop('form',None);self.send(user,w['disabled']);return
        try:
            store=self.reviewed_store()
            try:
                if not store.allowed(user):s.pop('form',None);self.send(user,w['consent']);return
                form=s['form']
                if form.answer(value):
                    # Reject a vacancy that closed while the form was being completed.
                    if not self.catalog.job(form.data['vacancy_id']):s.pop('form',None);self.send(user,w['missing']);return
                    MaxHRCrm(store,self.admins).submit(user,form,s['lang'],enabled=True)
                    s.pop('form',None);self.send(user,w['saved']);self.menu(user)
                else:self.question(user)
            finally:store.close()
        except (ValueError,PermissionError):self.send(user,w['missing'])
    def admin(self,user,raw):
        s=self.session(user);w=WORDS[s['lang']]
        if str(user) not in self.admins:self.send(user,w['admin_denied']);return
        parts=raw.split();cmd=parts[0]
        try:
            if cmd=='/admin':
                self.send(user,'EWU × MaxHR admin\n/admin_stats /admin_export /admin_commissions\n/admin_ad JOB_ID Telegram|Facebook|Instagram|Threads|WhatsApp\n/admin_sync\n/admin_status APPLICATION_ID STATUS REVISION\n/admin_history APPLICATION_ID\n/admin_finance APPLICATION_ID COMMISSION_INDEX\n/admin_payment APPLICATION_ID CONFIRMED_GROSZ PAID_GROSZ REVISION\n'+', '.join(STATUSES));return
            if cmd=='/admin_sync':
                # Separate connection for sync; only public data, no candidate data.
                ok=self.catalog.sync();self.send(user,'sync_ok' if ok else 'sync_failed_last_good_retained');return
            if cmd=='/admin_commissions':
                terms=self.catalog.read()['commissions']
                self.send(user,'\n\n'.join(str(i)+' '+json.dumps(t,ensure_ascii=False) for i,t in enumerate(terms)));return
            if cmd=='/admin_ad':
                job=self.catalog.job(parts[1]);self.send(user,generate_ad(job,parts[2]));return
            if cmd in ('/admin_stats','/admin_export'):
                counts={}
                if Path(self.privacy_path).is_file():
                    db=sqlite3.connect(f'file:{self.privacy_path}?mode=ro',uri=True)
                    try:
                        if db.execute("SELECT 1 FROM sqlite_master WHERE name='candidate_journey'").fetchone():counts=dict(db.execute('SELECT status,count(*) FROM candidate_journey GROUP BY status'))
                    finally:db.close()
                if cmd=='/admin_export':
                    body='status,count\n'+'\n'.join(f'{k},{v}' for k,v in counts.items())
                    stream=io.BytesIO(body.encode());stream.name='ewu-statistics.csv';self.bot.send_document(user,stream)
                else:self.send(user,json.dumps(dict(statuses=counts,vacancies=len(self.catalog.read()['vacancies']),last_sync=self.catalog.read()['synced_at'],intake_enabled=intake_enabled(self.env)),ensure_ascii=False))
                return
            store=self.reviewed_store()
            try:
                crm=MaxHRCrm(store,self.admins)
                if cmd=='/admin_status':result=crm.journey.transition(user,parts[1],parts[2],int(parts[3]))
                elif cmd=='/admin_history':
                    crm.journey._row(parts[1]);result=list(store.db.execute('SELECT status,revision,actor,at FROM journey_events WHERE application_id=? ORDER BY id',(parts[1],)))
                elif cmd=='/admin_finance':result=crm.terms(user,parts[1],self.catalog.read()['commissions'][int(parts[2])])
                elif cmd=='/admin_payment':result=crm.payment(user,parts[1],int(parts[2]),int(parts[3]),int(parts[4]))
                else:raise ValueError('Unknown admin command')
                self.send(user,json.dumps(result,ensure_ascii=False))
            finally:store.close()
        except (ValueError,PermissionError,IndexError,TypeError,OSError,KeyError):self.send(user,'Command refused: check arguments, permissions, current revision and reviewed privacy configuration.')
    def message(self,m):
        if m.chat.type!='private' or m.from_user.is_bot or m.chat.id!=m.from_user.id:return
        user=m.from_user.id;s=self.session(user,(m.from_user.language_code or 'uk').split('-')[0]);w=WORDS[s['lang']]
        raw=(m.text or '').strip();cmd=raw.split(maxsplit=1)[0].split('@')[0] if raw else ''
        if cmd.startswith('/admin'):self.admin(user,raw);return
        if cmd in ('/withdraw','/delete_data','/my_data','/status','/arrival'):
            s.pop('form',None)
            result=handle_right(self.privacy_path,user,cmd)
            if cmd in ('/withdraw','/delete_data'):self.send(user,UI[s['lang']]['stopped'] if cmd=='/withdraw' else UI[s['lang']]['deleted']);return
            if cmd=='/status':self.send(user,json.dumps(result.get('statuses',[]),ensure_ascii=False) if result.get('statuses') else w['no_apps']);return
            if cmd=='/arrival':
                # Keep the original arrival-plan functionality when its reviewed policy exists.
                try:
                    from recruitment import Journey
                    store=self.reviewed_store()
                    try:
                        j=Journey(store,self.admins);plans=[j.arrival(user,r['id']) for r in j.own(user)]
                        self.send(user,json.dumps([p for p in plans if p],ensure_ascii=False))
                    finally:store.close()
                except (ValueError,PermissionError,OSError,KeyError):self.send(user,w['missing'])
                return
            self.send(user,json.dumps(result,ensure_ascii=False,indent=2));return
        if cmd in ('/cancel','/reset'):
            s.pop('form',None);s.pop('pending_job',None);self.menu(user);return
        if cmd=='/language':self.languages(user);return
        if cmd in ('/privacy','/about'):
            self.send(user,w['privacy_note']+'\n'+w['disabled']);return
        if cmd=='/start':
            s.pop('form',None);self.menu(user)
            payload=raw.split(maxsplit=1)
            if len(payload)>1 and payload[1].startswith('job_'):self.card(user,payload[1][4:])
            else:self.languages(user)
            return
        if cmd in ('/jobs','/vacancies'):
            s['filters']={};self.listing(user);return
        if cmd=='/filters':self.filter_menu(user);return
        aliases={v[k]:k for v in WORDS.values() for k in MENU_KEYS}
        action=aliases.get(raw)
        if action in ('find','hot','high','housing','couples'):
            s.pop('form',None);s['filters']={'min_pay':28} if action=='high' else {'housing':True} if action=='housing' else {'couples':True} if action=='couples' else {}
            if action=='find':self.filter_menu(user)
            else:self.listing(user)
            return
        if action=='apps':
            result=handle_right(self.privacy_path,user,'/status');self.send(user,json.dumps(result.get('statuses'),ensure_ascii=False) if result.get('statuses') else w['no_apps']);return
        if action in ('contact','employer'):self.contact(user,action=='employer');return
        if 'form' in s and raw:self.answer(user,raw);return
        self.send(user,w['unknown']+'\n'+w['disabled'])
    def callback(self,c):
        if not c.message or c.message.chat.type!='private' or c.message.chat.id!=c.from_user.id:return
        self.bot.answer_callback_query(c.id)
        user=c.from_user.id;s=self.session(user);w=WORDS[s['lang']];data=c.data or ''
        if data.startswith('lang:'):
            lang=data[5:]
            if lang in WORDS:s['lang']=lang;self.menu(user)
        elif data=='menu':self.menu(user)
        elif data=='list':self.listing(user)
        elif data=='filters':self.filter_menu(user)
        elif data=='all':s['filters']={};self.listing(user)
        elif data.startswith('job:'):self.card(user,data[4:])
        elif data.startswith('apply:'):self.apply(user,data[6:])
        elif data=='cancel':s.pop('form',None);s.pop('pending_job',None);self.menu(user)
        elif data.startswith('answer:') and 'form' in s:self.answer(user,{'yes':'yes','no':'no','unsure':'unknown'}.get(data[7:],''))
        elif data.startswith('consent:') and intake_enabled(self.env):
            store=self.reviewed_store()
            try:
                if data[8:]==revision(store.policy):store.record(user,'acknowledged',s['lang'])
            finally:store.close()
            if s.get('pending_job'):self.apply(user,s['pending_job'])
        elif data.startswith('filter:'):
            field=data[7:];rows=[]
            if field=='city':
                # Use stable city hashes in callbacks to stay under Telegram's 64-byte limit.
                import hashlib
                rows=[[(city,'city:'+hashlib.sha256(city.encode()).hexdigest()[:12])] for city in sorted({j['city'] for j in self.catalog.read()['vacancies']})]
            elif field=='pay':rows=[[(str(n)+' PLN netto/h','pay:'+str(n))] for n in (24,26,28,30)]
            elif field=='type':rows=[[(label,'type:'+kind)] for kind,label in TYPES[s['lang']].items()]
            elif field=='housing':s['filters']['housing']=not s['filters'].get('housing',False);self.listing(user);return
            rows.append([(w['back'],'filters')]);self.send(user,w['filters'],reply_markup=self.keyboard(rows))
        elif data.startswith('city:'):
            import hashlib
            city=next((j['city'] for j in self.catalog.read()['vacancies'] if hashlib.sha256(j['city'].encode()).hexdigest()[:12]==data[5:]),None)
            if city:s['filters']['city']=city
            self.listing(user)
        elif data.startswith('pay:'):
            if data[4:] in ('24','26','28','30'):s['filters']['min_pay']=int(data[4:])
            self.listing(user)
        elif data.startswith('type:'):
            if data[5:] in ('warehouse','production','unspecified'):s['filters']['kind']=data[5:]
            self.listing(user)
        else:self.send(user,w['unknown'])


def create_public_bot(token,catalog_path,privacy_path,env=None,admins=(),bot_client=None):
    bot=bot_client or telebot.TeleBot(token,threaded=False)
    ui=PublicUI(bot,catalog_path,privacy_path,dict(os.environ) if env is None else env,admins)
    bot.message_handler(func=lambda m:True,content_types=['text','photo','document','contact','voice','video','audio','location','sticker'])(ui.message)
    bot.callback_query_handler(func=lambda c:True)(ui.callback)
    bot.ewu_ui=ui
    return bot


def runtime_smoke(catalog_path):
    """Exercise the deployed image with real public jobs and synthetic chat objects.
    Sends no Telegram messages and never opens the production candidate database.
    """
    from tempfile import TemporaryDirectory
    from types import SimpleNamespace as NS
    class Probe:
        def __init__(self):self.messages=0
        def send_message(self,user,text,**options):
            if not text or len(text)>3500:raise ValueError('Invalid Telegram message length')
            kb=options.get('reply_markup')
            if kb:
                for row in json.loads(kb.to_json()).get('inline_keyboard',[]):
                    for b in row:
                        if len(b.get('callback_data','').encode())>64:raise ValueError('Invalid callback length')
            self.messages+=1
        def answer_callback_query(self,*args):pass
    with TemporaryDirectory() as directory:
        probe=Probe();ui=PublicUI(probe,catalog_path,str(Path(directory)/'never-created.sqlite3'),{},[99])
        try:
            jobs=ui.catalog.read()['vacancies']
            for lang in WORDS:
                ui.session(42)['lang']=lang
                for key in MENU_KEYS:
                    ui.message(NS(text=WORDS[lang][key],chat=NS(id=42,type='private'),from_user=NS(id=42,is_bot=False,language_code=lang)))
                for job in jobs:ui.card(42,job['id'])
            if (Path(directory)/'never-created.sqlite3').exists():raise RuntimeError('Public browse wrote candidate data')
            check=Catalog(catalog_path)
            try:
                if check.read()!=ui.catalog.read():raise RuntimeError('Persisted catalogue mismatch')
                if check.db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise RuntimeError('Catalogue integrity failed')
            finally:check.close()
            return dict(languages=len(WORDS),vacancies=len(jobs),messages=probe.messages,persistence='ok',intake='disabled')
        finally:ui.catalog.close()
