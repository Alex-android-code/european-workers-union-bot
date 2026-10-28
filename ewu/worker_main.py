"""Staging-only runner; production activation requires a separate reviewed change."""
import argparse
import os
import signal
import time
from .config import configured_backend
from .domain import Actor
from .worker import Worker,SheetsSync,NotificationDelivery
from .sheets import GoogleSheets


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--loop',action='store_true')
    args=parser.parse_args(argv)
    if not args.execute:
        print('DRY RUN: no connection, worker, Google API or Telegram delivery started')
        return 0
    if os.environ.get('EWU_ENVIRONMENT')!='staging':raise ValueError('Staging only')
    backend=configured_backend()
    if backend is None:raise ValueError('Explicit v2 opt-in required')
    service=backend.service
    current=service.db.one('SELECT current_database() AS name')['name']
    if not os.environ.get('EWU_EXPECTED_DATABASE') or current!=os.environ['EWU_EXPECTED_DATABASE']:
        raise ValueError('Database identity mismatch')
    handlers={}
    if service.policy.get('sheets_approved') is True and os.environ.get('EWU_SHEETS_ACCESS_REVIEWED')=='1':
        import google.auth
        from google.auth.transport.requests import AuthorizedSession
        credentials,_=google.auth.default(scopes=['https://www.googleapis.com/auth/spreadsheets'])
        sink=GoogleSheets(os.environ.get('GOOGLE_SHEETS_ID',''),AuthorizedSession(credentials),legal_approved=True,access_reviewed=True)
        sync=SheetsSync(service,sink,Actor(os.environ['EWU_SYNC_ACTOR_ID']),os.environ.get('EWU_CANDIDATE_CARD_ID'))
        handlers.update(sheets=sync,sheets_finance=sync)
    if os.environ.get('EWU_ALLOW_STAGING_NOTIFICATIONS')=='1':
        import requests
        token=os.environ['TELEGRAM_TOKEN']
        class Transport:
            def send(self,chat_id,text,idempotency_key):
                response=requests.post('https://api.telegram.org/bot'+token+'/sendMessage',json={'chat_id':chat_id,'text':text},timeout=20)
                response.raise_for_status()
                if not response.json().get('ok'):raise RuntimeError('Telegram rejected delivery')
        handlers['notification']=NotificationDelivery(service,Transport())
    # No guessed GreenWork/Operations destination: unknown integration jobs stay pending.
    if not handlers:raise ValueError('No reviewed transport configured')
    worker=Worker(service,handlers)
    stopping=False
    def stop(signum,frame):
        nonlocal stopping
        stopping=True
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    next_tick=0.0
    try:
        while not stopping:
            if time.monotonic()>=next_tick:
                backend.refresh_policy()
                service.legal()
                service.expire_vacancies()
                service.due_followups()
                next_tick=time.monotonic()+60
            worked=worker.run_one()
            if not args.loop:break
            if not worked:time.sleep(1)
    finally:service.db.close()
    return 0


if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception:raise SystemExit('worker_configuration_or_delivery_failed') from None
