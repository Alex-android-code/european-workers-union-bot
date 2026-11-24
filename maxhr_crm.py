"""Private MaxHR CRM on the existing privacy database; money is stored in grosz."""
import csv
import io
import json
import re
from decimal import Decimal, InvalidOperation
from recruitment import Journey, NEXT

STATUSES=('NEW','SCREENING','SENT_MAXHR','AWAITING_EMPLOYMENT','EMPLOYED','HOURS_24','HOURS_100','COMMISSION_CONFIRMED','COMMISSION_PAID','REJECTED')
for i,status in enumerate(STATUSES[:-2]):
    NEXT.setdefault(status,set()).update({STATUSES[i+1],'REJECTED','WITHDRAWN'})
NEXT.setdefault('COMMISSION_CONFIRMED',set()).update({'COMMISSION_PAID','REJECTED','WITHDRAWN'})
NEXT.setdefault('COMMISSION_PAID',set());NEXT.setdefault('REJECTED',set())
DOCUMENTS=('passport','pesel','residence_card','visa','work_permit','sanepid','driving_licence')

class SimpleForm:
    """Only explicit vacancy requirements can add document yes/no/unknown questions."""
    def __init__(self,job):
        required=job.get('documents',[])
        if not isinstance(required,list) or any(d not in DOCUMENTS for d in required):raise ValueError('Unknown document requirement')
        self.fields=['first_name','last_name','phone']+required
        self.data={'vacancy_id':job['id']};self.index=0
    @property
    def field(self):return self.fields[self.index] if self.index<len(self.fields) else None
    def answer(self,value):
        if not isinstance(value,str) or not self.field:raise ValueError('Invalid answer')
        value=value.strip()
        if self.field in DOCUMENTS:
            if value not in ('yes','no','unknown'):raise ValueError('Use yes/no/unknown')
        elif self.field=='phone':
            if not re.fullmatch(r'\+?[0-9][0-9 ()-]{7,18}[0-9]',value):raise ValueError('Invalid phone')
            value='+'+re.sub(r'[^0-9]','',value)
        elif len(value)>80 or not re.fullmatch(r"[^\W\d_]+(?:[ '\-’][^\W\d_]+)*",value,re.UNICODE):raise ValueError('Invalid name')
        self.data[self.field]=value;self.index+=1
        return self.field is None

class MaxHRCrm:
    def __init__(self,store,admins=()):
        self.store=store;self.journey=Journey(store,admins);self.db=store.db
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS maxhr_finance(
          application_id TEXT PRIMARY KEY,expected INTEGER,confirmed INTEGER NOT NULL DEFAULT 0,
          paid INTEGER NOT NULL DEFAULT 0,revision INTEGER NOT NULL DEFAULT 1,terms TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS maxhr_finance_events(
          id INTEGER PRIMARY KEY,application_id TEXT NOT NULL,actor TEXT NOT NULL,
          at TEXT NOT NULL,before_json TEXT NOT NULL,after_json TEXT NOT NULL);
        ''')
    def submit(self,user,form,locale,enabled=False):
        if not enabled or form.field is not None or not self.store.allowed(user):raise PermissionError('Reviewed intake required')
        # Duplicate matching is private and never reveals another candidate's identity.
        for (raw,) in self.db.execute("SELECT data FROM applications WHERE kind='maxhr'"):
            data=json.loads(raw)
            if data.get('phone')==form.data['phone'] and data.get('vacancy_id')==form.data['vacancy_id']:raise ValueError('Duplicate application')
        self.store.begin_intake(user,'maxhr')
        for index,(key,value) in enumerate(form.data.items()):
            aid=self.store.save_answer(user,key,value,completed=index==len(form.data)-1)
        self.journey.register(aid,locale)
        return aid
    def statistics(self,actor):
        self.journey._admin(actor)
        return dict(self.db.execute('SELECT status,count(*) FROM candidate_journey GROUP BY status'))
    def export(self,actor):
        self.journey._admin(actor)
        out=io.StringIO();w=csv.writer(out);w.writerow(['status','count'])
        for status,count in self.statistics(actor).items():w.writerow([status,count])
        return out.getvalue()
    def terms(self,actor,aid,terms):
        self.journey._admin(actor);self.journey._row(aid)
        # Ambiguous bands and project colours require manual clarification.
        match=re.fullmatch(r'\s*(\d+(?:[.,]\d{1,2})?)\s*(?:zł|PLN)(?: за кандидата)?\s*',terms.get('base',''),re.I)
        expected=int(Decimal(match[1].replace(',','.'))*100) if match else None
        with self.db:self.db.execute('INSERT INTO maxhr_finance(application_id,expected,terms) VALUES(?,?,?) ON CONFLICT(application_id) DO UPDATE SET expected=excluded.expected,terms=excluded.terms,revision=revision+1',(aid,expected,json.dumps(terms,ensure_ascii=False)))
        return self.balance(actor,aid)
    def balance(self,actor,aid):
        self.journey._admin(actor);self.journey._row(aid)
        row=self.db.execute('SELECT expected,confirmed,paid,revision,terms FROM maxhr_finance WHERE application_id=?',(aid,)).fetchone()
        if row is None:raise ValueError('Commission terms not assigned')
        return dict(expected=row[0],confirmed=row[1],paid=row[2],debt=row[1]-row[2],revision=row[3],terms=json.loads(row[4]))
    def payment(self,actor,aid,confirmed,paid,revision):
        before=self.balance(actor,aid)
        if any(type(v)is not int for v in (confirmed,paid,revision)) or paid<0 or confirmed<paid:raise ValueError('Invalid money')
        if revision!=before['revision']:raise ValueError('Stale finance revision')
        row=self.journey._row(aid)
        if not self.store.allowed(row['user_id']):raise PermissionError('Processing paused')
        with self.db:
            change=self.db.execute('UPDATE maxhr_finance SET confirmed=?,paid=?,revision=revision+1 WHERE application_id=? AND revision=?',(confirmed,paid,aid,revision))
            if change.rowcount!=1:raise ValueError('Concurrent finance update')
            after=self.balance(actor,aid)
            self.db.execute('INSERT INTO maxhr_finance_events(application_id,actor,at,before_json,after_json) VALUES(?,?,?,?,?)',(aid,str(actor),self.journey._now(),json.dumps(before),json.dumps(after)))
        return after
