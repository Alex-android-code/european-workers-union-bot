import hashlib
import hmac
import json
import unittest
import uuid
from pathlib import Path
from tempfile import TemporaryDirectory

from crm_commands import apply_command, drain_notifications, exchange, import_commands
from privacy.onboarding import Store
from recruitment import Journey
from test_privacy import fixture


class CommandTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=Store(Path(self.tmp.name)/'db.sqlite3',fixture());self.addCleanup(self.store.close)
        self.j=Journey(self.store,[99]);self.store.record(42,'acknowledged','pl')
        self.store.begin_intake(42,'candidate');self.aid=self.store.save_answer(42,'name','SYNTHETIC',completed=True)
        self.command=dict(id=str(uuid.uuid4()),application_id=self.aid,status='FORM_COMPLETED',expected_revision=1,actor='99')

    def test_command_replay_is_atomic_and_notification_is_not_duplicated(self):
        first=apply_command(self.store,self.command,[99])
        self.assertEqual(first,apply_command(self.store,self.command,[99]))
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM notifications').fetchone()[0],1)
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM crm_commands').fetchone()[0],1)
        with self.assertRaises(ValueError):apply_command(self.store,{**self.command,'status':'UNDER_REVIEW'},[99])

    def test_unauthorized_stale_invalid_and_paused_commands_do_not_change_data(self):
        for changed,error in [({'actor':'42'},PermissionError),({'expected_revision':0},ValueError),({'status':'STARTED'},ValueError)]:
            with self.assertRaises(error):apply_command(self.store,{**self.command,**changed},[99])
        self.store.record(42,'restricted','pl')
        with self.assertRaises(PermissionError):apply_command(self.store,self.command,[99])
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM notifications').fetchone()[0],0)

    def test_localized_notification_sent_once(self):
        apply_command(self.store,self.command,[99]);sent=[]
        drain_notifications(self.store,lambda user,text:sent.append((user,text)))
        drain_notifications(self.store,lambda *args:self.fail('Duplicate notification'))
        self.assertEqual(len(sent),1);self.assertEqual(sent[0][0],42)
        self.assertIn('Formularz wypełniony',sent[0][1])

    def test_uncertain_delivery_is_held_instead_of_resent(self):
        apply_command(self.store,self.command,[99])
        def failed(*args):raise TimeoutError('SYNTHETIC SECRET')
        self.assertEqual(drain_notifications(self.store,failed)['uncertain'],1)
        self.assertEqual(drain_notifications(self.store,failed)['uncertain'],0)
        self.assertEqual(self.store.db.execute('SELECT state FROM notifications').fetchone()[0],'uncertain')

    def test_withdrawal_suppresses_queued_notification(self):
        apply_command(self.store,self.command,[99]);self.store.record(42,'withdrawn','pl')
        self.assertEqual(drain_notifications(self.store,lambda *args:self.fail('Must not send'))['sent'],0)

    def test_command_insert_failure_rolls_back_status_and_notification(self):
        self.store.db.execute("CREATE TRIGGER fail_command BEFORE INSERT ON crm_commands BEGIN SELECT RAISE(ABORT,'test'); END;")
        with self.assertRaises(Exception):apply_command(self.store,self.command,[99])
        self.assertEqual(self.j.own(42)[0]['revision'],1)
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM notifications').fetchone()[0],0)

    def test_exchange_requires_signed_matching_sheet_and_request_id(self):
        cfg=dict(url='https://script.google.com/macros/s/synthetic/exec',sheet_id='SYNTHETIC',secret='x'*40)
        def transport(req,timeout):
            incoming=json.loads(req.data);p=json.loads(incoming['payload'])
            body=dict(request_id=p['request_id'],result=[self.command],sheet_id='SYNTHETIC')
            body['signature']=hmac.new(cfg['secret'].encode(),json.dumps(body,sort_keys=True,separators=(',',':')).encode(),hashlib.sha256).hexdigest()
            class Response:
                def __enter__(self):return self
                def __exit__(self,*args):pass
                def read(self,n):return json.dumps(body).encode()
            return Response()
        self.assertEqual(exchange(cfg,'pull_status_commands',transport=transport),[self.command])
        with self.assertRaises(ValueError):exchange({**cfg,'sheet_id':'OTHER'},'pull_status_commands',transport=transport)
        with self.assertRaises(ValueError):exchange({**cfg,'secret':'OTHER'*10},'pull_status_commands',transport=transport)

    def test_bidirectional_import_requires_separate_explicit_enablement(self):
        self.assertFalse(import_commands(self.store,{})['enabled'])
        with self.assertRaises(ValueError):import_commands(self.store,dict(CRM_BIDIRECTIONAL_ENABLED='1'))


if __name__=='__main__':unittest.main()
