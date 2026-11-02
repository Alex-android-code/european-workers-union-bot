"""Authenticated, replay-safe Sheets status commands and at-most-once notifications.

Disabled independently from the outbound v2 bridge. The Apps Script command
extension must be installed and verified before CRM_BIDIRECTIONAL_ENABLED=1.
"""
import hashlib
import hmac
import json
import time
import uuid
from urllib.request import Request, build_opener

from crm_sync import config, GoogleResponseRedirect
from privacy.onboarding import revision
from recruitment import Journey
from statuses import label


def exchange(cfg,operation,body=None,transport=None,clock=time.time):
    request_id=str(uuid.uuid4())
    payload=dict(operation=operation,request_id=request_id,**(body or {}))
    raw=json.dumps(payload,sort_keys=True,separators=(',',':'),ensure_ascii=False)
    timestamp=str(int(clock()))
    envelope=dict(timestamp=timestamp,payload=raw,signature=hmac.new(cfg['secret'].encode(),(timestamp+'.'+raw).encode(),hashlib.sha256).hexdigest())
    request=Request(cfg['url'],data=json.dumps(envelope).encode(),headers={'Content-Type':'application/json'},method='POST')
    sender=transport or build_opener(GoogleResponseRedirect()).open
    with sender(request,timeout=10) as response:data=response.read(65537)
    if len(data)>65536:raise ValueError('Response exceeds limit')
    response=json.loads(data)
    if set(response)!={'request_id','sheet_id','result','signature'}:raise ValueError('Invalid command receipt')
    if response['request_id']!=request_id or response['sheet_id']!=cfg['sheet_id']:raise ValueError('Command receipt mismatch')
    signature=response.pop('signature')
    canonical=json.dumps(response,sort_keys=True,separators=(',',':'),ensure_ascii=False)
    expected=hmac.new(cfg['secret'].encode(),canonical.encode(),hashlib.sha256).hexdigest()
    if not isinstance(signature,str) or not hmac.compare_digest(signature,expected):raise ValueError('Invalid command signature')
    return response['result']


def apply_command(store,command,admin_ids):
    required={'id','application_id','status','expected_revision','actor'}
    if not isinstance(command,dict) or set(command)!=required:raise ValueError('Invalid command schema')
    if any(not isinstance(command[k],str) or not command[k] or len(command[k])>100 for k in required-{'expected_revision'}):
        raise ValueError('Invalid command value')
    uuid.UUID(command['id'])
    raw=json.dumps(command,sort_keys=True,separators=(',',':'))
    digest=hashlib.sha256(raw.encode()).hexdigest()
    journey=Journey(store,admin_ids)
    old=store.db.execute('SELECT digest,result FROM crm_commands WHERE id=?',(command['id'],)).fetchone()
    if old:
        if old[0]!=digest:raise ValueError('Command ID conflict')
        return json.loads(old[1])
    return journey.transition(command['actor'],command['application_id'],command['status'],command['expected_revision'],
                              source='google_sheets',command_id=command['id'],digest=digest)


def import_commands(store,environment,transport=None):
    if environment.get('CRM_BIDIRECTIONAL_ENABLED')!='1':return dict(enabled=False,applied=0,rejected=0)
    cfg=config(environment)
    if cfg is None:raise ValueError('Reviewed CRM configuration required')
    commands=exchange(cfg,'pull_status_commands',transport=transport)
    if not isinstance(commands,list) or len(commands)>20:raise ValueError('Invalid command batch')
    applied=rejected=0
    admins=[i.strip() for i in environment.get('EWU_ADMIN_IDS','').split(',') if i.strip()]
    for command in commands:
        try:
            result=apply_command(store,command,admins);outcome='applied';applied+=1
        except (PermissionError,ValueError):
            result={};outcome='rejected';rejected+=1
        # Local result and notification are committed atomically before ACK.
        # Lost ACKs replay the same command ID without another state change.
        exchange(cfg,'ack_status_command',dict(command_id=command.get('id'),outcome=outcome,result=result),transport)
    return dict(enabled=True,applied=applied,rejected=rejected)


def drain_notifications(store,send_message):
    sent=uncertain=0
    journey=Journey(store)
    rows=store.db.execute("SELECT id,application_id,user_id,status,locale,revision FROM notifications WHERE state='pending' ORDER BY rowid LIMIT 20").fetchall()
    for event_id,aid,user,status,lang,number in rows:
        if not store.allowed(user):
            with store.db:store.db.execute("UPDATE notifications SET state='suppressed' WHERE id=?",(event_id,))
            continue
        row=journey._row(aid)
        if row['revision']!=number or row['policy_revision']!=revision(store.policy):
            with store.db:store.db.execute("UPDATE notifications SET state='suppressed' WHERE id=?",(event_id,))
            continue
        with store.db:
            claimed=store.db.execute("UPDATE notifications SET state='sending' WHERE id=? AND state='pending'",(event_id,)).rowcount
        if not claimed:continue
        try:
            send_message(user,'EWU: '+label(status,lang)+'\n'+aid)
            with store.db:store.db.execute("UPDATE notifications SET state='sent' WHERE id=?",(event_id,))
            sent+=1
        except Exception:
            # Telegram has no idempotency key. An uncertain delivery is held
            # for operator review rather than sending a possible duplicate.
            with store.db:store.db.execute("UPDATE notifications SET state='uncertain' WHERE id=?",(event_id,))
            uncertain+=1
    return dict(sent=sent,uncertain=uncertain)
