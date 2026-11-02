import hashlib
import hmac
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from crm_operational import flush_operational, projection
from recruitment import Journey
from privacy.onboarding import Store
from test_privacy import fixture


class OperationalTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=Store(Path(self.tmp.name)/'db.sqlite3',fixture());self.addCleanup(self.store.close)
        self.j=Journey(self.store);self.store.record(42,'presented','uk');self.store.record(42,'acknowledged','uk')
        self.store.begin_intake(42,'candidate');self.aid=self.store.save_answer(42,'name','SYNTHETIC',completed=True)
        self.env=dict(CRM_OPERATIONAL_ENABLED='1',CRM_V2_ENABLED='1',CRM_V2_REVIEWED='1',CRM_V2_URL='https://script.google.com/macros/s/synthetic/exec',CRM_V2_SECRET='x'*40,CRM_V2_SHEET_ID='syntheticSheetId1234567890')

    def sender(self,req,timeout):
        payload=json.loads(json.loads(req.data)['payload'])
        result=dict(application_id=payload['application_id'],revision=payload['revision'],ok=True)
        response=dict(request_id=payload['request_id'],sheet_id=self.env['CRM_V2_SHEET_ID'],result=result)
        response['signature']=hmac.new(self.env['CRM_V2_SECRET'].encode(),json.dumps(response,sort_keys=True,separators=(',',':')).encode(),hashlib.sha256).hexdigest()
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,n):return json.dumps(response).encode()
        return Response()

    def test_projection_matches_the_shared_workbook_schema(self):
        schema=json.loads(Path('crm/schema.json').read_text())['specs']
        p=projection(self.j,self.j.crm_batch()[0])
        self.assertEqual(len(p['candidate']),len(schema['Candidates']))
        self.assertEqual(len(p['application']),7)
        self.assertEqual(p['application'][1],p['candidate'][0])
        self.assertEqual({r[7] for r in p['privacy']},{'presented','acknowledged'})
        self.assertEqual(len(p['history'][0]),len(schema['Candidate Journey']))

    def test_delivery_verified_and_durable_retry_is_idempotent(self):
        self.assertEqual(flush_operational(self.store,self.env,self.sender)['sent'],1)
        self.assertEqual(flush_operational(self.store,self.env,lambda *a:self.fail('Duplicate'))['sent'],0)

    def test_outage_preserves_queue_without_logging_candidate_data(self):
        def outage(*args,**kwargs):raise RuntimeError('SYNTHETIC SECRET')
        self.assertEqual(flush_operational(self.store,self.env,outage)['failed'],1)
        row=self.store.db.execute('SELECT status,attempts,last_error FROM crm_outbox').fetchone()
        self.assertEqual(row,('pending',1,'operational_delivery_unconfirmed'))
        self.assertEqual(flush_operational(self.store,self.env,self.sender)['sent'],1)

    def test_reviewed_config_and_current_acknowledgement_are_required(self):
        self.assertFalse(flush_operational(self.store,{})['enabled'])
        with self.assertRaises(ValueError):flush_operational(self.store,dict(CRM_OPERATIONAL_ENABLED='1'))
        self.store.record(42,'withdrawn','uk')
        self.assertEqual(flush_operational(self.store,self.env,lambda *a:self.fail('Must not export'))['sent'],0)


if __name__=='__main__':unittest.main()
