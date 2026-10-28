"""Leased transactional outbox; topic adapters must be idempotent or reconcile outcomes."""
from datetime import timedelta
import json

from .domain import Actor, Denied
from .sheets import projection


class UncertainDelivery(RuntimeError):
    pass


class Worker:
    def __init__(self,service,handlers,max_attempts=5):
        self.service,self.handlers,self.max_attempts=service,handlers,max_attempts

    def run_one(self):
        s=self.service
        with s.db.transaction():
            if not self.handlers:return False
            placeholders=','.join('?' for _ in self.handlers)
            job=s.db.one("SELECT * FROM ewu2_outbox WHERE topic IN ("+placeholders+") AND available_at<=? AND (status='pending' OR (status='leased' AND lease_until<=?)) ORDER BY available_at,id LIMIT 1",(*self.handlers,s.now(),s.now()))
            if not job:return False
            lease=(s.clock()+timedelta(minutes=5)).isoformat()
            s.db.execute("UPDATE ewu2_outbox SET status='leased',lease_until=?,attempts=attempts+1 WHERE id=?",(lease,job['id']))
        try:
            handler=self.handlers[job['topic']]
            handler(job['entity_id'],json.loads(job['payload']),job['dedupe_key'])
        except UncertainDelivery:
            with s.db.transaction():
                s.db.execute("UPDATE ewu2_outbox SET status='uncertain',last_error='delivery_uncertain' WHERE id=? AND lease_until=?",(job['id'],lease))
                s.audit('delivery.uncertain',Actor('system'),job['id'])
        except Exception:
            with s.db.transaction():
                final=job['attempts']+1>=self.max_attempts
                delay=(s.clock()+timedelta(seconds=min(3600,30*2**job['attempts'])+int(job['id'].replace('-','')[:4],16)%7)).isoformat()
                s.db.execute('UPDATE ewu2_outbox SET status=?,available_at=?,last_error=? WHERE id=? AND lease_until=?',('dead' if final else 'pending',delay,'adapter_failed',job['id'],lease))
                if final:s.audit('outbox.dead',Actor('system'),job['id'])
        else:
            with s.db.transaction():
                s.db.execute("UPDATE ewu2_outbox SET status='done',lease_until=NULL,last_error=NULL WHERE id=? AND lease_until=?",(job['id'],lease))
        return True


class SheetsSync:
    def __init__(self,service,sink,actor,selected_candidate_id=None):
        self.service,self.sink,self.actor,self.selected=service,sink,actor,selected_candidate_id
    def __call__(self,entity,payload,key):
        with self.service.db.transaction():
            self.service.legal()
            if self.service.policy.get('sheets_approved') is not True:raise Denied('Sheets processing approval required')
            snapshot=projection(self.service,self.actor,self.selected)
            self.sink.replace(snapshot)


class MemoryDelivery:
    def __init__(self):self.items={}
    def __call__(self,entity,payload,key):self.items.setdefault(key,(entity,payload))


class NotificationDelivery:
    def __init__(self,service,transport):self.service,self.transport=service,transport
    def __call__(self,entity,payload,key):
        s=self.service
        row=s.db.one('SELECT * FROM ewu2_applications WHERE id=?',(entity,))
        if payload.get('template')=='profile_reminder':
            candidate=s.db.one('SELECT * FROM ewu2_candidates WHERE id=?',(entity,))
            if candidate is None or candidate['status']=='PROFILE_COMPLETE':return
        else:
            if row is None:raise Denied('Application unavailable')
            candidate=s.db.one('SELECT * FROM ewu2_candidates WHERE id=?',(row['candidate_id'],))
        if not s.allowed(candidate['telegram_id']):return
        preference=s.db.one('SELECT allowed FROM ewu2_notification_preferences WHERE user_id=?',(candidate['telegram_id'],))
        if s.policy.get('notifications_approved') is not True or (preference and not preference['allowed']):return
        if payload.get('template')=='profile_reminder':
            text='EWU: /profile /stop_reminders'
        elif payload.get('template')=='travel_instructions':
            details=json.loads(row['instructions'])
            if not details:raise Denied('Verified instructions required')
            text='\n'.join(k+': '+v for k,v in details.items())
        elif payload.get('template')=='follow_up':
            if row['status'] in ('CANCELLED','REJECTED','STARTED_WORK'):return
            text='EWU: /profile /vacancies /stop_reminders — '+row['id']
        else:raise Denied('Unknown template')
        with s.db.transaction():
            if s.db.one('SELECT dedupe_key FROM ewu2_deliveries WHERE dedupe_key=?',(key,)):
                raise UncertainDelivery('Delivery requires reconciliation')
            s.db.execute('INSERT INTO ewu2_deliveries VALUES(?,?,?,NULL)',(key,'attempted',s.now()))
        try:
            self.transport.send(candidate['telegram_id'],text,idempotency_key=key)
        except Exception:
            raise UncertainDelivery('Delivery outcome uncertain') from None
        with s.db.transaction():
            s.db.execute("UPDATE ewu2_deliveries SET status='completed',completed_at=? WHERE dedupe_key=?",(s.now(),key))


class PartnerDelivery:
    def __init__(self,service,transport):self.service,self.transport=service,transport
    def __call__(self,entity,payload,key):
        s=self.service
        row=s.db.one('SELECT * FROM ewu2_applications WHERE id=?',(entity,))
        if row is None or row['status'] not in ('SUBMITTED_TO_PARTNER','PARTNER_REVIEW'):
            return
        c=s.db.one('SELECT * FROM ewu2_candidates WHERE id=?',(row['candidate_id'],))
        if s.policy.get('partner_transfer_approved') is not True or not s.allowed(c['telegram_id']):return
        p=json.loads(c['profile'])
        permitted={'candidate_id':c['id'],'profession':p.get('profession',''),'city':p.get('city','')}
        if not getattr(self.transport,'supports_idempotency',False):raise Denied('Verified idempotent partner adapter required')
        self.transport.submit(row['partner_id'],{'application_id':row['id'],'vacancy_id':row['vacancy_id'],'candidate':permitted},idempotency_key=key)
