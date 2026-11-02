import hashlib,hmac,json,subprocess,sys,time,unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from types import SimpleNamespace as NS
from privacy.onboarding import Store,revision
from recruitment import Journey
from crm_sync import config,deliver,flush,GoogleResponseRedirect
from railway_start import preflight
from test_privacy import fixture,FakeBot
from bot import create_bot

class RecoveryTests(unittest.TestCase):
 def setUp(self):
  self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.path=Path(self.tmp.name)/'privacy.sqlite3';self.policy=fixture()
  self.now=datetime(2026,11,2,tzinfo=timezone.utc)
  self.store=Store(self.path,self.policy,clock=lambda:self.now);self.addCleanup(self.store.close)
  self.journey=Journey(self.store,admin_ids=[99]);self.store.record(42,'acknowledged','uk')
 def application(self):
  self.store.begin_intake(42,'candidate')
  for key,value in [('name','TEST PERSON'),('city','TEST CITY'),('phone','+48123456789')]:self.store.save_answer(42,key,value)
  return self.store.save_answer(42,'profession','TEST WORK',completed=True)
 def env(self):return dict(CRM_V2_ENABLED='1',CRM_V2_REVIEWED='1',CRM_V2_URL='https://script.google.com/macros/s/synthetic/exec',CRM_V2_SECRET='x'*40,CRM_V2_SHEET_ID='syntheticSheetId1234567890')
 def sender(self,request,timeout):
  envelope=json.loads(request.data);p=json.loads(envelope['payload']);cfg=config(self.env())
  self.assertTrue(hmac.compare_digest(envelope['signature'],hmac.new(cfg['secret'].encode(),(envelope['timestamp']+'.'+envelope['payload']).encode(),hashlib.sha256).hexdigest()))
  body=dict(event_id=p['event_id'],ok=True,revision=p['revision'],sheet_id=cfg['sheet_id'])
  body['signature']=hmac.new(cfg['secret'].encode(),json.dumps(body,sort_keys=True,separators=(',',':')).encode(),hashlib.sha256).hexdigest()
  class Response:
   def __enter__(self):return self
   def __exit__(self,*args):pass
   def read(self,n):return json.dumps(body).encode()
  return Response()
 def test_application_journey_outbox_are_one_atomic_commit(self):
  aid=self.application();self.assertEqual(self.journey.own(42)[0]['status'],'NEW')
  self.assertEqual(len(self.journey.crm_batch()),1)
  self.store.begin_intake(42,'candidate')
  self.store.db.execute("CREATE TRIGGER fail_queue BEFORE INSERT ON crm_outbox BEGIN SELECT RAISE(ABORT,'synthetic failure'); END;")
  with self.assertRaises(Exception):self.store.save_answer(42,'name','TEST',completed=True)
  self.assertEqual(self.store.db.execute('SELECT count(*) FROM applications').fetchone()[0],1)
  self.assertIsNotNone(self.store.intake(42))
 def test_only_coordinator_can_change_status_and_revision_is_checked(self):
  aid=self.application()
  with self.assertRaises(PermissionError):self.journey.transition(42,aid,'CONTACTED',1)
  with self.assertRaises(ValueError):self.journey.transition(99,aid,'STARTED',1)
  self.assertEqual(self.journey.transition(99,aid,'CONTACTED',1)['revision'],2)
  with self.assertRaises(ValueError):self.journey.transition(99,aid,'OFFERED',1)
  self.assertEqual(len(self.journey.crm_batch()),1)
  self.assertEqual(self.journey.crm_batch()[0]['revision'],2)
 def test_approved_arrival_and_own_identity_isolation(self):
  aid=self.application();number=1
  for status in ['CONTACTED','OFFERED','CONFIRMED']:
   number=self.journey.transition(99,aid,status,number)['revision']
  self.assertIsNone(self.journey.arrival(42,aid))
  with self.assertRaises(ValueError):self.journey.transition(99,aid,'TRAVEL_PLANNED',number)
  plan=dict(workplace='TEST SITE',address='TEST ADDRESS',arrival_at=(self.now+timedelta(days=2)).isoformat(),contact='TEST CONTACT',transport='TEST ROUTE')
  number=self.journey.set_plan(99,aid,plan,number)['revision']
  number=self.journey.transition(99,aid,'TRAVEL_PLANNED',number)['revision']
  self.assertEqual(self.journey.arrival(42,aid),plan)
  with self.assertRaises(PermissionError):self.journey.arrival(43,aid)
  self.assertEqual(self.journey.own(43),[])
  self.now+=timedelta(days=3);self.assertIsNone(self.journey.arrival(42,aid))
 def test_withdraw_and_policy_change_prevent_sync_and_status_change(self):
  aid=self.application();self.store.record(42,'withdrawn','uk');self.journey.pause(42)
  self.assertEqual(self.journey.crm_batch(),[])
  self.assertEqual(len(self.journey.export_own(42)['applications']),1)
  with self.assertRaises(PermissionError):self.journey.transition(99,aid,'CONTACTED',1)
  self.store.record(42,'acknowledged','uk');self.policy['version']='test-v2'
  self.assertEqual(self.journey.crm_batch(),[])
 def test_current_policy_change_without_withdrawal_blocks_queued_old_record(self):
  aid=self.application();self.policy['version']='test-v2';self.store.record(42,'acknowledged','uk')
  self.assertEqual(self.journey.crm_batch(),[])
 def test_successful_signed_crm_receipt_and_no_duplicate_send(self):
  self.application();self.assertEqual(flush(self.store,self.env(),self.sender)['sent'],1)
  def forbidden(*args,**kwargs):raise AssertionError('Duplicate send')
  self.assertEqual(flush(self.store,self.env(),forbidden)['sent'],0)
 def test_no_network_when_disabled_and_unknown_legacy_endpoint_ignored(self):
  self.application()
  with patch('socket.socket',side_effect=AssertionError('No network')):
   self.assertFalse(flush(self.store,dict(CRM_ENABLED='1',GOOGLE_SCRIPT_URL='https://old.invalid'))['enabled'])
  for url in ['http://script.google.com/macros/s/x/exec','https://attacker.invalid/macros/s/x/exec','https://user:pw@script.google.com/macros/s/x/exec']:
   with self.assertRaises(ValueError):config({**self.env(),'CRM_V2_URL':url})
 def test_failed_attempts_bounded_and_errors_redacted(self):
  self.application()
  def broken(*a,**k):raise RuntimeError('SECRET_TOKEN_PRIVATE_DATA')
  for _ in range(5):self.assertEqual(flush(self.store,self.env(),broken)['failed'],1)
  self.assertEqual(flush(self.store,self.env(),broken)['failed'],0)
  row=self.store.db.execute('SELECT status,attempts,last_error FROM crm_outbox').fetchone()
  self.assertEqual(row,('held',5,'delivery_unconfirmed'))
 def test_unsigned_success_not_accepted_and_redirects_restricted(self):
  p=self.journey.crm_batch();aid=self.application();p=self.journey.crm_batch()[0]
  class Fake:
   def __enter__(self):return self
   def __exit__(self,*args):pass
   def read(self,n):return b'{"ok":true}'
  with self.assertRaises(ValueError):deliver(config(self.env()),p,lambda *a,**k:Fake())
  from urllib.request import Request
  redirect=GoogleResponseRedirect();request=Request(self.env()['CRM_V2_URL'],data=b'PRIVATE')
  with self.assertRaises(ValueError):redirect.redirect_request(request,None,302,'',{},'https://example.org/leak')
  new=redirect.redirect_request(request,None,302,'',{},'https://script.googleusercontent.com/macros/echo?user_content_key=test')
  self.assertIsNone(new.data);self.assertEqual(new.get_method(),'GET')
 def test_retention_cleans_local_card_and_outbox_without_export(self):
  self.application();self.now+=timedelta(days=8);self.journey.cleanup()
  for table in ['applications','candidate_journey','journey_events','crm_outbox']:
   self.assertEqual(self.store.db.execute('SELECT count(*) FROM '+table).fetchone()[0],0)
 def test_startup_requires_legal_and_explicit_controls_no_token_printed(self):
  out=preflight(dict(TELEGRAM_TOKEN='SYNTHETIC_SECRET'))
  self.assertFalse(out['ready']);self.assertNotIn('SYNTHETIC_SECRET',json.dumps(out))
  policy_path=Path(self.tmp.name)/'policy.json';policy_path.write_text(json.dumps(self.policy))
  out=preflight(dict(TELEGRAM_TOKEN='TEST',PRIVACY_CONFIG_FILE=str(policy_path),PRIVACY_DB_PATH=str(self.path),EWU_START_ALLOWED='1',EWU_MAINTENANCE='0'))
  self.assertTrue(out['ready']);self.assertFalse(out['paid_api_calls'])
  env=dict(TELEGRAM_TOKEN='TEST',PRIVACY_CONFIG_JSON=json.dumps(self.policy),PRIVACY_DB_PATH=str(self.path),EWU_START_ALLOWED='1',EWU_MAINTENANCE='0')
  self.assertTrue(preflight(env)['ready'])
 def test_bot_pipeline_and_rights_after_policy_config_disappears(self):
  path=Path(self.tmp.name)/'policy.json';path.write_text(json.dumps(self.policy));fake=FakeBot()
  create_bot(None,path,self.path,fake,admin_ids=[99])
  def msg(t):return NS(text=t,chat=NS(id=42,type='private'),from_user=NS(id=42,language_code='uk',is_bot=False))
  for text in ['👷 Шукаю роботу','TEST NAME','TEST CITY','+48123456789','TEST WORK']:fake.handle(msg(text))
  fake.handle(msg('/status'));self.assertIn('NEW',fake.sent[-1][1])
  fake.handle(msg('/arrival'));self.assertIn('ще немає',fake.sent[-1][1])
  path.unlink();fake.handle(msg('/my_data'));self.assertIn('TEST NAME',fake.sent[-1][1])
  fake.handle(msg('/delete_data'));self.assertFalse(self.store.allowed(42))
  self.assertEqual(self.journey.crm_batch(),[])
 def test_reopen_has_same_queue_and_own_card(self):
  aid=self.application();other=Store(self.path,self.policy,clock=lambda:self.now)
  try:
   j=Journey(other);self.assertEqual(j.own(42)[0]['id'],aid);self.assertEqual(len(j.crm_batch()),1)
  finally:other.close()
 def test_repeated_ack_and_restart_keep_partial_form(self):
  self.store.begin_intake(42,'candidate');self.store.save_answer(42,'name','TEST RESUME')
  self.store.record(42,'acknowledged','uk')
  self.assertEqual(self.store.intake(42)[1]['name'],'TEST RESUME')
  other=Store(self.path,self.policy,clock=lambda:self.now)
  try:self.assertEqual(other.intake(42)[1]['name'],'TEST RESUME')
  finally:other.close()
 def test_process_lock_rejects_second_owner(self):
  from polling_lock import acquire
  path=Path(self.tmp.name)/'poll.lock'
  with acquire(path):
   with self.assertRaises((BlockingIOError,OSError)):
    with acquire(path):pass

if __name__=='__main__':unittest.main()
