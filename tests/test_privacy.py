import copy
import json
from pathlib import Path
from types import SimpleNamespace as NS
from tempfile import TemporaryDirectory
import unittest
from datetime import datetime, timedelta, timezone

from bot import create_bot
from privacy.onboarding import UI, FIELDS, Store, load_policy, revision, render


def fixture():
    # Synthetic test data only. Not a publishable legal policy.
    return {'version': 'test-v1', 'core_legal_basis': 'art6_1_b', 'audit_retention_days': 30, 'application_retention_days': 7,
            'notices': {lang: {**{k: 'TEST ONLY '+k for k in FIELDS},
                               'policy_url': 'https://example.invalid/privacy'} for lang in UI}}


class FakeBot:
    def __init__(self):
        self.sent = []
    def message_handler(self, **kwargs):
        def register(fn):
            self.handle = fn
            return fn
        return register
    def callback_query_handler(self, **kwargs):
        def register(fn):
            self.callback = fn
            return fn
        return register
    def send_message(self, chat_id, text, **kwargs):
        self.sent.append((chat_id, text, kwargs))
    def answer_callback_query(self, call_id):
        pass


class PrivacyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)/'policy.json'
        self.db = Path(self.tmp.name)/'events.sqlite'
        self.p = fixture()
        self.write()
        self.fake = FakeBot()
        create_bot(None, self.path, self.db, self.fake)
    def write(self):
        self.path.write_text(json.dumps(self.p), encoding='utf-8')
    def msg(self, text, user=42, kind='private'):
        return NS(text=text, chat=NS(id=user, type=kind), from_user=NS(id=user, language_code='uk', is_bot=False))
    def click(self, action='yes', key=None, user=42, lang='uk'):
        self.fake.callback(NS(id='test', data=f'p:{key or revision(self.p)}:{lang}:{action}',
                              message=self.msg('notice', user), from_user=NS(id=user)))
    def store(self):
        s=Store(self.db, self.p)
        self.addCleanup(s.close)
        return s
    def test_start_displays_five_notices_without_record_or_questionnaire(self):
        self.fake.handle(self.msg('/start'))
        self.assertEqual(len(self.fake.sent), len(UI))
        for lang, (_, text, options) in zip(UI, self.fake.sent):
            self.assertIn(UI[lang]['title'], text)
            self.assertIn('Polityka prywatności:', text)
            self.assertIn(UI[lang]['note'], text)
            self.assertNotIn('Please send your name', text)
            self.assertIn('inline_keyboard', options['reply_markup'].to_dict())
        self.assertFalse(self.store().allowed(42))
        self.assertEqual(self.store().db.execute('SELECT count(*) FROM privacy_events').fetchone()[0], 0)
    def test_acknowledgement_enables_menu_and_records_exact_text(self):
        self.click(lang='uz')
        s=self.store()
        self.assertTrue(s.allowed(42))
        row=s.db.execute('SELECT user_id,action,version,notice,at FROM privacy_events').fetchone()
        self.assertEqual(row[:4], (42,'acknowledged','test-v1',render(self.p,'uz')))
        self.assertTrue(datetime.fromisoformat(row[4]).tzinfo)
        self.assertIn('choose an option', self.fake.sent[-1][1])
    def test_pre_onboarding_text_never_saved_or_forwarded(self):
        self.fake.handle(self.msg('PRIVATE PASSPORT 12345'))
        s=self.store()
        self.assertFalse(s.allowed(42))
        self.assertEqual(s.db.execute('SELECT count(*) FROM privacy_events').fetchone()[0],0)
        self.assertNotIn('PRIVATE PASSPORT', repr(self.fake.sent))
    def test_decline_blocks_and_isolated_from_other_users(self):
        self.click('no')
        self.assertFalse(self.store().allowed(42))
        self.click(user=43)
        self.assertTrue(self.store().allowed(43))
        self.assertFalse(self.store().allowed(42))
    def test_version_and_content_changes_invalidate_and_old_buttons_fail(self):
        old=revision(self.p)
        self.click()
        self.p['notices']['pl']['retention']='CHANGED TEST ONLY'
        self.write()
        self.fake.handle(self.msg('👷 I’m looking for work'))
        self.assertFalse(self.store().allowed(42))
        self.click(key=old)
        self.assertFalse(self.store().allowed(42))
        self.click()
        self.assertTrue(self.store().allowed(42))
    def test_withdraw_and_deletion_request_block_reentry(self):
        self.click()
        self.fake.handle(self.msg('/withdraw'))
        self.assertFalse(self.store().allowed(42))
        self.click()
        self.fake.handle(self.msg('/delete_data'))
        self.click()
        s=self.store()
        self.assertFalse(s.allowed(42))
        self.assertEqual(s.db.execute('SELECT status FROM deletion_requests').fetchone()[0],'pending')
        self.fake.handle(self.msg('/delete_data'))
        self.assertEqual(s.db.execute('SELECT count(*) FROM deletion_requests').fetchone()[0],1)
    def test_missing_invalid_configuration_and_group_messages_fail_closed(self):
        self.p['notices']['ru']['controller']=''
        self.write()
        with self.assertRaises(ValueError): load_policy(self.path)
        self.fake.handle(self.msg('/start'))
        self.assertTrue(all('reply_markup' in item[2] for item in self.fake.sent))
        self.assertNotIn('callback_data',repr(self.fake.sent))
        self.fake.sent.clear()
        self.fake.handle(self.msg('/start',kind='group'))
        self.assertEqual(self.fake.sent,[])
    def test_expiry_invalidates_acknowledgement_and_private_db_permissions(self):
        now=datetime(2026,1,1,tzinfo=timezone.utc)
        s=Store(self.db,self.p,clock=lambda:now)
        self.addCleanup(s.close)
        s.record(42,'acknowledged','uk')
        now+=timedelta(days=31)
        self.assertFalse(s.allowed(42))
        self.assertEqual(self.db.stat().st_mode & 0o777,0o600)
    def test_no_application_text_persisted_even_after_acknowledgement(self):
        self.click()
        self.fake.handle(self.msg('SECRET QUESTIONNAIRE TEXT'))
        s=self.store()
        self.assertNotIn('SECRET QUESTIONNAIRE',repr(s.db.execute('SELECT * FROM privacy_events').fetchall()))
        self.assertIn('No application has been saved',self.fake.sent[-1][1])
    def test_media_and_foreign_callback_cannot_open_intake(self):
        self.fake.handle(self.msg(None))
        self.assertFalse(self.store().allowed(42))
        self.fake.callback(NS(id='foreign', data=f'p:{revision(self.p)}:uk:yes',
                              message=self.msg('notice', user=42), from_user=NS(id=43)))
        self.assertFalse(self.store().allowed(42))
        self.assertFalse(self.store().allowed(43))
    def test_old_version_and_missing_policy_file_fail_closed(self):
        self.click()
        self.p['version']='test-v2'
        self.write()
        self.fake.handle(self.msg('👷 I’m looking for work'))
        self.assertFalse(self.store().allowed(42))
        self.path.unlink()
        self.fake.sent.clear()
        self.fake.handle(self.msg('/start'))
        self.assertEqual(len(self.fake.sent),len(UI))
        self.assertNotIn('callback_data',repr(self.fake.sent))
    def test_selected_intake_is_saved_only_after_acknowledgement(self):
        self.fake.handle(self.msg('👷 I’m looking for work'))
        self.assertEqual(self.store().db.execute('SELECT count(*) FROM intake_sessions').fetchone()[0],0)
        self.click()
        self.fake.handle(self.msg('👷 I’m looking for work'))
        for text in ['TEST NAME', 'TEST CITY', 'invalid-phone']:
            self.fake.handle(self.msg(text))
        self.assertEqual(self.store().db.execute('SELECT count(*) FROM applications').fetchone()[0],0)
        self.fake.handle(self.msg('+48123456789'))
        self.fake.handle(self.msg('TEST PROFESSION'))
        s=self.store()
        rows=s.db.execute('SELECT data FROM applications').fetchall()
        self.assertEqual(len(rows),1)
        self.assertEqual(set(json.loads(rows[0][0])),{'name','city','phone','profession'})
        self.assertEqual(s.db.execute('SELECT count(*) FROM intake_sessions').fetchone()[0],0)
    def test_withdrawal_clears_partial_intake_and_policy_change_blocks_save(self):
        self.click()
        self.fake.handle(self.msg('👷 I’m looking for work'))
        self.fake.handle(self.msg('TEST NAME'))
        self.fake.handle(self.msg('/withdraw'))
        self.assertIsNone(self.store().intake(42))
        self.fake.handle(self.msg('TEST PHONE'))
        self.assertEqual(self.store().db.execute('SELECT count(*) FROM applications').fetchone()[0],0)
        with self.assertRaises(ValueError):self.store().begin_intake(42,'candidate')
    def test_application_and_partial_form_retention(self):
        now=datetime(2026,1,1,tzinfo=timezone.utc)
        s=Store(self.db,self.p,clock=lambda:now)
        self.addCleanup(s.close)
        s.record(42,'acknowledged','uk')
        s.begin_intake(42,'candidate')
        s.save_answer(42,'name','TEST',completed=True)
        s.begin_intake(42,'candidate')
        now+=timedelta(days=8)
        s.purge()
        self.assertEqual(s.db.execute('SELECT count(*) FROM applications').fetchone()[0],0)
        self.assertIsNone(s.intake(42))
    def test_url_and_retention_validation(self):
        self.path.write_text('[]')
        with self.assertRaises(ValueError):load_policy(self.path)
        for mutate in [lambda p:p.update(core_legal_basis='consent'),
                       lambda p:p.update(audit_retention_days=0),
                       lambda p:p['notices']['uk'].update(policy_url='http://example.invalid'),
                       lambda p:p.update(version='')]:
            self.p=fixture();mutate(self.p);self.write()
            with self.assertRaises(ValueError):load_policy(self.path)


if __name__=='__main__':unittest.main()
