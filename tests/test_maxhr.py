import io,json,os,sqlite3,unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace as NS
from unittest.mock import patch
from openpyxl import Workbook
from maxhr import Catalog,parse_xlsx,generate_ad
from maxhr_crm import SimpleForm,MaxHRCrm,STATUSES
from public_bot import create_public_bot,intake_enabled
from public_text import WORDS,LANGUAGES
from public_bot import MENU_KEYS
from privacy.onboarding import Store
from test_privacy import fixture,FakeBot
from existing_rights import handle_right
from recovery import snapshot
from railway_start import preflight

def workbook(status='Активная',salary='32,50 PLN brutto / 26,24 PLN netto',name='Synthetic Factory',city='Test City',places=5):
    w=Workbook();s=w.active;s.title='Offers'
    s.append(['ID','Статус предложения','Проект / заказчик','Город / местоположение','Кого мы ищем на работу:','Количество','Тип работы','ЗАРАБОТНАЯ ПЛАТА','Премии / доплаты','Часы / RBH','Жильё — ссылка на папку с фото и видео','Транспорт','Фотографии предприятия — ссылка','Офис (оформление)'])
    s.append([1,status,name,city,'М / Ж / П',places,'warehouse',salary,'200 PLN',180,'Test hostel','bus','',''])
    c=w.create_sheet('Commissions');c.append(['Проект','Стандартная комиссия','Условие выплаты','Image','Бонусная система','Гарантированная выплата','Примечания'])
    c.append(['Synthetic Factory','1000 zł за кандидата','100 RBH','','3+1','300 zł przy 24 RBH','Not confirmed as stackable'])
    out=io.BytesIO();w.save(out);return out.getvalue()

class Fake(FakeBot):
    def send_document(self,user,stream):self.sent.append((user,stream.read().decode(),{}))

class MaxHRTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.path=self.root/'catalog.sqlite3';self.cat=Catalog(self.path);self.addCleanup(self.cat.close)
        self.assertTrue(self.cat.sync(lambda:workbook()))
        self.db=self.root/'privacy.sqlite3';self.fake=Fake()
        self.bot=create_public_bot(None,self.path,self.db,env={},admins=[99],bot_client=self.fake);self.ui=self.bot.ewu_ui;self.addCleanup(self.ui.catalog.close)
    def msg(self,t,user=42,lang='uk',private=True):return NS(text=t,chat=NS(id=user,type='private' if private else 'group'),from_user=NS(id=user,is_bot=False,language_code=lang))
    def click(self,data,user=42):self.fake.callback(NS(id='synthetic',data=data,message=self.msg('',user),from_user=NS(id=user)))
    def test_live_shape_and_last_good_survives_failure_and_restart(self):
        before=self.cat.read()
        self.assertEqual(len(before['vacancies']),1);self.assertEqual(len(before['commissions']),1)
        def fail():raise OSError('SECRET NEVER LOG')
        self.assertFalse(self.cat.sync(fail));self.assertEqual(self.cat.read(),before)
        reopened=Catalog(self.path)
        try:self.assertEqual(reopened.read(),before)
        finally:reopened.close()
    def test_closed_and_paused_hidden_valid_empty_not_stale(self):
        for status in ('Закрыта','Приостановлено'):
            self.assertTrue(self.cat.sync(lambda:workbook(status)));self.assertEqual(self.cat.read()['vacancies'],[])
    def test_new_jobs_changes_and_stable_identity(self):
        jid=self.cat.read()['vacancies'][0]['id']
        self.cat.sync(lambda:workbook(salary='40,00 brutto / 32,00 netto',places=2))
        job=self.cat.read()['vacancies'][0]
        self.assertEqual(job['id'],jid);self.assertEqual(job['places'],2);self.assertEqual(job['pay_floor'],32)
        self.cat.sync(lambda:workbook(name='Another Factory'));self.assertNotEqual(self.cat.read()['vacancies'][0]['id'],jid)
    def test_malformed_source_retains_last_good(self):
        before=self.cat.read()
        for bad in (b'<html>login required</html>',b'PKbroken'):
            self.assertFalse(self.cat.sync(lambda:bad));self.assertEqual(self.cat.read(),before)
    def test_filters(self):
        self.assertEqual(len(self.cat.select(city='Test City',min_pay=26,housing=True,couples=True)),1)
        self.assertEqual(self.cat.select(city='No such city'),[]);self.assertEqual(self.cat.select(min_pay=30),[])
        self.assertEqual(self.cat.select(kind='production'),[])
    def test_image_salary_not_parsed_and_unknown_not_high_paid(self):
        self.cat.sync(lambda:workbook(salary='image.png'))
        job=self.cat.read()['vacancies'][0];self.assertEqual(job['salary'],'');self.assertTrue(job['issues']);self.assertEqual(self.cat.select(min_pay=24),[])
    def test_all_languages_all_menu_buttons_and_all_callbacks(self):
        for lang in LANGUAGES:
            self.fake.handle(self.msg('/start',lang=lang));self.click('lang:'+lang)
            for key in MENU_KEYS:
                self.fake.handle(self.msg(WORDS[lang][key],lang=lang));self.assertTrue(self.fake.sent[-1][1])
            jid=self.cat.read()['vacancies'][0]['id']
            for data in ('menu','list','filters','all','filter:city','filter:pay','filter:type','filter:housing','pay:26','type:unspecified','job:'+jid,'apply:'+jid,'cancel','garbage'):
                self.click(data)
                self.assertTrue(self.fake.sent[-1][1])
            for _,body,options in self.fake.sent:
                self.assertLessEqual(len(body),3500)
                kb=options.get('reply_markup')
                if kb:
                    for row in json.loads(kb.to_json()).get('inline_keyboard',[]):
                        for b in row:
                            if 'callback_data' in b:self.assertLessEqual(len(b['callback_data'].encode()),64)
            self.fake.sent.clear()
    def test_browsing_and_media_never_create_personal_db_or_store_input(self):
        for value in ('/start','/jobs','SYNTHETIC PRIVATE DATA',None):self.fake.handle(self.msg(value))
        self.assertFalse(self.db.exists())
        self.assertNotIn('SYNTHETIC PRIVATE DATA',repr(self.fake.sent))
        self.assertEqual(self.cat.db.execute('SELECT count(*) FROM catalog_sync').fetchone()[0],1)
    def test_group_and_foreign_callback_ignored(self):
        self.fake.handle(self.msg('/start',private=False));self.assertEqual(self.fake.sent,[])
        c=NS(id='x',data='lang:pl',message=self.msg('',42),from_user=NS(id=43));self.fake.callback(c);self.assertEqual(self.fake.sent,[])
    def test_admin_commands_denied_for_candidates(self):
        for command in ('/admin','/admin_stats','/admin_export','/admin_commissions','/admin_sync','/admin_ad x Facebook','/admin_status x EMPLOYED 1','/admin_finance x 0','/admin_payment x 1000 1000 1','/admin_history x'):
            self.fake.handle(self.msg(command));self.assertEqual(self.fake.sent[-1][1],WORDS['uk']['admin_denied'])
        self.assertNotIn('1000 zł',repr(self.fake.sent))
    def test_authorized_admin_stats_export_and_ads(self):
        for command in ('/admin','/admin_stats','/admin_export','/admin_commissions'):
            self.fake.handle(self.msg(command,user=99));self.assertTrue(self.fake.sent[-1][1])
        jid=self.cat.read()['vacancies'][0]['id']
        for platform in ('Telegram','Facebook','Instagram','Threads','WhatsApp'):
            self.fake.handle(self.msg('/admin_ad '+jid+' '+platform,user=99));body=self.fake.sent[-1][1]
            self.assertIn('?start=job_'+jid,body);self.assertNotIn('1000 zł',body)
            if platform=='Threads':self.assertLessEqual(len(body),500)
    def test_deep_link_opens_specific_job(self):
        job=self.cat.read()['vacancies'][0];self.fake.handle(self.msg('/start job_'+job['id']))
        self.assertIn(job['name'],self.fake.sent[-1][1])
    def test_intake_requires_both_switches_and_reviewed_policy(self):
        p=fixture();raw=json.dumps(p)
        for env in ({},{'MAXHR_INTAKE_ENABLED':'1'},{'MAXHR_INTAKE_ENABLED':'1','MAXHR_PRIVACY_REVIEWED':'1'},{'PRIVACY_CONFIG_JSON':raw}):self.assertFalse(intake_enabled(env))
        self.assertTrue(intake_enabled(dict(MAXHR_INTAKE_ENABLED='1',MAXHR_PRIVACY_REVIEWED='1',PRIVACY_CONFIG_JSON=raw)))
    def test_synthetic_form_no_prohibited_fields_documents_three_options(self):
        form=SimpleForm(dict(id='synthetic',documents=['passport','work_permit']))
        for answer in ('Test','Person','+48 123 456 789','yes','unknown'):done=form.answer(answer)
        self.assertTrue(done);self.assertEqual(set(form.data),{'first_name','last_name','phone','vacancy_id','passport','work_permit'})
        with self.assertRaises(ValueError):SimpleForm(dict(id='x',documents=['passport_number']))
        form=SimpleForm(dict(id='x',documents=['pesel']))
        for answer in ('Test','Person','+48123456789'):form.answer(answer)
        with self.assertRaises(ValueError):form.answer('12345678901')
    def reviewed(self):
        store=Store(self.db,fixture());self.addCleanup(store.close);store.record(42,'acknowledged','uk');return store
    def form(self):
        f=SimpleForm(dict(id='synthetic',documents=[]))
        for answer in ('Test','Person','+48123456789'):f.answer(answer)
        return f
    def test_crm_duplicate_status_history_finance_no_bonus_stacking(self):
        store=self.reviewed();crm=MaxHRCrm(store,[99]);form=self.form()
        with self.assertRaises(PermissionError):crm.submit(42,form,'uk')
        aid=crm.submit(42,form,'uk',enabled=True)
        with self.assertRaises(ValueError):crm.submit(42,form,'uk',enabled=True)
        for revision,status in enumerate(STATUSES[1:-1],1):crm.journey.transition(99,aid,status,revision)
        self.assertEqual(crm.statistics(99),{'COMMISSION_PAID':1})
        self.assertEqual(store.db.execute('SELECT count(*) FROM journey_events').fetchone()[0],9)
        with self.assertRaises(PermissionError):crm.statistics(42)
        terms=self.cat.read()['commissions'][0];balance=crm.terms(99,aid,terms)
        self.assertEqual(balance['expected'],100000);self.assertEqual(balance['paid'],0)
        balance=crm.payment(99,aid,100000,40000,balance['revision']);self.assertEqual(balance['debt'],60000)
        with self.assertRaises(ValueError):crm.payment(99,aid,100000,100001,balance['revision'])
        with self.assertRaises(PermissionError):crm.balance(42,aid)
        self.assertIn('COMMISSION_PAID,1',crm.export(99))
        terms['base']='900/700 Zł';self.assertIsNone(crm.terms(99,aid,terms)['expected'])
    def test_existing_data_rights_without_policy_keep_owner_isolation(self):
        store=self.reviewed();crm=MaxHRCrm(store,[99]);aid=crm.submit(42,self.form(),'uk',enabled=True)
        self.assertEqual(handle_right(self.db,43,'/my_data')['applications'],[])
        self.assertEqual(len(handle_right(self.db,42,'/my_data')['applications']),1)
        handle_right(self.db,42,'/delete_data');self.assertFalse(store.allowed(42));self.assertEqual(crm.journey.crm_batch(),[])
        self.assertEqual(store.db.execute('SELECT count(*) FROM deletion_requests').fetchone()[0],1)
    def test_snapshot_is_consistent_repeatable_and_database_survives_restart(self):
        store=self.reviewed();crm=MaxHRCrm(store,[99]);aid=crm.submit(42,self.form(),'uk',enabled=True)
        result=snapshot(self.root);self.assertEqual(len(result['databases']),2)
        self.assertEqual(snapshot(self.root),result)
        for item in result['databases']:
            backup=self.root/'recovery'/result['release']/item['backup']
            db=sqlite3.connect(backup)
            try:self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
            finally:db.close()
        other=Store(self.db,fixture())
        try:self.assertEqual(MaxHRCrm(other,[99]).journey.own(42)[0]['id'],aid)
        finally:other.close()
    def test_public_preflight_works_without_intake_policy_but_switch_does_not_bypass_review(self):
        env=dict(TELEGRAM_TOKEN='synthetic',EWU_START_ALLOWED='1',EWU_MAINTENANCE='0',EWU_PUBLIC_CATALOG='1',MAXHR_INTAKE_ENABLED='0')
        self.assertTrue(preflight(env)['ready'])
        self.assertFalse(preflight({**env,'MAXHR_INTAKE_ENABLED':'1'})['ready'])
    def test_synthetic_end_to_end_intake_enabled_and_withdrawal(self):
        self.ui.env.update(MAXHR_INTAKE_ENABLED='1',MAXHR_PRIVACY_REVIEWED='1',PRIVACY_CONFIG_JSON=json.dumps(fixture()))
        jid=self.cat.read()['vacancies'][0]['id'];self.click('apply:'+jid)
        from privacy.onboarding import revision
        self.click('consent:'+revision(fixture()))
        for answer in ('Test','Person','+48123456789'):self.fake.handle(self.msg(answer))
        own=handle_right(self.db,42,'/my_data')['applications'];self.assertEqual(len(own),1)
        self.assertEqual(set(own[0]['data']),{'first_name','last_name','phone','vacancy_id'})
        self.fake.handle(self.msg('/withdraw'));self.assertEqual(self.ui.sessions[42].get('form'),None)

if __name__=='__main__':unittest.main()
