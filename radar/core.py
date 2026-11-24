"""Shared server database and explicit public/private boundaries for Candidate Radar."""
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

STATUSES=('NEW','CONTACT','INTERVIEW','HIRED','UNSUITABLE','WITHDRAWN')
STATUS_LABELS=dict(zip(STATUSES,('Нова','Зв’язатися','На співбесіді','Найнятий','Не підходить','Відкликана')))
PUBLIC_KEYS={'title','city','description','pay','schedule','hours','housing','transport','bonuses','places','requirements','start_date','job_type','schedule_type','pay_net_min'}
REQUIRED={'title','city','description','pay','schedule'}
SAFE_REQUIREMENTS={'polish_basic','power_tools','scanner','physical_work','warehouse_certificate'}
PREFERENCE_KEYS={'city','schedule','start','skills','min_pay'}

class Refused(ValueError):pass
class Forbidden(PermissionError):pass

def now():return datetime.now(timezone.utc).isoformat(timespec='seconds')
def uid():return str(uuid.uuid4())
def dump(value):return json.dumps(value,ensure_ascii=False,separators=(',',':'))
def digest(value):return hashlib.sha256(value.encode()).hexdigest()

def source_tag(value):
    return value if isinstance(value,str) and re.fullmatch(r'[a-zA-Z0-9_-]{1,48}',value) else 'direct'

def validate_preferences(value):
    if not isinstance(value,dict) or set(value)-PREFERENCE_KEYS:raise Refused('Невідомі критерії підбору')
    out={}
    for key in ('city','schedule','start'):
        text=value.get(key,'any')
        if not isinstance(text,str) or len(text)>100:raise Refused('Некоректний критерій')
        out[key]=text
    if out['schedule'] not in ('any','day','night','shifts'):raise Refused('Некоректний графік')
    if out['start'] not in ('any','now','week','month'):raise Refused('Некоректна дата початку')
    skills=value.get('skills',{})
    if not isinstance(skills,dict) or set(skills)-SAFE_REQUIREMENTS or any(v not in ('yes','no','unknown') for v in skills.values()):raise Refused('Некоректні навички')
    out['skills']=skills
    amount=value.get('min_pay')
    if amount is not None and (type(amount) not in (int,float) or not 0<=amount<=1000):raise Refused('Некоректна ставка')
    out['min_pay']=amount
    return out

class Settings:
    def __init__(self,env=None):
        env=os.environ if env is None else env
        self.database=Path(env.get('RADAR_DB_PATH','/data/ewu/radar.sqlite3'))
        self.secret=env.get('RADAR_SESSION_SECRET','')
        self.admin_hash=env.get('RADAR_ADMIN_PASSWORD_HASH','')
        self.intake=env.get('RADAR_INTAKE_ENABLED')=='1'
        self.reviewed=env.get('RADAR_PRIVACY_REVIEWED')=='1'
        self.policy_version=env.get('RADAR_POLICY_VERSION','')
        self.controller=env.get('RADAR_CONTROLLER','')
        self.contact=env.get('RADAR_PRIVACY_CONTACT','')
        self.legal_basis=env.get('RADAR_LEGAL_BASIS','')
        self.policy_text=env.get('RADAR_PRIVACY_TEXT','')
        self.retention=int(env.get('RADAR_RETENTION_DAYS','0'))
        self.origin=env.get('RADAR_PUBLIC_ORIGIN','').rstrip('/')
        self.telegram_token=env.get('TELEGRAM_TOKEN','')
        self.bot_enabled=env.get('RADAR_BOT_ENABLED')=='1'
        self.secure=env.get('RADAR_DEV_HTTP')!='1'
        self.admin_ids={x.strip() for x in env.get('EWU_ADMIN_IDS',env.get('ADMIN_CHAT_ID','')).split(',') if re.fullmatch(r'[1-9][0-9]*',x.strip())}
    @property
    def ready(self):
        return bool(self.intake and self.reviewed and self.policy_version and self.controller and self.contact and self.legal_basis and self.policy_text and 1<=self.retention<=3650)
    @property
    def policy_revision(self):
        return digest(dump(dict(version=self.policy_version,controller=self.controller,contact=self.contact,basis=self.legal_basis,text=self.policy_text,retention=self.retention)))
    def notice(self):
        return f'{self.controller}\n{self.policy_text}\nПравова підстава: {self.legal_basis}\nЗберігання: {self.retention} днів.\nКонтакт: {self.contact}\n/withdraw — відкликати заявки; /delete_data — запит на видалення.\nВерсія: {self.policy_version}'

class Radar:
    def __init__(self,settings):
        self.settings=settings;settings.database.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        with self.connect() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.executescript('''
CREATE TABLE IF NOT EXISTS vacancies(id TEXT PRIMARY KEY,public_json TEXT NOT NULL,verified_json TEXT NOT NULL DEFAULT '{}',active INTEGER NOT NULL DEFAULT 0,revision INTEGER NOT NULL DEFAULT 1,updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS vacancy_private(vacancy_id TEXT PRIMARY KEY REFERENCES vacancies(id),notes TEXT NOT NULL DEFAULT '',source_json TEXT NOT NULL DEFAULT '{}');
CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY,title TEXT NOT NULL,commission_json TEXT NOT NULL DEFAULT '{}');
CREATE TABLE IF NOT EXISTS applicants(id TEXT PRIMARY KEY,telegram_hash TEXT UNIQUE NOT NULL,telegram_id INTEGER UNIQUE,phone TEXT,phone_hash TEXT,consent_revision TEXT NOT NULL,consent_text TEXT NOT NULL,consented_at TEXT NOT NULL,expires_at TEXT NOT NULL,deletion_requested INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS applications(id TEXT PRIMARY KEY,applicant_id TEXT NOT NULL REFERENCES applicants(id),vacancy_id TEXT NOT NULL REFERENCES vacancies(id),answers_json TEXT NOT NULL,source TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'NEW',note TEXT NOT NULL DEFAULT '',revision INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL,UNIQUE(applicant_id,vacancy_id));
CREATE TABLE IF NOT EXISTS status_history(id INTEGER PRIMARY KEY,application_id TEXT NOT NULL REFERENCES applications(id),status TEXT NOT NULL,actor TEXT NOT NULL,at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY,action TEXT NOT NULL,object_id TEXT,actor TEXT NOT NULL,at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY,kind TEXT NOT NULL,source TEXT NOT NULL,visit_hash TEXT,at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS deletion_requests(id TEXT PRIMARY KEY,applicant_id TEXT NOT NULL REFERENCES applicants(id),requested_at TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'PENDING');
CREATE UNIQUE INDEX IF NOT EXISTS one_pending_deletion ON deletion_requests(applicant_id) WHERE status='PENDING';
CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY,csrf_hash TEXT NOT NULL,expires_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS outbox(id TEXT PRIMARY KEY,application_id TEXT UNIQUE NOT NULL REFERENCES applications(id),created_at TEXT NOT NULL,seen INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS sources(tag TEXT PRIMARY KEY,label TEXT NOT NULL,spend_grosz INTEGER NOT NULL DEFAULT 0);
CREATE INDEX IF NOT EXISTS phone_duplicates ON applicants(phone_hash);
CREATE INDEX IF NOT EXISTS app_filters ON applications(vacancy_id,status,source);
''')
        os.chmod(settings.database,0o600)
    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.settings.database,timeout=20)
        db.row_factory=sqlite3.Row;db.execute('PRAGMA foreign_keys=ON');db.execute('PRAGMA secure_delete=ON')
        try:
            with db:yield db
        finally:db.close()
    def keyed_hash(self,value):
        if len(self.settings.secret)<32:raise Forbidden('Секрет сервера не налаштований')
        return hmac.new(self.settings.secret.encode(),str(value).encode(),hashlib.sha256).hexdigest()
    def audit(self,db,action,obj,actor):db.execute('INSERT INTO audit(action,object_id,actor,at) VALUES(?,?,?,?)',(action,obj,str(actor),now()))
    def public(self,row):
        public=json.loads(row['public_json']);verified=json.loads(row['verified_json'])
        if not row['active'] or not REQUIRED<=set(verified):return None
        # Never serialize the private row or anything outside this allowlist.
        result={k:v for k,v in public.items() if k in PUBLIC_KEYS and k in verified}
        return dict(id=row['id'],**result,verified_at=row['updated_at'])
    def jobs(self):
        with self.connect() as db:return [job for row in db.execute('SELECT * FROM vacancies WHERE active=1') if (job:=self.public(row))]
    def admin_jobs(self):
        with self.connect() as db:
            return [dict(id=r['id'],public=json.loads(r['public_json']),verified=json.loads(r['verified_json']),active=bool(r['active']),revision=r['revision'],updated_at=r['updated_at'],internal_notes=r['notes'],source=json.loads(r['source_json'])) for r in db.execute('SELECT v.*,p.notes,p.source_json FROM vacancies v JOIN vacancy_private p ON p.vacancy_id=v.id ORDER BY v.id')]
    def save_job(self,actor,jid,body):
        if set(body)-{'public','verified','active','revision','internal_notes'}:raise Refused('Невідомі поля вакансії')
        public=body.get('public',{});verified=body.get('verified',{})
        if not isinstance(public,dict) or set(public)-PUBLIC_KEYS:raise Refused('Непублічні поля заборонені')
        if not isinstance(verified,dict) or set(verified)-set(public):raise Refused('Некоректне підтвердження')
        if any(not isinstance(v,str) or not v.startswith('https://') or len(v)>1000 for v in verified.values()):raise Refused('Для кожного підтвердженого поля потрібне джерело HTTPS')
        if any(not isinstance(public.get(k),str) or not public[k].strip() or len(public[k])>6000 for k in REQUIRED):raise Refused('Заповніть назву, місто, опис, оплату та графік')
        if public.get('schedule_type','any') not in ('day','night','shifts','any'):raise Refused('Некоректний тип графіка')
        amount=public.get('pay_net_min')
        if amount is not None and (type(amount) not in (int,float) or not 0<=amount<=1000):raise Refused('Некоректна мінімальна ставка')
        schedule=public['schedule']
        if not isinstance(schedule,str):raise Refused('Некоректний графік')
        reqs=public.get('requirements',[])
        if not isinstance(reqs,list) or any(x not in SAFE_REQUIREMENTS for x in reqs):raise Refused('Дозволені лише погоджені вимоги до навичок')
        pay=public.get('pay')
        # Public pay is a reviewed description. A numeric filter is optional via a separate validated syntax.
        active=body.get('active',False)
        if type(active)is not bool or (active and not REQUIRED<=set(verified)):raise Refused('Публікація потребує підтвердження всіх основних умов')
        note=body.get('internal_notes','')
        if not isinstance(note,str) or len(note)>10000:raise Refused('Завелика примітка')
        with self.connect() as db:
            row=db.execute('SELECT * FROM vacancies WHERE id=?',(jid,)).fetchone()
            if row is None:raise Refused('Вакансію не знайдено')
            if row['revision']!=body.get('revision'):raise Refused('Дані вже змінено; оновіть сторінку')
            old=json.loads(row['public_json']);previous=json.loads(row['verified_json'])
            # A changed field MUST have a fresh explicit review; editing cannot inherit old verification.
            for key in set(verified):
                if key in old and old[key]!=public[key] and previous.get(key)==verified[key]:
                    raise Refused('Для зміненої умови вкажіть нове підтвердження джерела з датою')
            db.execute('UPDATE vacancies SET public_json=?,verified_json=?,active=?,revision=revision+1,updated_at=? WHERE id=?',(dump(public),dump(verified),int(active),now(),jid))
            db.execute('UPDATE vacancy_private SET notes=? WHERE vacancy_id=?',(note,jid))
            self.audit(db,'vacancy_reviewed',jid,actor)
    def match(self,answers):
        answers=validate_preferences(answers);ranked=[]
        for job in self.jobs():
            reasons=[];score=0
            city=answers['city']
            if city!='any':
                if job['city'].casefold()!=city.casefold():continue
                reasons.append('Вакансія у вибраному місті');score+=3
            schedule=answers['schedule']
            # Only a separately reviewed shift field can establish compatibility.
            known=job.get('schedule_type')
            if schedule!='any' and known:
                if known not in (schedule,'any'):continue
                reasons.append('Підходить графік');score+=2
            elif schedule!='any':reasons.append('Сумісність графіка потрібно уточнити')
            requirements=job.get('requirements',[])
            if any(answers['skills'].get(skill)=='no' for skill in requirements):continue
            if requirements and all(answers['skills'].get(skill)=='yes' for skill in requirements):reasons.append('Підтверджені необхідні навички');score+=2
            elif requirements:reasons.append('Частину навичок потрібно уточнити з рекрутером')
            start=job.get('start_date')
            if answers['start']!='any' and start:
                try:
                    days=(datetime.fromisoformat(start).date()-datetime.now(timezone.utc).date()).days
                    limit={'now':2,'week':7,'month':31}[answers['start']]
                    if days>limit:continue
                    reasons.append('Підходить дата початку');score+=1
                except ValueError:reasons.append('Дату початку потрібно уточнити')
            elif answers['start']!='any':reasons.append('Дата початку не підтверджена')
            if answers['min_pay'] is not None:
                floor=job.get('pay_net_min')
                if floor is not None and floor<answers['min_pay']:continue
                reasons.append('Відповідає побажанню щодо оплати' if floor is not None else 'Погодинну ставку для порівняння потрібно уточнити')
            ranked.append((score,dict(**job,reasons=reasons or ['Активна вакансія з перевіреними основними умовами'])))
        return [job for _,job in sorted(ranked,key=lambda v:(-v[0],v[1]['id']))]
    def record_visit(self,user,source):
        # Daily deduplication; no Telegram identifier or raw payload in analytics.
        source=source_tag(source);visit=self.keyed_hash(str(user)+'|'+now()[:10]+'|'+source)
        with self.connect() as db:
            if not db.execute("SELECT 1 FROM events WHERE kind='start' AND visit_hash=?",(visit,)).fetchone():db.execute('INSERT INTO events(kind,source,visit_hash,at) VALUES(?,?,?,?)',('start',source,visit,now()))
    def consent(self,user):
        s=self.settings
        if not s.ready:raise Forbidden('Збір контактів вимкнений до перевірки умов обробки даних')
        end=(datetime.now(timezone.utc)+timedelta(days=s.retention)).isoformat(timespec='seconds')
        with self.connect() as db:
            old=db.execute('SELECT id,deletion_requested FROM applicants WHERE telegram_hash=?',(self.keyed_hash(user),)).fetchone()
            if old and old['deletion_requested']:raise Forbidden('Спочатку потрібно обробити запит на видалення')
            aid=old['id'] if old else uid()
            db.execute('INSERT INTO applicants(id,telegram_hash,telegram_id,consent_revision,consent_text,consented_at,expires_at) VALUES(?,?,?,?,?,?,?) ON CONFLICT(telegram_hash) DO UPDATE SET consent_revision=excluded.consent_revision,consent_text=excluded.consent_text,consented_at=excluded.consented_at,expires_at=excluded.expires_at',(aid,self.keyed_hash(user),user,s.policy_revision,s.notice(),now(),end))
            self.audit(db,'consent_recorded',aid,'candidate')
        return aid
    def submit(self,user,jids,phone,answers,source):
        if not self.settings.ready:raise Forbidden('Збір контактів вимкнений')
        answers=validate_preferences(answers)
        if not isinstance(jids,list) or not 1<=len(jids)<=11 or any(not isinstance(j,str) for j in jids):raise Refused('Оберіть вакансії')
        if not isinstance(phone,str) or not re.fullmatch(r'\+?[0-9][0-9 ()-]{7,18}[0-9]',phone):raise Refused('Некоректний телефон')
        phone='+'+re.sub(r'\D','',phone);source=source_tag(source)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            person=db.execute('SELECT * FROM applicants WHERE telegram_hash=?',(self.keyed_hash(user),)).fetchone()
            if person is None or person['consent_revision']!=self.settings.policy_revision or person['deletion_requested'] or person['expires_at']<=now():raise Forbidden('Потрібна чинна згода')
            result=[]
            # The write transaction already serializes rights and duplicate checks.
            for jid in dict.fromkeys(jids):
                row=db.execute('SELECT * FROM vacancies WHERE id=?',(jid,)).fetchone()
                if row is None or not self.public(row):raise Refused('Вакансія вже недоступна')
                existing=db.execute('SELECT id,status FROM applications WHERE applicant_id=? AND vacancy_id=?',(person['id'],jid)).fetchone()
                if existing:result.append(dict(id=existing['id'],duplicate=True,status=existing['status']));continue
                aid=uid()
                db.execute('INSERT INTO applications(id,applicant_id,vacancy_id,answers_json,source,created_at) VALUES(?,?,?,?,?,?)',(aid,person['id'],jid,dump(answers),source,now()))
                db.execute('INSERT INTO status_history(application_id,status,actor,at) VALUES(?,?,?,?)',(aid,'NEW','candidate',now()))
                db.execute('INSERT INTO outbox(id,application_id,created_at) VALUES(?,?,?)',(uid(),aid,now()))
                self.audit(db,'application_created',aid,'candidate');result.append(dict(id=aid,duplicate=False,status='NEW'))
            db.execute('UPDATE applicants SET phone=?,phone_hash=? WHERE id=?',(phone,self.keyed_hash(phone),person['id']))
            if any(not x['duplicate'] for x in result):
                db.execute('INSERT INTO events(kind,source,at) VALUES(?,?,?)',('form_completed',source,now()))
            return result
    def own(self,user):
        with self.connect() as db:
            return [dict(id=r['id'],vacancy_id=r['vacancy_id'],status=r['status'],created_at=r['created_at']) for r in db.execute('SELECT a.* FROM applications a JOIN applicants p ON p.id=a.applicant_id WHERE p.telegram_hash=?',(self.keyed_hash(user),))]
    def withdraw(self,user,delete=False):
        with self.connect() as db:
            p=db.execute('SELECT id FROM applicants WHERE telegram_hash=?',(self.keyed_hash(user),)).fetchone()
            if p is None:return
            for row in db.execute("SELECT id FROM applications WHERE applicant_id=? AND status!='WITHDRAWN'",(p['id'],)).fetchall():
                db.execute("UPDATE applications SET status='WITHDRAWN',revision=revision+1 WHERE id=?",(row['id'],))
                db.execute('INSERT INTO status_history(application_id,status,actor,at) VALUES(?,?,?,?)',(row['id'],'WITHDRAWN','candidate',now()))
            db.execute("UPDATE applicants SET consent_revision='' WHERE id=?",(p['id'],))
            if delete:
                db.execute('UPDATE applicants SET deletion_requested=1 WHERE id=?',(p['id'],))
                db.execute('INSERT OR IGNORE INTO deletion_requests(id,applicant_id,requested_at) VALUES(?,?,?)',(uid(),p['id'],now()))
            self.audit(db,'deletion_requested' if delete else 'applications_withdrawn',p['id'],'candidate')
    def candidates(self,q='',vacancy='',city='',status='',source=''):
        if status and status not in STATUSES:raise Refused('Невідомий статус')
        sql='SELECT a.*,p.phone,p.phone_hash,p.deletion_requested,v.public_json FROM applications a JOIN applicants p ON p.id=a.applicant_id JOIN vacancies v ON v.id=a.vacancy_id WHERE 1=1';params=[]
        for clause,value in [('a.vacancy_id',vacancy),('a.status',status),('a.source',source)]:
            if value:sql+=' AND '+clause+'=?';params.append(value)
        if q:sql+=' AND (a.id LIKE ? OR p.phone LIKE ?)';params.extend(['%'+q[:100]+'%']*2)
        if city:sql+=" AND json_extract(a.answers_json,'$.city')=?";params.append(city)
        with self.connect() as db:
            result=[]
            for row in db.execute(sql+' ORDER BY a.created_at DESC LIMIT 500',params):
                answers=json.loads(row['answers_json'])
                item=dict(row);item['answers']=answers;item['vacancy']=json.loads(item.pop('public_json'))['title'];item.pop('answers_json');ph=item.pop('phone_hash')
                item['possible_duplicate']=db.execute('SELECT count(*) FROM applicants WHERE phone_hash=?',(ph,)).fetchone()[0]>1 if ph else False
                result.append(item)
            return result
    def detail(self,aid):
        with self.connect() as db:
            row=db.execute('SELECT a.*,p.phone,p.consented_at,p.expires_at,p.deletion_requested FROM applications a JOIN applicants p ON p.id=a.applicant_id WHERE a.id=?',(aid,)).fetchone()
            if row is None:raise Refused('Заявку не знайдено')
            item=dict(row);item['answers']=json.loads(item.pop('answers_json'))
            item['history']=[dict(r) for r in db.execute('SELECT status,actor,at FROM status_history WHERE application_id=? ORDER BY id',(aid,))]
            return item
    def update_application(self,actor,aid,status,note,revision):
        if status not in STATUSES or not isinstance(note,str) or len(note)>6000:raise Refused('Некоректна зміна')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT a.*,p.deletion_requested FROM applications a JOIN applicants p ON p.id=a.applicant_id WHERE a.id=?',(aid,)).fetchone()
            if row is None or row['revision']!=revision:raise Refused('Заявку змінено або не знайдено')
            if (row['status']=='WITHDRAWN' or row['deletion_requested']) and status!='WITHDRAWN':raise Refused('Відкликану заявку не можна поновити без нового звернення')
            db.execute('UPDATE applications SET status=?,note=?,revision=revision+1 WHERE id=?',(status,note,aid))
            if row['status']!=status:db.execute('INSERT INTO status_history(application_id,status,actor,at) VALUES(?,?,?,?)',(aid,status,str(actor),now()))
            self.audit(db,'application_updated',aid,actor)
    def erase(self,actor,aid):
        with self.connect() as db:
            p=db.execute('SELECT * FROM applicants WHERE id=?',(aid,)).fetchone()
            if p is None or not p['deletion_requested']:raise Refused('Немає запиту на видалення')
            self._erase(db,aid);self.audit(db,'deletion_completed',None,actor)
    def _erase(self,db,aid):
        db.execute('DELETE FROM outbox WHERE application_id IN (SELECT id FROM applications WHERE applicant_id=?)',(aid,))
        db.execute('DELETE FROM status_history WHERE application_id IN (SELECT id FROM applications WHERE applicant_id=?)',(aid,))
        db.execute('DELETE FROM applications WHERE applicant_id=?',(aid,));db.execute('DELETE FROM deletion_requests WHERE applicant_id=?',(aid,))
        db.execute('UPDATE audit SET object_id=NULL WHERE object_id=?',(aid,));db.execute('DELETE FROM applicants WHERE id=?',(aid,))
    def cleanup(self):
        with self.connect() as db:
            for p in db.execute('SELECT id FROM applicants WHERE expires_at<=?',(now(),)).fetchall():self._erase(db,p['id'])
            db.execute('DELETE FROM sessions WHERE expires_at<=?',(now(),))
            # Daily anonymous visit hashes are no longer needed after 48 hours; counts remain.
            cutoff=(datetime.now(timezone.utc)-timedelta(days=2)).isoformat(timespec='seconds')
            db.execute('UPDATE events SET visit_hash=NULL WHERE at<?',(cutoff,))
    def metrics(self):
        with self.connect() as db:
            sources={r['source'] for r in db.execute('SELECT DISTINCT source FROM events')}|{r['source'] for r in db.execute('SELECT DISTINCT source FROM applications')}|{r['tag'] for r in db.execute('SELECT tag FROM sources')}
            rows=[]
            for source in sorted(sources):
                visits=db.execute("SELECT count(*) FROM events WHERE kind='start' AND source=?",(source,)).fetchone()[0]
                forms=db.execute("SELECT count(*) FROM events WHERE kind='form_completed' AND source=?",(source,)).fetchone()[0]
                apps=db.execute('SELECT count(*) FROM applications WHERE source=?',(source,)).fetchone()[0]
                candidate_count=db.execute('SELECT count(DISTINCT applicant_id) FROM applications WHERE source=?',(source,)).fetchone()[0]
                counts={status:db.execute('SELECT count(DISTINCT a.applicant_id) FROM applications a JOIN status_history h ON h.application_id=a.id WHERE a.source=? AND h.status=?',(source,status)).fetchone()[0] for status in ('CONTACT','INTERVIEW','HIRED')}
                spend=db.execute('SELECT spend_grosz FROM sources WHERE tag=?',(source,)).fetchone();spend=spend[0] if spend else None
                rows.append(dict(source=source,starts=visits,forms=forms,applications=apps,candidates=candidate_count,**counts,spend_grosz=spend,cost_per_interview_grosz=round(spend/counts['INTERVIEW']) if spend is not None and counts['INTERVIEW'] else None,cost_per_hire_grosz=round(spend/counts['HIRED']) if spend is not None and counts['HIRED'] else None,start_to_application=round(candidate_count/visits,4) if visits else None))
            return dict(sources=rows,by_vacancy=[dict(vacancy_id=r[0],applications=r[1]) for r in db.execute('SELECT vacancy_id,count(*) FROM applications GROUP BY vacancy_id')],notifications=db.execute('SELECT count(*) FROM outbox WHERE seen=0').fetchone()[0])
    def backup(self,path):
        path=Path(path);path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        with self.connect() as original:
            target=sqlite3.connect(path)
            try:
                original.backup(target)
                if target.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise Refused('Помилка перевірки копії')
            finally:target.close()
        os.chmod(path,0o600);return str(path)
