"""Opt-in signed Apps Script bridge. Disabled unless explicitly reviewed.
All queued content comes from current approved intake; no legacy endpoint reuse.
"""
import hashlib
import hmac
import json
import re
import time
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler
from privacy.onboarding import revision
from recruitment import Journey


class GoogleResponseRedirect(HTTPRedirectHandler):
 def redirect_request(self,req,fp,code,msg,headers,newurl):
  u=urlsplit(newurl)
  if (u.scheme!='https' or u.hostname!='script.googleusercontent.com' or u.username or u.password
      or u.port not in (None,443) or req.get_header('X-ewu-redirect') or code not in (301,302,303)):
   raise ValueError('CRM redirect refused')
  # Google ContentService serves its response by GET; no form data is forwarded.
  return Request(newurl,headers={'X-EWU-Redirect':'1'},method='GET')


def config(env):
 if env.get('CRM_V2_ENABLED')!='1' or env.get('CRM_V2_REVIEWED')!='1':return None
 endpoint=env.get('CRM_V2_URL','');u=urlsplit(endpoint)
 secret=env.get('CRM_V2_SECRET','');sheet=env.get('CRM_V2_SHEET_ID','')
 if (u.scheme!='https' or u.hostname!='script.google.com' or u.username or u.password
     or u.query or u.fragment or u.port not in (None,443)
     or not re.fullmatch(r'/macros/s/[A-Za-z0-9_-]+/exec',u.path)
     or len(secret)<32 or not re.fullmatch(r'[A-Za-z0-9_-]{20,}',sheet)):
  raise ValueError('Incomplete reviewed CRM configuration')
 return dict(url=endpoint,secret=secret,sheet_id=sheet)


def deliver(cfg,payload,transport=None,clock=time.time):
 body=json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(',',':'))
 timestamp=str(int(clock()))
 signature=hmac.new(cfg['secret'].encode(),(timestamp+'.'+body).encode(),hashlib.sha256).hexdigest()
 data=json.dumps(dict(timestamp=timestamp,payload=body,signature=signature),ensure_ascii=False).encode()
 request=Request(cfg['url'],data=data,headers={'Content-Type':'application/json'},method='POST')
 sender=transport or build_opener(GoogleResponseRedirect()).open
 with sender(request,timeout=10) as response:raw=response.read(8193)
 if len(raw)>8192:raise ValueError('CRM response too large')
 receipt=json.loads(raw)
 expected=dict(event_id=payload['event_id'],revision=payload['revision'],ok=True,sheet_id=cfg['sheet_id'])
 if not isinstance(receipt,dict) or set(receipt)!=(set(expected)|{'signature'}):raise ValueError('Invalid CRM receipt')
 if any(receipt[k]!=v for k,v in expected.items()):raise ValueError('CRM receipt mismatch')
 signed=json.dumps(expected,sort_keys=True,separators=(',',':'))
 mac=hmac.new(cfg['secret'].encode(),signed.encode(),hashlib.sha256).hexdigest()
 if not isinstance(receipt['signature'],str) or not hmac.compare_digest(mac,receipt['signature']):raise ValueError('Unsigned CRM response')
 return True


def flush(store,environment,transport=None):
 cfg=config(environment)
 if cfg is None:return dict(enabled=False,sent=0,failed=0)
 journey=Journey(store);sent=failed=0
 for item in journey.crm_batch():
  # Serialize senders and privacy changes. A verified external write can be
  # retried after a crash using application ID + revision as idempotency keys.
  store.db.execute('BEGIN IMMEDIATE')
  try:
   event=store.db.execute('SELECT status,attempts FROM crm_outbox WHERE id=?',(item['event_id'],)).fetchone()
   row=journey._row(item['application_id'])
   ack=store.db.execute("SELECT action,revision FROM privacy_events WHERE user_id=? AND action!='presented' ORDER BY id DESC LIMIT 1",(row['user_id'],)).fetchone()
   pending=store.db.execute('SELECT 1 FROM deletion_requests WHERE user_id=? AND status="pending"',(row['user_id'],)).fetchone()
   if (not event or event[0]!='pending' or pending or ack!=('acknowledged',revision(store.policy))
       or row['policy_revision']!=revision(store.policy) or row['revision']!=item['revision']):
    store.db.execute("UPDATE crm_outbox SET status='suppressed',last_error='changed_before_send' WHERE id=?",(item['event_id'],))
   else:
    try:
     deliver(cfg,item,transport=transport)
     store.db.execute("UPDATE crm_outbox SET status='sent',attempts=attempts+1,last_error=NULL WHERE id=?",(item['event_id'],));sent+=1
    except Exception:
     # Never persist raw HTTP errors, signed bodies, tokens or candidate data.
     store.db.execute("UPDATE crm_outbox SET attempts=attempts+1,status=CASE WHEN attempts>=4 THEN 'held' ELSE 'pending' END,last_error='delivery_unconfirmed' WHERE id=?",(item['event_id'],));failed+=1
   store.db.commit()
  except BaseException:
   store.db.rollback();raise
 return dict(enabled=True,sent=sent,failed=failed)
