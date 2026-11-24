import io,json,os,sqlite3,unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace as NS
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from fastapi.testclient import TestClient
from radar.core import Settings,Radar,Refused,Forbidden,REQUIRED,now,dump
from radar.api import create_app
from radar.security import password_hash,verify_password
from radar.telegram import create_bot
from radar.__main__ import restore

PASS='synthetic-test-password-42'
BASE=dict(RADAR_SESSION_SECRET='synthetic-session-key-'*3,RADAR_PUBLIC_ORIGIN='https://testserver',RADAR_ADMIN_PASSWORD_HASH=password_hash(PASS),RADAR_INTAKE_ENABLED='1',RADAR_PRIVACY_REVIEWED='1',RADAR_POLICY_VERSION='synthetic-v1',RADAR_CONTROLLER='SYNTHETIC CONTROLLER',RADAR_PRIVACY_CONTACT='test@example.invalid',RADAR_LEGAL_BASIS='SYNTHETIC REVIEW ONLY',RADAR_PRIVACY_TEXT='SYNTHETIC TEST NOTICE — NOT A LIVE POLICY',RADAR_RETENTION_DAYS='7')
ANSWERS=dict(city='any',schedule='any',start='any',skills={},min_pay=None)

def seed(radar,jid='test-job',active=True,schedule='day: 06:00–14:00',requirements=None):
    public=dict(title='SYNTHETIC WAREHOUSE',city='Test City',description='Pack synthetic goods',pay='28 PLN netto/hour',pay_net_min=28,schedule=schedule,schedule_type=schedule.split(':')[0],housing='Synthetic accommodation',requirements=requirements or [])
    verified={k:'https://example.invalid/review#test-v1' for k in public}
    with radar.connect() as db:
        db.execute('INSERT INTO vacancies(id,public_json,verified_json,active,updated_at) VALUES(?,?,?,?,?)',(jid,dump(public),dump(verified),int(active),now()))
        db.execute('INSERT INTO vacancy_private(vacancy_id,notes,source_json) VALUES(?,?,?)',(jid,'SECRET INTERNAL NOTE',dump({'commission':'SECRET COMMISSION','age':'SECRET AGE'})))
        db.execute('INSERT OR IGNORE INTO projects VALUES(?,?,?)',('project','SYNTHETIC PRIVATE PROJECT','{"bonus":"SECRET BONUS"}'))

class FakeBot:
    def __init__(self):self.sent=[]
    def message_handler(self,**kwargs):
        def register(fn):self.handle=fn;return fn
        return register
    def callback_query_handler(self,**kwargs):
        def register(fn):self.callback=fn;return fn
        return register
    def send_message(self,user,text,**kwargs):self.sent.append((user,text,kwargs))
    def answer_callback_query(self,*args):pass

class RadarTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.settings=Settings({**BASE,'RADAR_DB_PATH':str(self.root/'radar.sqlite3')});self.radar=Radar(self.settings);seed(self.radar)
        self.client=TestClient(create_app(self.settings),base_url='https://testserver');self.addCleanup(self.client.close)
    def login(self):
        response=self.client.post('/api/login',json={'password':PASS},headers={'origin':'https://testserver'})
        self.assertEqual(response.status_code,200,response.text)
        return {'origin':'https://testserver','x-csrf-token':response.json()['csrf']}
    def submit(self,user=42,jids=None,phone='+48123456789',source='fb_test'):
        self.radar.consent(user);return self.radar.submit(user,jids or ['test-job'],phone,ANSWERS,source)
    def test_no_defaults_enable_intake_and_policy_changes_invalidate_consent(self):
        self.assertFalse(Settings({}).ready)
        self.radar.consent(42);self.settings.policy_text+=' CHANGED'
        with self.assertRaises(Forbidden):self.radar.submit(42,['test-job'],'+48123456789',ANSWERS,'test')
        self.settings.intake=False
        with self.assertRaises(Forbidden):self.radar.consent(43)
    def test_drafts_inactive_and_unverified_vacancies_not_public(self):
        seed(self.radar,'inactive',False)
        with self.radar.connect() as db:db.execute("UPDATE vacancies SET verified_json='{}' WHERE id='test-job'")
        self.assertEqual(self.client.get('/api/public/vacancies').json()['vacancies'],[])
    def test_no_private_notes_commissions_sensitive_criteria_in_any_public_projection(self):
        for response in [self.client.get('/api/public/vacancies'),self.client.post('/api/public/match',json=ANSWERS)]:
            self.assertEqual(response.status_code,200);body=response.text
            for secret in ('SECRET','commission','internal_notes','age'):self.assertNotIn(secret,body)
        for key in ('age','gender','nationality','citizenship','passport','address','birth_date'):
            self.assertEqual(self.client.post('/api/public/match',json={**ANSWERS,key:'synthetic'}).status_code,409)
    def test_match_explains_city_schedule_pay_and_filters_clear_mismatches(self):
        seed(self.radar,'night',schedule='night: 22:00–06:00')
        jobs=self.radar.match({**ANSWERS,'city':'Test City','schedule':'day','min_pay':27})
        self.assertEqual([j['id'] for j in jobs],['test-job']);self.assertIn('Підходить графік',jobs[0]['reasons'])
        self.assertEqual(self.radar.match({**ANSWERS,'city':'Unknown City'}),[])
        self.assertEqual(self.radar.match({**ANSWERS,'min_pay':30}),[])
    def test_required_skill_no_excludes_unknown_never_auto_rejected(self):
        seed(self.radar,'tools',requirements=['power_tools'])
        self.assertNotIn('tools',[j['id'] for j in self.radar.match({**ANSWERS,'skills':{'power_tools':'no'}})])
        self.assertIn('tools',[j['id'] for j in self.radar.match({**ANSWERS,'skills':{'power_tools':'unknown'}})])
    def test_consent_required_before_contact_no_unknown_fields(self):
        with self.assertRaises(Forbidden):self.radar.submit(42,['test-job'],'+48123456789',ANSWERS,'test')
        with self.radar.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM applicants').fetchone()[0],0)
        self.radar.consent(42)
        with self.assertRaises(Refused):self.radar.submit(42,['test-job'],'+48123456789',{**ANSWERS,'passport':'123'},'test')
    def test_one_person_multiple_vacancies_no_duplicate_same_job(self):
        seed(self.radar,'second')
        first=self.submit(jids=['test-job','second','test-job']);self.assertEqual(len(first),2)
        repeat=self.radar.submit(42,['test-job'],'48123456789',ANSWERS,'another_source')
        self.assertTrue(repeat[0]['duplicate'])
        with self.radar.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM applications').fetchone()[0],2)
            self.assertEqual(db.execute('SELECT DISTINCT source FROM applications').fetchall()[0][0],'fb_test')
    def test_parallel_submissions_are_atomic_and_deduplicated(self):
        self.radar.consent(42)
        def send(_):return self.radar.submit(42,['test-job'],'+48123456789',ANSWERS,'test')
        with ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(send,range(8)))
        self.assertEqual(sum(not r[0]['duplicate'] for r in results),1)
    def test_application_closed_between_selection_and_submit_not_saved(self):
        self.radar.consent(42)
        with self.radar.connect() as db:db.execute('UPDATE vacancies SET active=0')
        with self.assertRaises(Refused):self.radar.submit(42,['test-job'],'+48123456789',ANSWERS,'test')
        self.assertEqual(self.radar.own(42),[])
    def test_same_phone_other_identity_flagged_not_merged_or_exposed(self):
        self.submit(42);self.submit(43)
        candidates=self.radar.candidates();self.assertTrue(all(c['possible_duplicate'] for c in candidates))
        self.assertEqual(len(self.radar.own(42)),1);self.assertEqual(self.radar.own(44),[])
    def test_all_admin_endpoints_require_auth_and_writes_need_csrf_origin(self):
        aid=self.submit()[0]['id']
        for url in ['/api/admin/vacancies','/api/admin/applications','/api/admin/applications/'+aid,'/api/admin/metrics','/api/admin/notifications','/api/admin/deletion-requests']:
            response=self.client.get(url);self.assertEqual(response.status_code,403,url);self.assertNotIn('+48123456789',response.text)
        headers=self.login()
        for h in ({},{'origin':'https://attacker.invalid','x-csrf-token':headers['x-csrf-token']},{'origin':'https://testserver','x-csrf-token':'wrong'}):
            self.assertEqual(self.client.patch('/api/admin/applications/'+aid,headers=h,json={'status':'CONTACT','note':'test','revision':1}).status_code,403)
    def test_cookie_secure_http_only_no_credential_exposure(self):
        response=self.client.post('/api/login',json={'password':PASS},headers={'origin':'https://testserver'})
        cookie=response.headers['set-cookie'];self.assertIn('HttpOnly',cookie);self.assertIn('Secure',cookie);self.assertIn('SameSite=strict',cookie)
        self.assertNotIn(PASS,response.text)
        self.assertIn("frame-ancestors 'none'",response.headers['content-security-policy'])
    def test_login_rate_limit_and_password_hash(self):
        self.assertTrue(verify_password(PASS,self.settings.admin_hash));self.assertFalse(verify_password('bad',self.settings.admin_hash))
        for _ in range(5):self.assertEqual(self.client.post('/api/login',json={'password':'wrong-password'},headers={'origin':'https://testserver'}).status_code,403)
        self.assertEqual(self.client.post('/api/login',json={'password':PASS},headers={'origin':'https://testserver'}).status_code,429)
    def test_edit_vacancy_revision_public_boundary_and_reverification(self):
        headers=self.login();job=self.radar.admin_jobs()[0]
        body={k:job[k] for k in ('public','verified','active','revision','internal_notes')}
        body['public']['pay']='netto_min=30.00; synthetic changed'
        self.assertEqual(self.client.put('/api/admin/vacancies/test-job',headers=headers,json=body).status_code,409)
        body['verified']['pay']='https://example.invalid/new-review#20261124'
        self.assertEqual(self.client.put('/api/admin/vacancies/test-job',headers=headers,json=body).status_code,200)
        self.assertEqual(self.client.put('/api/admin/vacancies/test-job',headers=headers,json=body).status_code,409)
        body['revision']=2;body['public']['commission']='secret'
        self.assertEqual(self.client.put('/api/admin/vacancies/test-job',headers=headers,json=body).status_code,409)
    def test_status_history_search_filters_notes_and_stale_update(self):
        aid=self.submit()[0]['id'];headers=self.login()
        body={'status':'INTERVIEW','note':'SYNTHETIC PRIVATE RECRUITER NOTE','revision':1}
        self.assertEqual(self.client.patch('/api/admin/applications/'+aid,headers=headers,json=body).status_code,200)
        self.assertEqual(self.client.patch('/api/admin/applications/'+aid,headers=headers,json=body).status_code,409)
        response=self.client.get('/api/admin/applications',params={'q':'123456','source':'fb_test','city':'any','status':'INTERVIEW'})
        self.assertEqual(len(response.json()['applications']),1)
        detail=self.client.get('/api/admin/applications/'+aid).json();self.assertEqual([h['status'] for h in detail['history']],['NEW','INTERVIEW'])
    def test_withdraw_and_deletion_request_block_processing_then_erase(self):
        aid=self.submit()[0]['id'];self.radar.withdraw(42,delete=True)
        with self.assertRaises(Refused):self.radar.update_application('test',aid,'HIRED','',2)
        with self.assertRaises(Forbidden):self.radar.consent(42)
        headers=self.login();requests=self.client.get('/api/admin/deletion-requests').json()['requests'];self.assertEqual(len(requests),1)
        self.assertEqual(self.client.post('/api/admin/deletion-requests/'+requests[0]['applicant_id']+'/complete',headers=headers,json={}).status_code,200)
        with self.radar.connect() as db:
            for name in ('applicants','applications','status_history','outbox','deletion_requests'):self.assertEqual(db.execute('SELECT count(*) FROM '+name).fetchone()[0],0,name)
    def test_notifications_never_contain_contact_or_answers(self):
        self.submit();self.login();response=self.client.get('/api/admin/notifications')
        self.assertNotIn('123456789',response.text);self.assertNotIn('answers',response.text);self.assertEqual(len(response.json()['notifications']),1)
    def test_source_attribution_funnel_counts_unique_candidates_cost_interview(self):
        seed(self.radar,'second');self.radar.record_visit(42,'fb_test');self.radar.record_visit(42,'fb_test')
        apps=self.submit(jids=['test-job','second'])
        for a in apps:self.radar.update_application('test',a['id'],'INTERVIEW','',1)
        headers=self.login();self.assertEqual(self.client.put('/api/admin/sources/fb_test',headers=headers,json={'label':'TEST ADS','spend_grosz':20000}).status_code,200)
        metrics=self.radar.metrics()['sources'][0]
        self.assertEqual(metrics['starts'],1);self.assertEqual(metrics['applications'],2);self.assertEqual(metrics['INTERVIEW'],1)
        self.assertEqual(metrics['cost_per_interview_grosz'],20000);self.assertEqual(metrics['start_to_application'],1)
    def test_retention_cleanup_removes_expired_contacts(self):
        self.submit()
        with self.radar.connect() as db:db.execute("UPDATE applicants SET expires_at='2000-01-01T00:00:00+00:00'")
        self.radar.cleanup();self.assertEqual(self.radar.candidates(),[])
    def test_database_reopen_backup_and_real_restore_preserve_records(self):
        aid=self.submit()[0]['id'];self.radar.update_application('test',aid,'CONTACT','SYNTHETIC NOTE',1)
        self.assertEqual(Radar(self.settings).own(42)[0]['id'],aid)
        backup=self.root/'backups'/'test.sqlite3';self.radar.backup(backup)
        restored=self.root/'restored.sqlite3';restore(backup,restored)
        settings=Settings({**BASE,'RADAR_DB_PATH':str(restored)});other=Radar(settings)
        self.assertEqual(other.detail(aid),self.radar.detail(aid))
        self.assertEqual(other.admin_jobs(),self.radar.admin_jobs());self.assertEqual(other.metrics(),self.radar.metrics())
        with self.assertRaises(ValueError):restore(backup,self.settings.database)
    def test_no_candidate_text_or_contact_in_audit(self):
        aid=self.submit()[0]['id'];self.radar.update_application('test',aid,'CONTACT','SYNTHETIC SECRET NOTE',1)
        with self.radar.connect() as db:body=dump([dict(r) for r in db.execute('SELECT * FROM audit')])
        self.assertNotIn('123456789',body);self.assertNotIn('SYNTHETIC SECRET NOTE',body)
    def test_bot_end_to_end_multi_job_source_consent_own_contact(self):
        seed(self.radar,'second');fake=FakeBot();bot=create_bot(self.radar,fake)
        def msg(text=None,contact=None,user=42):return NS(text=text,contact=contact,chat=NS(id=user,type='private'),from_user=NS(id=user,is_bot=False))
        def click(data):fake.callback(NS(id='test',data=data,message=msg(),from_user=NS(id=42)))
        fake.handle(msg('/start src_fb_test'))
        for value in ('begin','city:any','schedule:any','start:now','pay:any','job:test-job','select:test-job','select:second','submit'):
            click(value)
        with self.radar.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM applicants').fetchone()[0],0)
        click('consent:'+self.settings.policy_revision[:20])
        fake.handle(msg(contact=NS(user_id=43,phone_number='+48999999999')));self.assertEqual(self.radar.own(42),[])
        fake.handle(msg(contact=NS(user_id=42,phone_number='+48123456789')))
        self.assertEqual(len(self.radar.own(42)),2)
        for row in self.radar.candidates():self.assertEqual(row['source'],'fb_test')
        self.assertNotIn('SECRET INTERNAL',str(fake.sent));self.assertNotIn('SECRET COMMISSION',str(fake.sent))
        fake.handle(msg('/withdraw'));self.assertTrue(all(r['status']=='WITHDRAWN' for r in self.radar.own(42)))
        for _,text,options in fake.sent:
            self.assertLessEqual(len(text),3500)
            kb=options.get('reply_markup')
            if kb:
                for row in json.loads(kb.to_json()).get('inline_keyboard',[]):
                    for button in row:self.assertLessEqual(len(button.get('callback_data','').encode()),64)
    def test_bot_disabled_intake_unknown_text_and_media_never_saved(self):
        self.settings.intake=False;fake=FakeBot();create_bot(self.radar,fake)
        def msg(t):return NS(text=t,contact=None,chat=NS(id=42,type='private'),from_user=NS(id=42,is_bot=False))
        fake.handle(msg('/start'));fake.handle(msg('PRIVATE PASSPORT DATA'));fake.handle(msg(None))
        fake.radar_flow if hasattr(fake,'radar_flow') else None
        with self.radar.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM applicants').fetchone()[0],0)
        self.assertNotIn('PRIVATE PASSPORT DATA',str(fake.sent))

if __name__=='__main__':unittest.main()
