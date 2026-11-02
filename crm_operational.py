"""Nine-tab operational projection; gated independently from legacy v2 export."""
import json

from crm_commands import exchange
from crm_sync import config
from privacy.onboarding import revision
from recruitment import Journey
from statuses import LEGACY


def projection(journey,item):
    store=journey.store;row=journey._row(item['application_id']);data=json.loads(row['data'])
    identity=store.db.execute('SELECT candidate_id FROM candidate_identity WHERE user_id=?',(row['user_id'],)).fetchone()
    if not identity:raise ValueError('Candidate identity migration required')
    cid=identity[0];aid=row['id'];now=store.db.execute('SELECT updated_at FROM candidate_journey WHERE application_id=?',(aid,)).fetchone()[0]
    version=store.policy['version'];status=LEGACY.get(row['status'],row['status'])
    candidate=[cid,str(row['user_id']),'',data.get('name',data.get('company','')),'',data.get('phone',''),row['locale'],'',data.get('city',data.get('location','')),data.get('profession',''),'','',status,'',row['at'],now,version,'acknowledged','SQLite only',row['revision']]
    application=[aid,cid,'',status,row['at'],now,row['revision']]
    history=[[aid+':'+str(r[2]),aid,cid,'',LEGACY.get(r[0],r[0]),r[1],str(r[3]).split(':')[0],str(r[3]),r[2]] for r in store.db.execute('SELECT status,at,revision,actor FROM journey_events WHERE application_id=? ORDER BY id',(aid,))]
    privacy=[[cid+':privacy:'+str(r[0]),cid,str(row['user_id']),r[1],r[2],r[3],r[4] if r[5]=='presented' else '',r[5],r[4],'recruitment_notice',store.policy['core_legal_basis']] for r in store.db.execute('SELECT id,version,revision,locale,at,action FROM privacy_events WHERE user_id=? ORDER BY id',(row['user_id'],))]
    requests=[[r[0],cid,r[1],r[2],r[3],'','','pending','',''] for r in store.db.execute('SELECT id,kind,at,status FROM data_requests WHERE user_id=? ORDER BY at',(row['user_id'],))]
    payload=dict(event_id=item['event_id'],application_id=aid,revision=row['revision'],candidate=candidate,application=application,history=history,privacy=privacy,requests=requests)
    if len(json.dumps(payload,ensure_ascii=False).encode())>40000:raise ValueError('Projection requires paginated reconciliation')
    return payload


def flush_operational(store,environment,transport=None):
    if environment.get('CRM_OPERATIONAL_ENABLED')!='1':return dict(enabled=False,sent=0,failed=0)
    cfg=config(environment)
    if cfg is None:raise ValueError('Reviewed CRM configuration required')
    journey=Journey(store);sent=failed=0
    for item in journey.crm_batch():
        store.db.execute('BEGIN IMMEDIATE')
        try:
            row=journey._row(item['application_id'])
            event=store.db.execute('SELECT status FROM crm_outbox WHERE id=?',(item['event_id'],)).fetchone()
            ack=store.db.execute("SELECT action,revision FROM privacy_events WHERE user_id=? AND action!='presented' ORDER BY id DESC LIMIT 1",(row['user_id'],)).fetchone()
            pending=store.db.execute('SELECT 1 FROM deletion_requests WHERE user_id=? AND status="pending"',(row['user_id'],)).fetchone()
            if not event or event[0]!='pending' or pending or ack!=('acknowledged',revision(store.policy)) or row['revision']!=item['revision']:
                store.db.execute("UPDATE crm_outbox SET status='suppressed',last_error='stale_or_paused' WHERE id=?",(item['event_id'],))
            else:
                try:
                    payload=projection(journey,item)
                    receipt=exchange(cfg,'sync_operational',payload,transport)
                    if receipt!=dict(application_id=item['application_id'],revision=item['revision'],ok=True):raise ValueError('Projection receipt mismatch')
                    store.db.execute("UPDATE crm_outbox SET status='sent',attempts=attempts+1,last_error=NULL WHERE id=?",(item['event_id'],));sent+=1
                except Exception:
                    store.db.execute("UPDATE crm_outbox SET attempts=attempts+1,status=CASE WHEN attempts>=4 THEN 'held' ELSE 'pending' END,last_error='operational_delivery_unconfirmed' WHERE id=?",(item['event_id'],));failed+=1
            store.db.commit()
        except BaseException:store.db.rollback();raise
    return dict(enabled=True,sent=sent,failed=failed)
