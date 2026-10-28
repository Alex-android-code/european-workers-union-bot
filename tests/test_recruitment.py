"""Synthetic-only backend/transport end-to-end and adversarial tests."""
from datetime import datetime,timedelta,timezone
import json
from types import SimpleNamespace as NS
import unittest

from ewu.storage import Database
from ewu.domain import Actor,Denied
from ewu.service import Recruitment
from ewu.ai import RecruitmentAI
from ewu.sheets import MemorySheets,GoogleSheets,projection,TABS
from ewu.worker import Worker,SheetsSync,MemoryDelivery
from ewu.telegram import TelegramRecruitment
from privacy.onboarding import UI,FIELDS,revision


def policy():
    return {'version':'synthetic-v2','legal_review_approved':True,'effective_at':'2026-01-01T00:00:00+00:00',
            'core_legal_basis':'art6_1_b','ai_approved':True,'ai_processing_basis':'art6_1_b','partner_transfer_approved':True,'notifications_approved':True,'sheets_approved':True,
            'audit_retention_days':30,'application_retention_days':7,
            'notices':{lang:{**{k:'SYNTHETIC TEST ONLY '+k for k in FIELDS},'policy_url':'https://example.invalid/privacy'} for lang in UI}}


class RecruitmentTests(unittest.TestCase):
    def setUp(self):
        self.db=Database.synthetic();self.addCleanup(self.db.close)
        self.now=datetime(2026,10,28,12,tzinfo=timezone.utc)
        self.p=policy();self.s=Recruitment(self.db,self.p,lambda:self.now)
        self.owner=Actor('9000');self.candidate=Actor('1000');self.partner_actor=Actor('9001')
        self.db.execute("INSERT INTO ewu2_actors VALUES('9000','owner',NULL)")
        self.db.execute("INSERT INTO ewu2_actors VALUES('system-recruiter','recruiter',NULL)")
        self.partner=self.s.partner(self.owner,'SYNTHETIC Partner','test@example.invalid')
        self.s.grant_actor(self.owner,'9001','partner',self.partner)
        self.vacancy=self.s.vacancy(self.owner,self.partner,'test-1',self.conditions(),(self.now+timedelta(days=7)).isoformat())
    @staticmethod
    def conditions():
        return {'title':'TEST welder','location':'TEST City','address':'TEST Address','rate':'TEST 30 PLN/h',
                'payment_type':'hourly','schedule':'TEST schedule','housing':'TEST housing','transport':'TEST transport',
                'requirements':'TEST skill','places':2,'start_date':'2026-11-02','coordinator':'test@example.invalid'}
    def register(self,actor=None):
        actor=actor or self.candidate
        self.s.privacy(actor,'uk','acknowledged',revision(self.p))
        return self.s.register(actor,'uk',{'name':'SYNTHETIC Candidate','city':'TEST','profession':'welder'},'+48123456789')
    def accepted(self):
        self.register();app=self.s.apply(self.candidate,self.vacancy)
        for state in ['SUBMITTED_TO_PARTNER','PARTNER_REVIEW']:
            self.s.transition(self.owner,app,state)
        self.s.transition(self.partner_actor,app,'ACCEPTED')
        self.s.instructions(self.partner_actor,app,{'address':'TEST address','arrival_at':(self.now+timedelta(days=2)).isoformat(),
                                                  'coordinator':'test@example.invalid','transport':'TEST train','packing':'TEST checklist'})
        self.s.transition(self.partner_actor,app,'START_DATE_CONFIRMED')
        self.s.transition(self.owner,app,'TRAVEL_PLANNED')
        return app
    def started(self):
        app=self.accepted()
        self.s.transition(self.candidate,app,'ON_THE_WAY');self.s.transition(self.candidate,app,'ARRIVED')
        self.s.transition(self.partner_actor,app,'CHECKED_IN');self.s.transition(self.partner_actor,app,'STARTED_WORK')
        return app
    def test_full_twenty_step_synthetic_scenario(self):
        # Existing Telegram bot transport: choose language, notice, form and ID.
        adapter=TelegramRecruitment(self.s)
        class Bot:
            def __init__(self):self.sent=[]
            def send_message(self,chat,text,**kw):self.sent.append((text,kw))
            def answer_callback_query(self,identifier):pass
        bot=Bot();counter=0
        user=NS(id=1000,is_bot=False,language_code='uk')
        def send(text):
            nonlocal counter
            counter+=1;adapter.message(NS(chat=NS(id=1000,type='private'),from_user=user,text=text,message_id=counter),bot)
        def click(data):
            nonlocal counter
            counter+=1;adapter.callback(NS(id=str(counter),data=data,from_user=user,message=NS(chat=NS(id=1000,type='private'))),bot)
        send('/start');self.assertIn('inline_keyboard',bot.sent[-1][1]['reply_markup'])
        self.assertIsNone(self.s.candidate('1000'))
        click('v2:lang:uk');self.assertIn('Polityka prywatności',bot.sent[-1][0])
        click('v2:ack:uk:'+revision(self.p))
        send('/profile')
        for text in ['SYNTHETIC Candidate','TEST City','welder','+48123456789']:send(text)
        candidate=self.s.candidate('1000');self.assertIsNotNone(candidate);self.assertIn(candidate['id'],bot.sent[-1][0])
        sheet=MemorySheets();delivery=MemoryDelivery()
        sync=SheetsSync(self.s,sheet,self.owner,candidate['id'])
        worker=Worker(self.s,{'sheets':sync,'sheets_finance':sync,'partner':delivery,'notification':delivery,'operator':delivery})
        for _ in range(50):
            if not worker.run_one():break
        self.assertEqual(len(sheet.tabs['Candidates']),2)
        send('/vacancies');self.assertIn(self.vacancy,bot.sent[-1][0])
        send('/apply '+self.vacancy)
        app=self.db.one('SELECT * FROM ewu2_applications')['id']
        self.s.transition(self.owner,app,'SUBMITTED_TO_PARTNER');self.s.transition(self.partner_actor,app,'PARTNER_REVIEW')
        self.s.transition(self.partner_actor,app,'ACCEPTED')
        self.s.instructions(self.partner_actor,app,{'address':'TEST Address','arrival_at':(self.now+timedelta(days=1)).isoformat(),'coordinator':'test@example.invalid','transport':'TEST train','packing':'TEST checklist'})
        self.s.transition(self.partner_actor,app,'START_DATE_CONFIRMED');self.s.transition(self.owner,app,'TRAVEL_PLANNED')
        self.s.follow_up(self.owner,app,self.now.isoformat());self.s.due_followups()
        send('/on_the_way '+app);send('/arrived '+app)
        self.assertIsNone(self.db.one('SELECT * FROM ewu2_employment_starts'))
        self.s.transition(self.partner_actor,app,'CHECKED_IN');self.s.transition(self.partner_actor,app,'STARTED_WORK')
        commission=self.s.commission(self.owner,app,'one_time',10000,1,'PLN','TEST-CONTRACT','2026-11')
        self.assertEqual(commission,self.s.commission(self.owner,app,'one_time',10000,1,'PLN','TEST-CONTRACT','2026-11'))
        for _ in range(100):
            if not worker.run_one():break
        self.assertEqual(sheet.tabs['Applications'][1][4],'STARTED_WORK')
        self.assertEqual(len(sheet.tabs['Commissions']),2)
        self.assertEqual(dict(sheet.tabs['Dashboard'][1:])['confirmed_starts'],1)
        self.assertIn('UNPAID',sheet.tabs['Commissions'][1])
        self.assertTrue(delivery.items)
        self.assertGreater(self.db.one('SELECT count(*) AS n FROM ewu2_audit_events')['n'],15)
        self.assertEqual(self.db.one('SELECT count(*) AS n FROM ewu2_recruitment_events')['n'],14)
        # Restarting and repeated /start preserve canonical candidate ID.
        send('/start');click('v2:lang:uk');click('v2:ack:uk:'+revision(self.p))
        self.assertEqual(self.s.candidate('1000')['id'],candidate['id'])
        self.assertEqual(Recruitment(self.db,self.p).self_data(self.candidate)['applications'][0]['id'],app)
    def test_no_profile_before_legal_gate_and_current_ack(self):
        with self.assertRaises(Denied):self.s.register(self.candidate,'uk',{'name':'TEST'})
        self.p['legal_review_approved']=False
        with self.assertRaises(Denied):self.register()
        self.p['legal_review_approved']=True;self.register();self.p['version']='changed'
        with self.assertRaises(Denied):self.s.register(self.candidate,'uk',{'city':'TEST'})
    def test_one_candidate_multiple_applications_and_partner_identity(self):
        cid=self.register();self.assertEqual(cid,self.s.register(self.candidate,'uk',{'city':'UPDATED'}))
        first=self.s.apply(self.candidate,self.vacancy);self.assertEqual(first,self.s.apply(self.candidate,self.vacancy))
        partner2=self.s.partner(self.owner,'TEST second partner','test2@example.invalid')
        vacancy2=self.s.vacancy(self.owner,partner2,'test-1',self.conditions(),(self.now+timedelta(days=2)).isoformat())
        second=self.s.apply(self.candidate,vacancy2);self.assertNotEqual(first,second)
        with self.assertRaises(Denied):self.s.application(self.partner_actor,second)
        with self.assertRaises(Denied):self.s.application(self.partner_actor,first) # not submitted yet
        self.s.transition(self.owner,first,'SUBMITTED_TO_PARTNER')
        self.assertEqual(self.s.application(self.partner_actor,first)['partner_id'],self.partner)
        with self.assertRaises(Denied):self.s.application(Actor('other-candidate'),first)
        self.s.transition(self.partner_actor,first,'PARTNER_REVIEW')
        self.s.transition(self.partner_actor,first,'REJECTED')
        # Existing applications remain independent; create a third vacancy for alternatives.
        third=self.s.vacancy(self.owner,partner2,'test-3',self.conditions(),(self.now+timedelta(days=2)).isoformat())
        self.assertEqual([v['id'] for v in self.s.alternatives(self.candidate,first)],[third])
        self.assertEqual(self.s.application(self.candidate,first)['status'],'REJECTED')
    def test_withdrawal_optional_consent_and_rights_isolation(self):
        self.register()
        self.p['optional_consents']={'marketing':{'legal_review_approved':True,'texts':{lang:'TEST optional consent' for lang in UI}}}
        self.s.privacy(self.candidate,'uk','acknowledged',revision(self.p))
        self.s.privacy(self.candidate,'uk','consent_refused',revision(self.p),'marketing')
        self.assertTrue(self.s.allowed('1000'))
        self.s.rights(self.candidate,'withdraw');self.assertFalse(self.s.allowed('1000'))
        self.assertEqual(self.db.one('SELECT granted FROM ewu2_consents')['granted'],0)
        delete=self.s.rights(self.candidate,'delete');self.assertEqual(delete,self.s.rights(self.candidate,'delete'))
        self.s.privacy(self.candidate,'uk','acknowledged',revision(self.p));self.assertFalse(self.s.allowed('1000'))
        self.assertIsNone(self.s.self_data(Actor('1001'))['candidate'])
        with self.assertRaises(Exception):self.db.execute("UPDATE ewu2_privacy_records SET decision='acknowledged'")
    def test_partner_transfer_gated_stale_vacancy_excluded_and_alternatives(self):
        self.register();app=self.s.apply(self.candidate,self.vacancy)
        self.p['partner_transfer_approved']=False
        # A policy change also invalidates acknowledgement; acknowledge new content first.
        self.s.privacy(self.candidate,'uk','acknowledged',revision(self.p))
        with self.assertRaises(Denied):self.s.transition(self.owner,app,'SUBMITTED_TO_PARTNER')
        self.now+=timedelta(days=8);self.assertEqual(self.s.expire_vacancies(),1)
        self.assertEqual(self.s.matches(self.candidate),[])
        with self.assertRaises(Denied):self.s.apply(self.candidate,self.vacancy)
    def test_arrival_is_not_employment_and_finance_rbac(self):
        app=self.accepted();self.s.transition(self.candidate,app,'ON_THE_WAY');self.s.transition(self.candidate,app,'ARRIVED')
        with self.assertRaises(Denied):self.s.transition(self.candidate,app,'STARTED_WORK')
        with self.assertRaises(Denied):self.s.commission(self.owner,app,'one_time',1,1,'PLN','TEST','TEST')
        self.s.transition(self.partner_actor,app,'CHECKED_IN');self.s.transition(self.partner_actor,app,'STARTED_WORK')
        with self.assertRaises(Denied):self.s.commission(self.partner_actor,app,'one_time',1,1,'PLN','TEST','TEST')
        with self.assertRaises(Denied):self.s.commission(self.owner,app,'one_time',1,2,'PLN','TEST','TEST')
    def test_ai_fallback_kill_switch_injection_and_budget(self):
        self.register()
        class Provider:
            def __init__(self):self.calls=[]
            def rank(self,request,**kw):
                self.calls.append(request)
                return {'vacancy_ids':['invented-vacancy'],'cost_minor':1}
        provider=Provider();ai=RecruitmentAI(self.s,provider,True,10,5)
        self.assertEqual(ai.choose(self.candidate,'r1')['mode'],'fallback');self.assertFalse(provider.calls)
        with self.assertRaises(Denied):self.s.ai_switch(self.candidate,True)
        self.s.ai_switch(self.owner,True)
        self.assertEqual(ai.choose(self.candidate,'r2')['mode'],'fallback');self.assertEqual(len(provider.calls),1)
        self.assertNotIn('SYNTHETIC Candidate',json.dumps(provider.calls));self.assertNotIn('+48123456789',json.dumps(provider.calls))
        ai.choose(self.candidate,'r3');ai.choose(self.candidate,'r4');self.assertEqual(len(provider.calls),2)
        self.s.ai_switch(self.owner,False);ai.choose(self.candidate,'r5');self.assertEqual(len(provider.calls),2)
        self.assertEqual(self.db.one('SELECT sum(reserved_minor) AS n FROM ewu2_ai_usage')['n'],10)
    def test_notifications_bounded_on_hold_and_optout_keeps_core(self):
        app=self.accepted();self.s.follow_up(self.owner,app,self.now.isoformat(),max_attempts=1,interval_hours=12)
        self.s.due_followups();self.now+=timedelta(hours=13);self.s.due_followups()
        self.assertEqual(self.s.application(self.candidate,app)['status'],'ON_HOLD')
        self.assertEqual(self.db.one("SELECT count(*) AS n FROM ewu2_outbox WHERE dedupe_key LIKE 'followup:%'")['n'],1)
        self.s.transition(self.candidate,app,'INTERESTED')
        self.s.notification_preference(self.candidate,False);self.assertTrue(self.s.allowed('1000'))
    def test_sheets_failure_retry_no_duplicate_and_finance_access(self):
        self.register();sink=MemorySheets();sink.failures=1
        sync=SheetsSync(self.s,sink,self.owner);worker=Worker(self.s,{'sheets':sync})
        worker.run_one();self.assertEqual(self.db.one("SELECT status FROM ewu2_outbox WHERE topic='sheets'")['status'],'pending')
        self.now+=timedelta(minutes=2);worker.run_one();self.assertEqual(len(sink.tabs['Candidates']),2)
        sync('ignored',{},'repeat');self.assertEqual(len(sink.tabs['Candidates']),2)
        self.s.grant_actor(self.owner,'9002','recruiter')
        with self.assertRaises(Denied):projection(self.s,Actor('9002'))
    def test_atomic_duplicate_telegram_updates_and_rollback(self):
        self.register()
        fn=lambda:self.s.apply(self.candidate,self.vacancy)
        first=self.s.process_update('synthetic-update',fn);self.assertIsNone(self.s.process_update('synthetic-update',fn))
        self.assertEqual(self.db.one('SELECT count(*) AS n FROM ewu2_applications')['n'],1)
        def broken():
            self.db.execute("UPDATE ewu2_candidates SET profile='{}'")
            raise Denied('synthetic failure')
        with self.assertRaises(Denied):self.s.process_update('broken',broken)
        self.assertIn('name',json.loads(self.s.candidate('1000')['profile']))
        self.assertIsNone(self.db.one("SELECT * FROM ewu2_processed_updates WHERE update_id='broken'"))
    def test_google_adapter_raw_strings_atomic_replacement_and_no_sheet_creation(self):
        self.register();rows=projection(self.s,self.owner)
        rows['Candidates'][1][1]='=IMPORTXML("https://example.invalid","x")'
        class Response:
            def raise_for_status(self):pass
            def json(self):return {'sheets':[{'properties':{'title':name,'sheetId':i}} for i,name in enumerate(TABS)]}
        class Session:
            def __init__(self):self.posts=[]
            def get(self,*a,**kw):return Response()
            def post(self,*a,**kw):self.posts.append(kw['json']);return Response()
        session=Session()
        with self.assertRaises(Denied):GoogleSheets('test',session)
        GoogleSheets('test',session,legal_approved=True,access_reviewed=True).replace(rows)
        data=session.posts[0];self.assertNotIn('formulaValue',json.dumps(data));self.assertIn('stringValue',json.dumps(data))
        self.assertEqual(sum('repeatCell' in r for r in data['requests']),9)
        self.assertNotIn('addSheet',json.dumps(data))

    def test_notification_uncertain_not_retried_and_withdrawal_blocks_queued_send(self):
        from ewu.worker import NotificationDelivery
        app=self.accepted()
        class Transport:
            def __init__(self):self.calls=0
            def send(self,*args,**kw):self.calls+=1;raise OSError('synthetic timeout')
        transport=Transport();handler=NotificationDelivery(self.s,transport)
        worker=Worker(self.s,{'notification':handler})
        worker.run_one();self.assertEqual(transport.calls,1)
        self.assertEqual(self.db.one("SELECT status FROM ewu2_outbox WHERE topic='notification'")['status'],'uncertain')
        self.now+=timedelta(hours=1);self.assertFalse(worker.run_one());self.assertEqual(transport.calls,1)
        self.s.enqueue('notification',app,'second',{'template':'follow_up'})
        self.s.rights(self.candidate,'withdraw');worker.run_one();self.assertEqual(transport.calls,1)
    def test_vacancy_import_preserves_partner_confirmation_and_detects_stale(self):
        from ewu.vacancies import import_rows
        record={'external_id':'test-1','data':self.conditions(),'confirmed_at':self.now.isoformat(),'expires_at':(self.now+timedelta(days=2)).isoformat()}
        with self.assertRaises(Denied):import_rows(self.s,self.owner,self.partner,[record])
        result=import_rows(self.s,self.owner,self.partner,[record],source_reviewed=True)
        self.assertEqual(result['imported'],[self.vacancy])
        self.now+=timedelta(days=4)
        self.assertEqual(import_rows(self.s,self.owner,self.partner,[record],source_reviewed=True)['needs_confirmation'],['test-1'])
        self.assertEqual(self.db.one('SELECT status FROM ewu2_vacancies')['status'],'NEEDS_CONFIRMATION')
    def test_finance_invoice_attestation_and_private_quality_feedback(self):
        app=self.started()
        commission=self.s.commission(self.owner,app,'hourly',125,10,'PLN','TEST-CONTRACT','TEST-PERIOD')
        self.assertEqual(self.db.one('SELECT amount_minor FROM ewu2_commissions')['amount_minor'],1250)
        with self.assertRaises(Denied):self.s.record_payment(self.owner,commission,'TEST')
        self.s.invoice(self.owner,commission,'2026-11-01','2026-11-15')
        self.s.record_payment(self.owner,commission,'TEST independently verified reference')
        self.s.record_payment(self.owner,commission,'TEST independently verified reference')
        self.assertEqual(self.db.one('SELECT payment_status FROM ewu2_commissions')['payment_status'],'PAID')
        report=self.s.quality(self.candidate,app,{'conditions_match':False,'needs_help':True})
        self.assertIsNotNone(report)
        with self.assertRaises(Denied):self.s.quality(self.partner_actor,app,{'needs_help':False})
        with self.assertRaises(Denied):self.s.commission(self.owner,app,'hourly',125,11,'PLN','TEST-CONTRACT','TEST-PERIOD')
    def test_audit_verification_privacy_evidence_and_retention_planner(self):
        self.register();self.s.rights(self.candidate,'withdraw')
        self.assertTrue(self.s.verify_audit(self.owner))
        self.assertEqual(self.db.one("SELECT decision FROM ewu2_privacy_records WHERE event='rights'")['decision'],'withdraw')
        with self.assertRaises(Denied):self.s.verify_audit(self.candidate)
        with self.assertRaises(Exception):self.db.execute("DELETE FROM ewu2_audit_events")
        self.now+=timedelta(days=8)
        plan=self.s.retention_plan(self.owner)
        self.assertEqual(len(plan['expired_candidate_ids']),1);self.assertFalse(plan['automatic_erasure_enabled'])
    def test_webhook_secret_and_staging_commands_default_to_no_io(self):
        from ewu.security import verify_webhook
        from ewu.manage import main as manage
        from ewu.worker_main import main as worker_main
        import contextlib,io
        secret='synthetic-webhook-secret-32-characters'
        verify_webhook({'X-Telegram-Bot-Api-Secret-Token':secret},secret)
        for headers in [{},{'X-Telegram-Bot-Api-Secret-Token':'invalid'}]:
            with self.assertRaises(Denied):verify_webhook(headers,secret)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(manage(['migrate']),0)
            self.assertEqual(worker_main([]),0)
    def test_paid_provider_not_called_without_budget_even_if_switch_enabled(self):
        self.register();self.s.ai_switch(self.owner,True)
        class Provider:
            def rank(self,*args,**kwargs):raise AssertionError('must not be invoked')
        self.assertEqual(RecruitmentAI(self.s,Provider(),False,10,1).choose(self.candidate,'unapproved')['mode'],'fallback')
    def test_existing_bot_routes_to_v2_only_when_explicitly_injected(self):
        from bot import create_bot
        class Bot:
            def __init__(self):self.messages=[]
            def message_handler(self,**kwargs):
                def register(fn):self.handler=fn;return fn
                return register
            def callback_query_handler(self,**kwargs):
                def register(fn):self.callback=fn;return fn
                return register
            def send_message(self,chat,text,**kwargs):self.messages.append(text)
        fake=Bot();adapter=TelegramRecruitment(self.s)
        create_bot(None,'DOES_NOT_EXIST','DOES_NOT_EXIST',fake,backend=adapter)
        fake.handler(NS(chat=NS(id=1000,type='private'),from_user=NS(id=1000,is_bot=False,language_code='uk'),message_id=1,text='/start'))
        self.assertIn('Choose a language',fake.messages[0])

    def test_incomplete_profile_nudges_stop_and_do_not_create_applications(self):
        self.s.privacy(self.candidate,'uk','acknowledged',revision(self.p))
        identifier=self.s.begin_profile(self.candidate,'uk')
        self.assertEqual(self.s.begin_profile(self.candidate,'uk'),identifier)
        self.assertEqual(self.db.one("SELECT count(*) AS n FROM ewu2_followups WHERE status='pending'")['n'],1)
        for _ in range(3):
            self.now+=timedelta(hours=25);self.s.due_followups()
        self.assertEqual(self.s.candidate('1000')['status'],'ON_HOLD')
        self.assertEqual(self.db.one("SELECT count(*) AS n FROM ewu2_outbox WHERE dedupe_key LIKE 'profile-reminder:%'")['n'],2)
        self.assertEqual(self.db.one('SELECT count(*) AS n FROM ewu2_applications')['n'],0)
    def test_purpose_specific_optional_ui_and_withdrawal_does_not_block_core(self):
        self.p['optional_consents']={'ai_profile':{'legal_review_approved':True,'texts':{l:'SYNTHETIC voluntary purpose' for l in UI}}}
        self.register()
        adapter=TelegramRecruitment(self.s)
        with self.db.transaction():
            adapter.save_session('1000',{'lang':'uk'})
            screen=adapter.handle(self.candidate,'/consent','uk')[0]
        callback=screen['reply_markup']['inline_keyboard'][0][1]['callback_data']
        self.assertLessEqual(len(callback.encode()),64)
        with self.db.transaction():adapter.handle_callback(self.candidate,callback)
        self.assertTrue(self.s.allowed('1000'));self.assertEqual(self.db.one('SELECT granted FROM ewu2_consents')['granted'],0)
    def test_ai_consent_basis_enforced_independently_from_core_notice(self):
        self.p['ai_processing_basis']='consent';self.register();self.s.ai_switch(self.owner,True)
        class Provider:
            def rank(self,*args,**kwargs):raise AssertionError('No consent means no call')
        result=RecruitmentAI(self.s,Provider(),True,10,1).choose(self.candidate,'no-ai-consent')
        self.assertEqual(result['mode'],'fallback');self.assertTrue(self.s.allowed('1000'))
    def test_config_is_disabled_by_default_and_requires_verified_tls(self):
        from unittest.mock import patch
        from ewu.config import configured_backend,database_url
        with patch.dict('os.environ',{},clear=True):self.assertIsNone(configured_backend())
        with patch.dict('os.environ',{'EWU_DATABASE_URL':'postgresql://test.invalid/test?sslmode=disable'},clear=True):
            with self.assertRaises(Denied):database_url()
    def test_synthetic_backup_restore_preserves_identity_and_history(self):
        import sqlite3
        app=self.started();restored=sqlite3.connect(':memory:',isolation_level=None);restored.row_factory=sqlite3.Row
        self.addCleanup(restored.close)
        self.db.connection.backup(restored)
        other=Recruitment(Database(restored,'sqlite'),self.p,lambda:self.now)
        self.assertEqual(other.self_data(self.candidate)['applications'][0]['id'],app)
        self.assertTrue(other.verify_audit(self.owner))
        self.assertEqual(other.apply(self.candidate,self.vacancy),app)

    def test_policy_reload_requires_fresh_notice_and_missing_config_blocks_intake(self):
        import copy
        self.register();latest=copy.deepcopy(self.p)
        adapter=TelegramRecruitment(self.s,policy_loader=lambda:copy.deepcopy(latest))
        with self.db.transaction():adapter.save_session('1000',{'lang':'uk'})
        class Bot:
            def __init__(self):self.text=[]
            def send_message(self,chat,text,**kw):self.text.append(text)
        bot=Bot();latest['version']='synthetic-v3'
        message=NS(chat=NS(id=1000,type='private'),from_user=NS(id=1000,is_bot=False,language_code='uk'),message_id=42,text='/vacancies')
        adapter.message(message,bot)
        self.assertIn('synthetic-v3',bot.text[-1]);self.assertFalse(self.s.allowed('1000'))
        def unavailable():raise OSError('synthetic missing policy')
        adapter.policy_loader=unavailable;message.message_id=43;message.text='/profile';adapter.message(message,bot)
        self.assertFalse(self.s.policy['legal_review_approved'])
        self.assertEqual(self.db.one('SELECT count(*) AS n FROM ewu2_candidates')['n'],1)
    def test_restricted_profile_is_redacted_from_crm_projection(self):
        self.register();self.s.rights(self.candidate,'object')
        rows=projection(self.s,self.owner)
        self.assertEqual(rows['Candidates'][1][1:4],['','',''])
        self.assertNotIn('SYNTHETIC Candidate',json.dumps(rows))
        self.assertNotIn('+48123456789',json.dumps(rows))


if __name__=='__main__':unittest.main()
