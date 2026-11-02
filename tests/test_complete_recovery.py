import json
import sqlite3
import unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace as NS

from bot import create_bot
from operations import backup_database, inventory, snapshot_volume
from privacy.onboarding import Store, revision
from recruitment import Journey
from test_privacy import FakeBot, fixture


class CompleteRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.path=self.root/'policy.json';self.db=self.root/'privacy.sqlite3'
        self.p=fixture();self.path.write_text(json.dumps(self.p))
        self.fake=FakeBot();create_bot(None,self.path,self.db,self.fake)

    def message(self,text):
        return NS(text=text,chat=NS(id=42,type='private'),from_user=NS(id=42,is_bot=False,language_code='uk'))

    def click(self,data):
        self.fake.callback(NS(id='cb',data=data,message=self.message(''),from_user=NS(id=42)))

    def onboard(self):
        self.fake.handle(self.message('/start'));self.click('lang:uk')
        self.click('p:'+revision(self.p)+':uk:yes')

    def form(self):
        for value in ['👷 Шукаю роботу','SYNTHETIC NAME','SYNTHETIC CITY','+48000000000','SYNTHETIC WORK']:
            self.fake.handle(self.message(value))

    def test_forged_ack_requires_prior_presentation_and_optional_processing_stays_off(self):
        self.click('p:'+revision(self.p)+':uk:yes')
        with sqlite3.connect(self.db) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM privacy_events WHERE action='acknowledged'").fetchone()[0],0)
            self.assertEqual(db.execute("SELECT count(*) FROM privacy_events WHERE action='presented'").fetchone()[0],1)
        self.click('p:'+revision(self.p)+':uk:yes');self.form()
        s=Store(self.db,self.p)
        try:self.assertIs(Journey(s).crm_batch()[0]['future_recruitment_consent'],False)
        finally:s.close()

    def test_same_form_has_one_application_one_identity_and_one_outbox_event(self):
        self.onboard();self.form();self.form()
        with sqlite3.connect(self.db) as db:
            for table in ['applications','candidate_identity','candidate_journey','crm_outbox']:
                self.assertEqual(db.execute('SELECT count(*) FROM '+table).fetchone()[0],1)

    def test_rights_survive_restart_and_loss_of_policy_configuration(self):
        self.onboard();self.form();self.path.unlink()
        fake=FakeBot();create_bot(None,self.path,self.db,fake)
        fake.handle(self.message('/my_data'));self.assertIn('SYNTHETIC NAME',fake.sent[-1][1])
        fake.handle(self.message('/restrict'));fake.handle(self.message('/delete_data'))
        with sqlite3.connect(self.db) as db:
            self.assertEqual(set(r[0] for r in db.execute('SELECT kind FROM data_requests')),{'restriction','erasure'})
        fake.handle(self.message('👷 Шукаю роботу'))
        self.assertIn('недоступне',fake.sent[-1][1])

    def test_presentation_does_not_revoke_existing_acknowledgement(self):
        self.onboard();self.fake.handle(self.message('/privacy'))
        s=Store(self.db,self.p)
        try:self.assertTrue(s.allowed(42))
        finally:s.close()

    def test_rights_commands_are_durable_idempotent_and_identity_scoped(self):
        self.onboard();self.form()
        for text in ['/correct city SYNTHETIC NEW CITY','/correct city SYNTHETIC NEW CITY','/export_data','/object']:
            self.fake.handle(self.message(text))
        s=Store(self.db,self.p)
        try:
            self.assertEqual(s.db.execute('SELECT count(*) FROM data_requests').fetchone()[0],3)
            self.assertFalse(s.allowed(42))
            self.assertEqual(Journey(s).export_own(43)['applications'],[])
        finally:s.close()

    def test_online_backup_and_restore_preserve_wal_and_do_not_overwrite(self):
        with sqlite3.connect(self.db) as db:
            db.execute('PRAGMA journal_mode=WAL');db.execute('CREATE TABLE sample(value)')
            db.execute("INSERT INTO sample VALUES('SYNTHETIC')");db.commit()
            target=self.root/'backups'/'first.sqlite3'
            result=backup_database(self.db,target);self.assertEqual(result['integrity'],'ok')
            with sqlite3.connect(target) as backup:self.assertEqual(backup.execute('SELECT * FROM sample').fetchall(),[('SYNTHETIC',)])
            with self.assertRaises(FileExistsError):backup_database(self.db,target)
            restored=self.root/'restore.sqlite3';backup_database(target,restored)
            self.assertEqual(restored.stat().st_mode & 0o777,0o600)

    def test_volume_snapshot_does_not_copy_secrets_or_old_backups(self):
        with sqlite3.connect(self.db) as db:db.execute('CREATE TABLE sample(value)')
        (self.root/'secret.json').write_text('DO NOT COPY')
        result=snapshot_volume(self.root,self.root/'backups'/'checkpoint')
        self.assertEqual(len(result['databases']),1)
        self.assertFalse((self.root/'backups'/'checkpoint'/'secret.json').exists())
        self.assertEqual(inventory(self.root)[0]['tables']['sample'],['value'])

    def test_retention_preserves_external_erasure_reference_and_removes_form_fields(self):
        now=datetime(2026,11,2,tzinfo=timezone.utc)
        s=Store(self.db,self.p,clock=lambda:now)
        try:
            j=Journey(s);s.record(42,'acknowledged','uk');s.begin_intake(42,'candidate')
            aid=s.save_answer(42,'name','SYNTHETIC TO EXPIRE',completed=True)
            with s.db:s.db.execute("UPDATE crm_outbox SET status='sent'")
            now+=timedelta(days=8);j.cleanup()
            self.assertEqual(s.db.execute('SELECT data FROM applications WHERE id=?',(aid,)).fetchone()[0],'{}')
            self.assertEqual(s.db.execute('SELECT application_id FROM external_erasure_holds').fetchone()[0],aid)
            self.assertEqual(j.crm_batch(),[])
        finally:s.close()


if __name__=='__main__':unittest.main()
