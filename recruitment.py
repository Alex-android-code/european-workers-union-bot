"""EWU candidate journey and durable CRM outbox over the existing privacy DB.
No model calls, hiring decisions, automatic external messages or network here.
"""
import json
import re
import uuid
from datetime import datetime
from privacy.onboarding import revision

NEXT = {
 'NEW': {'FORM_COMPLETED','CONTACTED', 'CLOSED', 'WITHDRAWN','REJECTED'},
 'FORM_COMPLETED': {'UNDER_REVIEW','CONTACTED','REJECTED','WITHDRAWN'},
 'UNDER_REVIEW': {'APPROVED','REJECTED','WITHDRAWN'},
 'APPROVED': {'DEPARTURE_CONFIRMED','REJECTED','WITHDRAWN'},
 'DEPARTURE_CONFIRMED': {'ARRIVED','NO_SHOW','WITHDRAWN'},
 'CONTACTED': {'OFFERED', 'CLOSED', 'WITHDRAWN'},
 'OFFERED': {'CONFIRMED', 'CLOSED', 'WITHDRAWN'},
 'CONFIRMED': {'TRAVEL_PLANNED', 'CLOSED', 'WITHDRAWN'},
 'TRAVEL_PLANNED': {'ARRIVED', 'CLOSED', 'WITHDRAWN'},
 'ARRIVED': {'STARTED', 'CLOSED', 'WITHDRAWN','DID_NOT_START'},
 'STARTED': {'CLOSED', 'WITHDRAWN','FINISHED'}, 'CLOSED': set(), 'WITHDRAWN': set(),
 'REJECTED':set(),'NO_SHOW':set(),'DID_NOT_START':set(),'FINISHED':set(),
}


class Journey:
 def __init__(self, store, admin_ids=()):
  self.store=store; self.db=store.db; self.admins={str(i) for i in admin_ids}
  self.db.executescript('''
  CREATE TABLE IF NOT EXISTS candidate_journey(
    application_id TEXT PRIMARY KEY REFERENCES applications(id),
    status TEXT NOT NULL DEFAULT 'NEW', revision INTEGER NOT NULL DEFAULT 1,
    policy_revision TEXT NOT NULL, locale TEXT NOT NULL, plan TEXT, updated_at TEXT NOT NULL);
  CREATE TABLE IF NOT EXISTS journey_events(
    id INTEGER PRIMARY KEY,application_id TEXT NOT NULL, status TEXT NOT NULL,
    revision INTEGER NOT NULL,actor TEXT NOT NULL,at TEXT NOT NULL);
  CREATE TABLE IF NOT EXISTS crm_outbox(
    id TEXT PRIMARY KEY,application_id TEXT NOT NULL,revision INTEGER NOT NULL,
    kind TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'pending',attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT, UNIQUE(application_id,revision,kind));
  CREATE TABLE IF NOT EXISTS crm_commands(
    id TEXT PRIMARY KEY,digest TEXT NOT NULL,result TEXT NOT NULL,at TEXT NOT NULL);
  CREATE TABLE IF NOT EXISTS notifications(
    id TEXT PRIMARY KEY,application_id TEXT NOT NULL,user_id INTEGER NOT NULL,
    status TEXT NOT NULL,locale TEXT NOT NULL,revision INTEGER NOT NULL,
    state TEXT NOT NULL DEFAULT 'pending',at TEXT NOT NULL,
    UNIQUE(application_id,revision));
  ''')

 def _now(self): return self.store.clock().isoformat()
 def _queue(self, aid, number, kind='upsert'):
  self.db.execute('INSERT OR IGNORE INTO crm_outbox(id,application_id,revision,kind) VALUES(?,?,?,?)',
                  (str(uuid.uuid4()),aid,number,kind))
 def _admin(self,actor):
  if str(actor) not in self.admins: raise PermissionError('Coordinator access denied')
 def _row(self,aid,user_id=None):
  row=self.db.execute('''SELECT a.id,a.user_id,a.kind,a.data,a.at,j.status,j.revision,j.policy_revision,j.locale,j.plan
    FROM applications a JOIN candidate_journey j ON j.application_id=a.id WHERE a.id=?''',(aid,)).fetchone()
  if row is None or (user_id is not None and row[1]!=user_id):raise PermissionError('Application unavailable')
  keys=('id','user_id','kind','data','at','status','revision','policy_revision','locale','plan')
  return dict(zip(keys,row))

 def register(self,aid,locale):
  row=self.db.execute('SELECT user_id FROM applications WHERE id=?',(aid,)).fetchone()
  if row is None or not self.store.allowed(row[0]):raise PermissionError('Current onboarding required')
  with self.db:
   exists=self.db.execute('SELECT 1 FROM candidate_journey WHERE application_id=?',(aid,)).fetchone()
   if exists:return
   self.db.execute('INSERT INTO candidate_journey(application_id,policy_revision,locale,updated_at) VALUES(?,?,?,?)',
                   (aid,revision(self.store.policy),locale,self._now()))
   self.db.execute('INSERT INTO journey_events(application_id,status,revision,actor,at) VALUES(?,?,?,?,?)',
                   (aid,'NEW',1,'candidate',self._now()))
   self._queue(aid,1)

 def own(self,user_id):
  ids=self.db.execute('SELECT application_id FROM candidate_journey j JOIN applications a ON a.id=j.application_id WHERE a.user_id=? ORDER BY a.at DESC LIMIT 20',(user_id,)).fetchall()
  return [dict(id=r['id'],status=r['status'],revision=r['revision'],created_at=r['at']) for (aid,) in ids for r in [self._row(aid,user_id)]]

 def transition(self,actor,aid,status,expected_revision,source='telegram',command_id=None,digest=None):
  self._admin(actor)
  if type(expected_revision) is not int:raise ValueError('Revision must be an integer')
  row=self._row(aid)
  if not self.store.allowed(row['user_id']) or row['policy_revision']!=revision(self.store.policy):
   raise PermissionError('Processing paused or privacy notice changed')
  if row['revision']!=expected_revision:raise ValueError('Stale candidate revision')
  if self.db.execute('SELECT 1 FROM external_erasure_holds WHERE application_id=? AND status="pending"',(aid,)).fetchone():raise PermissionError('External erasure pending')
  if status not in NEXT[row['status']]:raise ValueError('Invalid status transition')
  if status in ('TRAVEL_PLANNED','DEPARTURE_CONFIRMED') and not row['plan']:raise ValueError('Approved arrival plan required')
  with self.db:
   changed=self.db.execute('UPDATE candidate_journey SET status=?,revision=revision+1,updated_at=? WHERE application_id=? AND revision=?',
                          (status,self._now(),aid,expected_revision))
   if changed.rowcount!=1:raise ValueError('Concurrent candidate update')
   number=expected_revision+1
   self.db.execute('INSERT INTO journey_events(application_id,status,revision,actor,at) VALUES(?,?,?,?,?)',(aid,status,number,source+':'+str(actor),self._now()))
   self._queue(aid,number)
   if command_id is not None:
    result=json.dumps(dict(id=aid,status=status,revision=number),sort_keys=True)
    self.db.execute('INSERT INTO crm_commands VALUES(?,?,?,?)',(command_id,digest,result,self._now()))
    self.db.execute('INSERT OR IGNORE INTO notifications(id,application_id,user_id,status,locale,revision,at) VALUES(?,?,?,?,?,?,?)',
                    (command_id,aid,row['user_id'],status,row['locale'],number,self._now()))
  return dict(id=aid,status=status,revision=number)

 def set_plan(self,actor,aid,plan,expected_revision):
  self._admin(actor)
  if not isinstance(plan,dict) or set(plan)!={'workplace','address','arrival_at','contact','transport'}:raise ValueError('Invalid arrival plan')
  if any(not isinstance(v,str) or not v.strip() or len(v)>500 for v in plan.values()):raise ValueError('Invalid plan value')
  when=datetime.fromisoformat(plan['arrival_at'])
  if when.tzinfo is None or when.utcoffset() is None or when<=self.store.clock():raise ValueError('Future arrival with timezone required')
  row=self._row(aid)
  if row['status'] not in ('CONFIRMED','APPROVED') or row['revision']!=expected_revision:raise ValueError('Approved current application required')
  if not self.store.allowed(row['user_id']) or row['policy_revision']!=revision(self.store.policy):raise PermissionError('Processing paused')
  with self.db:
   changed=self.db.execute('UPDATE candidate_journey SET plan=?,revision=revision+1,updated_at=? WHERE application_id=? AND revision=?',
                          (json.dumps(plan,ensure_ascii=False),self._now(),aid,expected_revision))
   if changed.rowcount!=1:raise ValueError('Concurrent candidate update')
   self._queue(aid,expected_revision+1)
  return dict(id=aid,revision=expected_revision+1)

 def arrival(self,user_id,aid):
  row=self._row(aid,user_id)
  if not self.store.allowed(user_id) or row['policy_revision']!=revision(self.store.policy):raise PermissionError('Processing paused')
  if row['status'] not in ('TRAVEL_PLANNED','DEPARTURE_CONFIRMED','ARRIVED','STARTED') or not row['plan']:return None
  plan=json.loads(row['plan'])
  if datetime.fromisoformat(plan['arrival_at'])<self.store.clock():return None
  return plan

 def export_own(self,user_id):
  # Available to the data subject after withdrawal too; never another user.
  identity=self.db.execute('SELECT candidate_id FROM candidate_identity WHERE user_id=?',(user_id,)).fetchone()
  return dict(candidate_id=identity[0] if identity else None,applications=[dict(id=r[0],kind=r[1],data=json.loads(r[2]),created_at=r[3]) for r in self.db.execute(
    'SELECT id,kind,data,at FROM applications WHERE user_id=?',(user_id,))],
    privacy_events=[dict(action=r[0],version=r[1],locale=r[2],at=r[3]) for r in self.db.execute(
    'SELECT action,version,locale,at FROM privacy_events WHERE user_id=? ORDER BY id',(user_id,))],
    requests=[dict(id=r[0],kind=r[1],status=r[2],at=r[3]) for r in self.db.execute('SELECT id,kind,status,at FROM data_requests WHERE user_id=?',(user_id,))])

 def pause(self,user_id):
  with self.db:
   self.db.execute("UPDATE crm_outbox SET status='suppressed',last_error='processing_paused' WHERE application_id IN (SELECT id FROM applications WHERE user_id=?) AND status='pending'",(user_id,))
  # Already-sent external copies require the rights-request runbook, not a false deletion promise.

 def cleanup(self):
  self.store.purge()
  with self.db:
   self.db.execute('DELETE FROM candidate_journey WHERE application_id NOT IN (SELECT id FROM applications)')
   self.db.execute('DELETE FROM journey_events WHERE application_id NOT IN (SELECT id FROM applications)')
   self.db.execute('DELETE FROM crm_outbox WHERE application_id NOT IN (SELECT id FROM applications)')
   self.db.execute('DELETE FROM notifications WHERE application_id NOT IN (SELECT id FROM applications)')

 def crm_batch(self,limit=10):
  if type(limit) is not int or not 1<=limit<=50:raise ValueError('Invalid batch size')
  self.cleanup();result=[]
  rows=self.db.execute("SELECT id,application_id,revision FROM crm_outbox WHERE status='pending' ORDER BY rowid LIMIT ?",(limit,)).fetchall()
  for event_id,aid,number in rows:
   row=self._row(aid)
   held=self.db.execute('SELECT 1 FROM external_erasure_holds WHERE application_id=? AND status="pending"',(aid,)).fetchone()
   if (not self.store.allowed(row['user_id']) or row['policy_revision']!=revision(self.store.policy)
       or number!=row['revision'] or held):
    with self.db:self.db.execute("UPDATE crm_outbox SET status='suppressed',last_error='stale_or_paused' WHERE id=?",(event_id,))
    continue
   data=json.loads(row['data'])
   # No Telegram ID, documents, AI score, message history, photos or raw form dump.
   payload=dict(event_id=event_id,application_id=aid,revision=number,kind=row['kind'],status=row['status'],
    name=data.get('name',data.get('company','')),phone=data.get('phone',''),
    city=data.get('city',data.get('location',data.get('country',''))),profession=data.get('profession',''),
    created_at=row['at'],policy_revision=row['policy_revision'],future_recruitment_consent=False)
   result.append(payload)
  return result
