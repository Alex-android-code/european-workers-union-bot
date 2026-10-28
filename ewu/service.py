"""Transactional recruitment core; no Telegram, Google, AI or GreenWork network calls."""
from datetime import datetime, timezone, timedelta
from functools import wraps
import hashlib
import json
import uuid

from privacy.onboarding import revision, render, UI
from .domain import Actor, Denied, NEXT, STATUSES, CANDIDATE_ACTIONS, PROFILE_FIELDS, RIGHTS


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def atomic(fn):
    @wraps(fn)
    def wrapper(self, *args, **kwargs):
        with self.db.transaction():
            return fn(self, *args, **kwargs)
    return wrapper


class Recruitment:
    def __init__(self, db, policy, clock=None):
        self.db, self.policy = db, policy
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def now(self):
        return self.clock().astimezone(timezone.utc).isoformat()

    @staticmethod
    def uid():
        return str(uuid.uuid4())

    def legal(self):
        if self.policy.get('legal_review_approved') is not True:
            raise Denied('Legal approval required')
        if self.policy.get('core_legal_basis') not in ('art6_1_b','art6_1_c','art6_1_f'):
            raise Denied('Core legal basis required')
        try:
            effective = datetime.fromisoformat(self.policy['effective_at'])
            if effective.tzinfo is None or effective > self.clock():
                raise ValueError()
            if any(not self.policy['notices'][lang]['controller'].strip() for lang in UI):
                raise ValueError()
        except (KeyError, TypeError, ValueError):
            raise Denied('Effective approved notice required') from None

    def role(self, actor, *roles):
        row = self.db.one('SELECT * FROM ewu2_actors WHERE id=?', (str(actor.id),))
        if row is None or row['role'] not in roles:
            raise Denied('Access denied')
        return row

    def audit(self, kind, actor, entity):
        previous = self.db.one('SELECT value FROM ewu2_audit_head WHERE singleton=1')['value']
        event = {'id': self.uid(), 'kind': kind, 'actor_id': str(actor.id), 'entity_id': entity,
                 'at': self.now(), 'previous_hash': previous}
        digest = hashlib.sha256(encoded(event).encode()).hexdigest()
        self.db.execute('INSERT INTO ewu2_audit_events VALUES(?,?,?,?,?,?,?)',
                        (*event.values(), digest))
        self.db.execute('UPDATE ewu2_audit_head SET value=? WHERE singleton=1', (digest,))
        return digest

    def enqueue(self, topic, entity, key, payload=None):
        self.db.execute('INSERT INTO ewu2_outbox(id,topic,entity_id,dedupe_key,payload,available_at) VALUES(?,?,?,?,?,?) ON CONFLICT(dedupe_key) DO NOTHING',
                        (self.uid(), topic, entity, key, encoded(payload or {}), self.now()))

    def candidate(self, user_id):
        return self.db.one('SELECT * FROM ewu2_candidates WHERE telegram_id=?', (str(user_id),))

    def allowed(self, user_id):
        self.legal()
        row = self.db.one('SELECT * FROM ewu2_privacy_state WHERE user_id=?', (str(user_id),))
        pending = self.db.one("SELECT id FROM ewu2_rights_requests WHERE user_id=? AND status='pending' AND kind IN ('delete','restrict','object')", (str(user_id),))
        return bool(row and row['allowed'] and row['revision'] == revision(self.policy) and not pending)

    @atomic
    def privacy(self, actor, lang, action, document_revision, purpose=None):
        self.legal()
        if lang not in UI or document_revision != revision(self.policy):
            raise Denied('Current policy required')
        if action not in ('acknowledged','declined','withdrawn','consent_granted','consent_refused','consent_withdrawn'):
            raise Denied('Unknown action')
        if action.startswith('consent_'):
            definitions = self.policy.get('optional_consents', {})
            if purpose not in definitions or not definitions[purpose].get('legal_review_approved'):
                raise Denied('Unreviewed optional purpose')
            if not all(definitions[purpose].get('texts', {}).get(l) for l in UI):
                raise Denied('Incomplete consent text')
            text = definitions[purpose]['texts'][lang]
        else:
            text = render(self.policy, lang)
        previous = self.db.one('SELECT value FROM ewu2_audit_head WHERE singleton=1')['value']
        entry = [self.uid(),str(actor.id),self.policy['version'],document_revision,lang,
                 purpose or 'information',action,'telegram',text,self.now(),previous]
        digest = hashlib.sha256(encoded(entry).encode()).hexdigest()
        self.db.execute('INSERT INTO ewu2_privacy_records VALUES(?,?,?,?,?,?,?,?,?,?,?,?)', (*entry,digest))
        if purpose:
            self.db.execute('INSERT INTO ewu2_consents VALUES(?,?,?,?,?) ON CONFLICT(user_id,purpose) DO UPDATE SET granted=excluded.granted,version=excluded.version,at=excluded.at',
                            (str(actor.id),purpose,int(action=='consent_granted'),self.policy['version'],self.now()))
        else:
            self.db.execute('INSERT INTO ewu2_privacy_state VALUES(?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET revision=excluded.revision,allowed=excluded.allowed,language=excluded.language',
                            (str(actor.id),document_revision,int(action=='acknowledged'),lang))
            self.db.execute('DELETE FROM ewu2_sessions WHERE user_id=?', (str(actor.id),))
            if action=='withdrawn':
                self.db.execute('UPDATE ewu2_consents SET granted=0,at=? WHERE user_id=?', (self.now(),str(actor.id)))
        self.audit('privacy.'+action,actor,entry[0]+':'+digest)
        return self.allowed(actor.id)

    @atomic
    def register(self, actor, lang, profile, phone=None):
        if not self.allowed(actor.id):
            raise Denied('Onboarding required')
        if lang not in UI or not isinstance(profile,dict) or set(profile)-PROFILE_FIELDS:
            raise Denied('Unsupported profile fields')
        if any(not isinstance(v,(str,bool)) or len(str(v))>500 for v in profile.values()):
            raise Denied('Invalid profile')
        if phone is not None:
            import re
            if not re.fullmatch(r'\+?[0-9][0-9 ()-]{7,18}[0-9]',phone):
                raise Denied('Invalid phone')
        existing = self.candidate(actor.id)
        if existing:
            candidate_id = existing['id']
            merged = {**json.loads(existing['profile']),**profile}
            self.db.execute('UPDATE ewu2_candidates SET language=?,profile=?,updated_at=? WHERE id=?', (lang,encoded(merged),self.now(),candidate_id))
        else:
            candidate_id = self.uid()
            self.db.execute('INSERT INTO ewu2_candidates(id,telegram_id,language,profile,restricted,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',
                            (candidate_id,str(actor.id),lang,encoded(profile),0,self.now(),self.now()))
        if phone:
            self.db.execute('INSERT INTO ewu2_contacts VALUES(?,?,?,?) ON CONFLICT(candidate_id,kind) DO UPDATE SET value=excluded.value',
                            (self.uid(),candidate_id,'phone',phone))
        current_profile=json.loads(self.db.one('SELECT profile FROM ewu2_candidates WHERE id=?',(candidate_id,))['profile'])
        contact=self.db.one("SELECT id FROM ewu2_contacts WHERE candidate_id=? AND kind='phone'",(candidate_id,))
        state='PROFILE_COMPLETE' if all(current_profile.get(k) for k in ('name','city','profession')) and contact else 'PROFILE_IN_PROGRESS'
        self.db.execute('UPDATE ewu2_candidates SET status=? WHERE id=?',(state,candidate_id))
        if state=='PROFILE_COMPLETE':
            self.db.execute("UPDATE ewu2_followups SET status='cancelled' WHERE candidate_id=? AND application_id IS NULL AND status='pending'",(candidate_id,))
        event=self.audit('candidate.updated' if existing else 'candidate.created',actor,candidate_id)
        self.enqueue('sheets',candidate_id,'candidate-event:'+event)
        return candidate_id

    def self_data(self, actor):
        row = self.candidate(actor.id)
        if row is None:
            return {'candidate':None,'applications':[]}
        return {'candidate':{**row,'profile':json.loads(row['profile'])},
                'contacts':self.db.all('SELECT kind,value FROM ewu2_contacts WHERE candidate_id=?',(row['id'],)),
                'applications':self.db.all('SELECT id,vacancy_id,status FROM ewu2_applications WHERE candidate_id=?',(row['id'],))}

    @atomic
    def rights(self, actor, kind):
        if kind not in RIGHTS:
            raise Denied('Unknown right')
        if kind=='view':
            return self.self_data(actor)
        existing = self.db.one("SELECT id FROM ewu2_rights_requests WHERE user_id=? AND kind=? AND status='pending'",(str(actor.id),kind))
        if existing:
            return existing['id']
        request_id = self.uid()
        self.db.execute('INSERT INTO ewu2_rights_requests VALUES(?,?,?,?,?)',(request_id,str(actor.id),kind,'pending',self.now()))
        if kind in ('delete','withdraw','object','restrict'):
            self.db.execute('UPDATE ewu2_privacy_state SET allowed=0 WHERE user_id=?',(str(actor.id),))
            self.db.execute('UPDATE ewu2_candidates SET restricted=1 WHERE telegram_id=?',(str(actor.id),))
            self.db.execute('DELETE FROM ewu2_sessions WHERE user_id=?',(str(actor.id),))
            self.db.execute("UPDATE ewu2_followups SET status='cancelled' WHERE candidate_id IN (SELECT id FROM ewu2_candidates WHERE telegram_id=?) OR application_id IN (SELECT id FROM ewu2_applications WHERE candidate_id IN (SELECT id FROM ewu2_candidates WHERE telegram_id=?))",(str(actor.id),str(actor.id)))
        if kind=='withdraw':
            self.db.execute('UPDATE ewu2_consents SET granted=0,at=? WHERE user_id=?',(self.now(),str(actor.id)))
        state=self.db.one('SELECT language FROM ewu2_privacy_state WHERE user_id=?',(str(actor.id),))
        language=state['language'] if state else 'uk'
        previous=self.db.one('SELECT value FROM ewu2_audit_head WHERE singleton=1')['value']
        evidence=[self.uid(),str(actor.id),self.policy.get('version') or 'unconfigured',revision(self.policy),language,'rights',kind,'telegram','Rights request registered for operator review',self.now(),previous]
        digest=hashlib.sha256(encoded(evidence).encode()).hexdigest()
        self.db.execute('INSERT INTO ewu2_privacy_records VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(*evidence,digest))
        self.audit('rights.'+kind,actor,request_id+':'+digest)
        self.enqueue('operator',request_id,'rights:'+request_id)
        candidate=self.candidate(actor.id)
        if candidate:self.enqueue('sheets',candidate['id'],'rights-sync:'+request_id)
        return request_id

    @atomic
    def grant_actor(self, actor, subject, role, partner_id=None):
        self.role(actor,'owner')
        if role not in ('owner','recruiter','finance','partner'):
            raise Denied('Unknown role')
        if role=='partner' and not self.db.one('SELECT id FROM ewu2_partners WHERE id=?',(partner_id,)):
            raise Denied('Partner scope required')
        self.db.execute('INSERT INTO ewu2_actors VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET role=excluded.role,partner_id=excluded.partner_id',(str(subject),role,partner_id))
        self.audit('access.granted',actor,str(subject))

    @atomic
    def partner(self, actor, name, contact):
        self.role(actor,'owner','recruiter')
        if not name or len(name)>200 or len(contact)>300:
            raise Denied('Invalid partner')
        partner_id = self.uid()
        self.db.execute('INSERT INTO ewu2_partners VALUES(?,?,?)',(partner_id,name,contact))
        self.audit('partner.created',actor,partner_id)
        return partner_id

    @atomic
    def vacancy(self, actor, partner_id, external_id, data, expires_at, confirmed_at=None):
        role = self.role(actor,'owner','recruiter','partner')
        if role['role']=='partner' and role['partner_id']!=partner_id:
            raise Denied('Partner scope denied')
        required = {'title','location','address','rate','payment_type','schedule','housing','transport','requirements','places','start_date','coordinator'}
        if set(data)!=required or any(len(str(v))>1000 for v in data.values()) or type(data['places']) is not int or data['places']<0:
            raise Denied('Incomplete vacancy')
        expiration = datetime.fromisoformat(expires_at)
        if expiration.tzinfo is None or expiration<=self.clock():
            raise Denied('Vacancy must be freshly confirmed')
        confirmation = datetime.fromisoformat(confirmed_at) if confirmed_at else self.clock()
        if confirmation.tzinfo is None or confirmation>self.clock() or expiration<=confirmation:
            raise Denied('Invalid confirmation evidence')
        existing = self.db.one('SELECT id FROM ewu2_vacancies WHERE partner_id=? AND external_id=?',(partner_id,external_id))
        vacancy_id = existing['id'] if existing else self.uid()
        self.db.execute("INSERT INTO ewu2_vacancies VALUES(?,?,?,?,?,?,?) ON CONFLICT(partner_id,external_id) DO UPDATE SET data=excluded.data,status=excluded.status,confirmed_at=excluded.confirmed_at,expires_at=excluded.expires_at",
                        (vacancy_id,partner_id,external_id,encoded(data),'CONFIRMED',confirmation.astimezone(timezone.utc).isoformat(),expiration.astimezone(timezone.utc).isoformat()))
        event=self.audit('vacancy.confirmed',actor,vacancy_id)
        self.enqueue('sheets',vacancy_id,'vacancy-event:'+event)
        return vacancy_id

    @atomic
    def expire_vacancies(self):
        rows = self.db.all("SELECT id,partner_id FROM ewu2_vacancies WHERE status='CONFIRMED' AND expires_at<=?",(self.now(),))
        for row in rows:
            self.db.execute("UPDATE ewu2_vacancies SET status='NEEDS_CONFIRMATION' WHERE id=?",(row['id'],))
            event=self.audit('vacancy.needs_confirmation',Actor('system'),row['id'])
            self.enqueue('sheets',row['id'],'vacancy-expired:'+event)
            self.enqueue('partner_confirmation',row['id'],'confirm:'+row['id']+':'+self.now())
        return len(rows)

    def matches(self, actor):
        if not self.allowed(actor.id):
            raise Denied('Onboarding required')
        candidate = self.candidate(actor.id)
        if candidate is None or candidate['status']!='PROFILE_COMPLETE':
            raise Denied('Complete profile required')
        profile = json.loads(candidate['profile'])
        rows = self.db.all("SELECT * FROM ewu2_vacancies WHERE status='CONFIRMED' AND expires_at>?",(self.now(),))
        # Deterministic fallback: every displayed condition comes from a confirmed registry row.
        rows = [r for r in rows if json.loads(r['data'])['places']>0]
        profession = profile.get('profession','').casefold()
        rows.sort(key=lambda r: (profession not in json.loads(r['data'])['title'].casefold(),r['id']))
        return [{**r,'data':json.loads(r['data'])} for r in rows]

    @atomic
    def apply(self, actor, vacancy_id):
        live = {r['id']:r for r in self.matches(actor)}
        if vacancy_id not in live:
            raise Denied('Confirmed vacancy required')
        candidate = self.candidate(actor.id)
        existing = self.db.one('SELECT id FROM ewu2_applications WHERE candidate_id=? AND vacancy_id=?',(candidate['id'],vacancy_id))
        if existing:
            return existing['id']
        application_id = self.uid()
        self.db.execute('INSERT INTO ewu2_applications VALUES(?,?,?,?,?,?,?,?)',
                        (application_id,candidate['id'],vacancy_id,live[vacancy_id]['partner_id'],'NEW','{}',self.now(),self.now()))
        self.audit('application.created',actor,application_id)
        for status in ('PRIVACY_COMPLETED','PROFILE_IN_PROGRESS','PROFILE_COMPLETE','MATCHED','INTERESTED'):
            self.transition(actor,application_id,status)
        return application_id

    def application(self, actor, application_id):
        row = self.db.one('SELECT * FROM ewu2_applications WHERE id=?',(application_id,))
        if row is None:
            raise Denied('Application unavailable')
        candidate = self.candidate(actor.id)
        if candidate and candidate['id']==row['candidate_id']:
            return row
        role = self.role(actor,'owner','recruiter','partner')
        if role['role']=='partner' and (role['partner_id']!=row['partner_id'] or row['status'] in STATUSES[:6]):
            raise Denied('Partner scope denied')
        return row

    @atomic
    def instructions(self, actor, application_id, details):
        row = self.application(actor,application_id)
        self.role(actor,'owner','partner')
        required = {'address','arrival_at','coordinator','transport','packing'}
        if set(details)!=required or any(not isinstance(v,str) or not v.strip() or len(v)>500 for v in details.values()):
            raise Denied('Verified instructions required')
        date = datetime.fromisoformat(details['arrival_at'])
        if date.tzinfo is None or date<=self.clock():
            raise Denied('Future arrival time required')
        if row['status']!='ACCEPTED':
            raise Denied('Partner acceptance required')
        self.db.execute('UPDATE ewu2_applications SET instructions=? WHERE id=?',(encoded(details),application_id))
        self.audit('instructions.confirmed',actor,application_id)

    @atomic
    def transition(self, actor, application_id, target):
        row = self.application(actor,application_id)
        if target==row['status']:
            return row
        if target not in NEXT.get(row['status'],set()):
            raise Denied('Invalid status transition')
        candidate = self.db.one('SELECT * FROM ewu2_candidates WHERE id=?',(row['candidate_id'],))
        is_self = candidate['telegram_id']==str(actor.id)
        if not self.allowed(candidate['telegram_id']) and target not in ('CANCELLED','ON_HOLD'):
            raise Denied('Processing restricted')
        if is_self:
            if target not in CANDIDATE_ACTIONS:
                raise Denied('Authorized confirmation required')
        else:
            self.role(actor,'owner','recruiter','partner')
        if target=='SUBMITTED_TO_PARTNER':
            self.role(actor,'owner','recruiter')
            if self.policy.get('partner_transfer_approved') is not True:
                raise Denied('Partner transfer legal approval required')
            vacancy = self.db.one('SELECT * FROM ewu2_vacancies WHERE id=?',(row['vacancy_id'],))
            if vacancy['status']!='CONFIRMED' or vacancy['expires_at']<=self.now():
                raise Denied('Vacancy requires reconfirmation')
        if target in ('ACCEPTED','REJECTED','START_DATE_CONFIRMED','CHECKED_IN','STARTED_WORK'):
            self.role(actor,'owner','partner')
        if target=='START_DATE_CONFIRMED' and not json.loads(row['instructions']):
            raise Denied('Verified instructions required')
        if target=='ARRIVED':
            if not is_self:
                raise Denied('Candidate arrival report required')
            self.db.execute('INSERT INTO ewu2_arrivals(application_id,reported_at) VALUES(?,?) ON CONFLICT(application_id) DO NOTHING',(application_id,self.now()))
        if target=='CHECKED_IN':
            if self.db.one('SELECT * FROM ewu2_arrivals WHERE application_id=?',(application_id,)) is None:
                raise Denied('Arrival report required')
            self.db.execute('UPDATE ewu2_arrivals SET confirmed_at=?,confirmed_by=? WHERE application_id=?',(self.now(),str(actor.id),application_id))
        if target=='STARTED_WORK':
            self.db.execute('INSERT INTO ewu2_employment_starts VALUES(?,?,?) ON CONFLICT(application_id) DO NOTHING',(application_id,self.now(),str(actor.id)))
        self.db.execute('UPDATE ewu2_applications SET status=?,updated_at=? WHERE id=?',(target,self.now(),application_id))
        self.db.execute('INSERT INTO ewu2_recruitment_events VALUES(?,?,?,?,?,?)',(self.uid(),application_id,row['status'],target,str(actor.id),self.now()))
        event=self.audit('application.'+target.lower(),actor,application_id)
        self.enqueue('sheets',application_id,'status-event:'+event)
        if target=='SUBMITTED_TO_PARTNER':
            self.enqueue('partner',application_id,'partner-submit:'+application_id)
        if target=='START_DATE_CONFIRMED':
            self.enqueue('notification',application_id,'travel-instructions:'+application_id,{'template':'travel_instructions'})
        if target=='ARRIVED':
            self.enqueue('operator',application_id,'arrival:'+application_id)
        if target=='REJECTED':
            self.enqueue('operator',application_id,'alternatives-review:'+application_id)
        return self.application(actor,application_id)

    @atomic
    def follow_up(self, actor, application_id, due_at, max_attempts=2, interval_hours=24):
        self.application(actor,application_id)
        self.role(actor,'owner','recruiter')
        if type(max_attempts) is not int or not 1<=max_attempts<=3 or type(interval_hours) is not int or interval_hours<12:
            raise Denied('Reminder frequency limit')
        due = datetime.fromisoformat(due_at)
        if due.tzinfo is None:
            raise Denied('Timezone required')
        existing=self.db.one("SELECT id FROM ewu2_followups WHERE application_id=? AND status='pending'",(application_id,))
        if existing:return existing['id']
        identifier = self.uid()
        self.db.execute('INSERT INTO ewu2_followups(id,application_id,due_at,attempts,max_attempts,interval_hours,status) VALUES(?,?,?,?,?,?,?)',(identifier,application_id,due.astimezone(timezone.utc).isoformat(),0,max_attempts,interval_hours,'pending'))
        event=self.audit('followup.created',actor,identifier)
        self.enqueue('sheets',application_id,'followup-event:'+event)
        return identifier

    @atomic
    def due_followups(self):
        jobs = self.db.all("SELECT * FROM ewu2_followups WHERE status='pending' AND due_at<=?",(self.now(),))
        for job in jobs:
            if job['application_id'] is None:
                candidate=self.db.one('SELECT * FROM ewu2_candidates WHERE id=?',(job['candidate_id'],))
                preference=self.db.one('SELECT allowed FROM ewu2_notification_preferences WHERE user_id=?',(candidate['telegram_id'],))
                if candidate['status']=='PROFILE_COMPLETE' or not self.allowed(candidate['telegram_id']) or self.policy.get('notifications_approved') is not True or (preference and not preference['allowed']):
                    self.db.execute("UPDATE ewu2_followups SET status='cancelled' WHERE id=?",(job['id'],))
                elif job['attempts']>=job['max_attempts']:
                    self.db.execute("UPDATE ewu2_followups SET status='exhausted' WHERE id=?",(job['id'],))
                    self.db.execute("UPDATE ewu2_candidates SET status='ON_HOLD' WHERE id=?",(candidate['id'],))
                    event=self.audit('candidate.no_response',Actor('system'),candidate['id'])
                    self.enqueue('sheets',candidate['id'],'candidate-no-response:'+event)
                    self.enqueue('operator',candidate['id'],'incomplete:'+job['id'])
                else:
                    next_due=(self.clock()+timedelta(hours=job['interval_hours'])).isoformat()
                    self.enqueue('notification',candidate['id'],f"profile-reminder:{job['id']}:{job['attempts']}",{'template':'profile_reminder'})
                    self.db.execute('UPDATE ewu2_followups SET attempts=attempts+1,due_at=? WHERE id=?',(next_due,job['id']))
                continue
            row = self.db.one('SELECT * FROM ewu2_applications WHERE id=?',(job['application_id'],))
            candidate = self.db.one('SELECT * FROM ewu2_candidates WHERE id=?',(row['candidate_id'],))
            preference=self.db.one('SELECT allowed FROM ewu2_notification_preferences WHERE user_id=?',(candidate['telegram_id'],))
            if self.policy.get('notifications_approved') is not True or (preference and not preference['allowed']) or not self.allowed(candidate['telegram_id']) or row['status'] in ('STARTED_WORK','REJECTED','CANCELLED'):
                self.db.execute("UPDATE ewu2_followups SET status='cancelled' WHERE id=?",(job['id'],))
                continue
            if job['attempts']>=job['max_attempts']:
                self.transition(Actor('system-recruiter'),row['id'],'ON_HOLD')
                self.db.execute("UPDATE ewu2_followups SET status='exhausted' WHERE id=?",(job['id'],))
                self.enqueue('operator',row['id'],'no-response:'+job['id'])
            else:
                next_due = (self.clock()+timedelta(hours=job['interval_hours'])).astimezone(timezone.utc).isoformat()
                self.enqueue('notification',row['id'],f"followup:{job['id']}:{job['attempts']}",{'template':'follow_up'})
                self.db.execute('UPDATE ewu2_followups SET attempts=attempts+1,due_at=? WHERE id=?',(next_due,job['id']))
        for job in jobs:
            event=self.audit('followup.checked',Actor('system'),job['id'])
            self.enqueue('sheets',job['application_id'] or job['candidate_id'],'followup-checked:'+event)
        return len(jobs)

    @atomic
    def commission(self, actor, application_id, model, rate_minor, units, currency, contract_ref, period):
        self.role(actor,'owner','finance')
        row = self.db.one('SELECT * FROM ewu2_applications WHERE id=?',(application_id,))
        if row is None or not self.db.one('SELECT * FROM ewu2_employment_starts WHERE application_id=?',(application_id,)):
            raise Denied('Confirmed employment required')
        if model not in ('one_time','hourly') or type(rate_minor) is not int or rate_minor<=0 or type(units) is not int or units<=0 or (model=='one_time' and units!=1):
            raise Denied('Approved commission terms required')
        if len(currency)!=3 or not currency.isupper() or not contract_ref.strip() or not period.strip():
            raise Denied('Contract, currency and period required')
        existing = self.db.one('SELECT * FROM ewu2_commissions WHERE application_id=?',(application_id,))
        terms = (model,rate_minor,units,currency,contract_ref,period)
        if existing:
            if terms!=tuple(existing[k] for k in ('model','rate_minor','units','currency','contract_ref','period')):
                raise Denied('Existing commission terms conflict')
            return existing['id']
        identifier = self.uid()
        self.db.execute('INSERT INTO ewu2_commissions(id,application_id,partner_id,candidate_id,model,rate_minor,units,currency,amount_minor,contract_ref,period,verification) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                        (identifier,application_id,row['partner_id'],row['candidate_id'],model,rate_minor,units,currency,rate_minor*units,contract_ref,period,'REQUIRES_REVIEW'))
        self.audit('commission.calculated',actor,identifier)
        self.enqueue('sheets_finance',identifier,'commission:'+identifier)
        return identifier

    @atomic
    def quality(self, actor, application_id, report):
        row = self.application(actor,application_id)
        candidate = self.candidate(actor.id)
        if not candidate or candidate['id']!=row['candidate_id'] or row['status']!='STARTED_WORK':
            raise Denied('Confirmed employment required')
        if set(report)-{'conditions_match','rate_match','housing_match','needs_help'} or not all(type(v) is bool for v in report.values()):
            raise Denied('Structured quality answers only')
        identifier = self.uid()
        self.db.execute('INSERT INTO ewu2_quality_reports VALUES(?,?,?,?)',(identifier,application_id,encoded(report),self.now()))
        self.audit('quality.operator_review',actor,identifier)
        self.enqueue('operator',identifier,'quality:'+identifier)
        return identifier

    def dashboard(self, actor):
        self.role(actor,'owner','recruiter','finance')
        statuses = {s:0 for s in STATUSES}
        for row in self.db.all('SELECT status,count(*) AS total FROM ewu2_applications GROUP BY status'):
            statuses[row['status']] = row['total']
        result = {'candidates':self.db.one('SELECT count(*) AS n FROM ewu2_candidates')['n'],
                  'applications':sum(statuses.values()),'statuses':statuses,
                  'confirmed_starts':self.db.one('SELECT count(*) AS n FROM ewu2_employment_starts')['n'],
                  'overdue_followups':self.db.one("SELECT count(*) AS n FROM ewu2_followups WHERE status='pending' AND due_at<?",(self.now(),))['n'],
                  'transitions':self.db.all('SELECT from_status,to_status,count(*) AS total FROM ewu2_recruitment_events GROUP BY from_status,to_status')}
        result['stage_counts']={r['to_status']:r['n'] for r in self.db.all('SELECT to_status,count(DISTINCT application_id) AS n FROM ewu2_recruitment_events GROUP BY to_status')}
        result['stage_counts']['NEW']=result['applications']
        result['conversions']={a+'>'+b:(result['stage_counts'].get(b,0)/result['stage_counts'][a] if result['stage_counts'].get(a,0) else 0) for a,b in zip(STATUSES[:14],STATUSES[1:15])}
        result['partner_performance']=self.db.all("SELECT a.partner_id,count(*) AS applications,count(s.application_id) AS starts FROM ewu2_applications a LEFT JOIN ewu2_employment_starts s ON s.application_id=a.id GROUP BY a.partner_id")
        result['ai_errors']=self.db.one("SELECT count(*) AS n FROM ewu2_ai_usage WHERE status='error'")['n']
        result['active_dialogues']=self.db.one('SELECT count(*) AS n FROM ewu2_sessions')['n']
        role = self.role(actor,'owner','recruiter','finance')
        if role['role'] in ('owner','finance'):
            result['commissions'] = self.db.all('SELECT currency,payment_status,sum(amount_minor) AS amount_minor FROM ewu2_commissions GROUP BY currency,payment_status')
            result['ai_spent_minor'] = self.db.one('SELECT coalesce(sum(spent_minor),0) AS n FROM ewu2_ai_usage')['n']
        return result

    @atomic
    def ai_switch(self, actor, enabled):
        self.role(actor,'owner')
        if type(enabled) is not bool:
            raise Denied('Boolean required')
        self.db.execute('UPDATE ewu2_settings SET value=? WHERE key=?',('true' if enabled else 'false','ai_enabled'))
        self.audit('ai.enabled' if enabled else 'ai.disabled',actor,'ai')

    @atomic
    def process_update(self, update_id, handler):
        if self.db.one('SELECT update_id FROM ewu2_processed_updates WHERE update_id=?',(str(update_id),)):
            return None
        result = handler()
        self.db.execute('INSERT INTO ewu2_processed_updates VALUES(?,?)',(str(update_id),self.now()))
        return result


    @atomic
    def notification_preference(self, actor, enabled):
        if type(enabled) is not bool:
            raise Denied('Boolean required')
        self.db.execute('INSERT INTO ewu2_notification_preferences VALUES(?,?) ON CONFLICT(user_id) DO UPDATE SET allowed=excluded.allowed',(str(actor.id),int(enabled)))
        self.audit('notifications.preference',actor,str(actor.id))


    @atomic
    def assign_recruiter(self, actor, candidate_id, recruiter_id):
        self.role(actor,'owner')
        self.role(Actor(str(recruiter_id)),'owner','recruiter')
        if not self.db.one('SELECT id FROM ewu2_candidates WHERE id=?',(candidate_id,)):
            raise Denied('Candidate unavailable')
        self.db.execute('UPDATE ewu2_candidates SET recruiter_id=? WHERE id=?',(str(recruiter_id),candidate_id))
        self.audit('candidate.assigned',actor,candidate_id)
        self.enqueue('sheets',candidate_id,'assignment:'+candidate_id+':'+self.now())

    @atomic
    def invoice(self, actor, commission_id, invoice_date, due_date):
        from datetime import date
        self.role(actor,'owner','finance')
        if date.fromisoformat(due_date)<date.fromisoformat(invoice_date):
            raise Denied('Invalid invoice dates')
        if not self.db.one('SELECT id FROM ewu2_commissions WHERE id=?',(commission_id,)):
            raise Denied('Commission unavailable')
        self.db.execute("UPDATE ewu2_commissions SET verification='VERIFIED',invoice_date=?,due_date=? WHERE id=?",(invoice_date,due_date,commission_id))
        self.audit('commission.invoiced',actor,commission_id)
        self.enqueue('sheets_finance',commission_id,'invoice:'+commission_id)

    @atomic
    def record_payment(self, actor, commission_id, verified_reference):
        self.role(actor,'owner','finance')
        row=self.db.one('SELECT * FROM ewu2_commissions WHERE id=?',(commission_id,))
        if not row or row['verification']!='VERIFIED' or not verified_reference.strip():
            raise Denied('Verified invoice and payment evidence required')
        if row['payment_status']=='PAID':return
        # The finance operator supplies an independently verified evidence reference.
        # This records an attestation; it does not query a bank or prove receipt itself.
        self.db.execute("UPDATE ewu2_commissions SET payment_status='PAID' WHERE id=?",(commission_id,))
        self.audit('commission.payment_attested',actor,commission_id)
        self.enqueue('sheets_finance',commission_id,'payment:'+commission_id)


    def verify_audit(self, actor):
        self.role(actor,'owner')
        rows=self.db.all('SELECT * FROM ewu2_audit_events')
        by_previous={}
        for row in rows:
            digest=row.pop('event_hash')
            if hashlib.sha256(encoded(row).encode()).hexdigest()!=digest or row['previous_hash'] in by_previous:
                return False
            by_previous[row['previous_hash']]=digest
        current=''
        for _ in rows:
            if current not in by_previous:return False
            current=by_previous[current]
        if current!=self.db.one('SELECT value FROM ewu2_audit_head WHERE singleton=1')['value']:return False
        keys=('id','user_id','version','revision','language','event','decision','source','notice','at','previous_hash')
        linked={r['entity_id'].rsplit(':',1)[-1] for r in self.db.all('SELECT entity_id FROM ewu2_audit_events')}
        for row in self.db.all('SELECT * FROM ewu2_privacy_records'):
            if row['event_hash'] not in linked or hashlib.sha256(encoded([row[k] for k in keys]).encode()).hexdigest()!=row['event_hash']:return False
        return True

    def retention_plan(self, actor):
        self.role(actor,'owner')
        # Legal hold/finance/evidence deletion requires a separately approved disposition;
        # this planner does not silently remove evidence or production data.
        cutoff=(self.clock()-timedelta(days=self.policy['application_retention_days'])).isoformat()
        return {'expired_candidate_ids':[r['id'] for r in self.db.all('SELECT id FROM ewu2_candidates WHERE updated_at<?',(cutoff,))],
                'automatic_erasure_enabled':False,'operator_legal_review_required':True}


    @atomic
    def begin_profile(self, actor, lang):
        candidate_id=self.register(actor,lang,{})
        candidate=self.candidate(actor.id)
        if candidate['status']!='PROFILE_COMPLETE' and not self.db.one("SELECT id FROM ewu2_followups WHERE candidate_id=? AND application_id IS NULL AND status='pending'",(candidate_id,)):
            due=(self.clock()+timedelta(hours=24)).isoformat()
            self.db.execute("INSERT INTO ewu2_followups(id,application_id,due_at,attempts,max_attempts,interval_hours,status,candidate_id,template) VALUES(?,NULL,?,0,2,24,'pending',?,'profile_reminder')",(self.uid(),due,candidate_id))
        return candidate_id


    def alternatives(self, actor, application_id):
        row=self.application(actor,application_id)
        candidate=self.candidate(actor.id)
        if candidate is None or candidate['id']!=row['candidate_id']:
            raise Denied('Candidate self-service required')
        previous={r['vacancy_id'] for r in self.db.all('SELECT vacancy_id FROM ewu2_applications WHERE candidate_id=?',(candidate['id'],))}
        return [v for v in self.matches(actor) if v['id'] not in previous]
