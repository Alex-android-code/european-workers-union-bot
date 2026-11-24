"""Single-runtime startup; verify configuration without network using --check."""
import argparse
import json
import os
import re
import threading
from pathlib import Path
from privacy.onboarding import load_policy, Store
from recruitment import Journey
from crm_sync import config as crm_config, flush


def preflight(env):
 issues=[]
 if not env.get('TELEGRAM_TOKEN'):issues.append('TELEGRAM_TOKEN missing')
 if env.get('EWU_START_ALLOWED')!='1':issues.append('EWU_START_ALLOWED must equal 1')
 if env.get('EWU_MAINTENANCE','1')!='0':issues.append('EWU_MAINTENANCE must equal 0')
 policy_path=env.get('PRIVACY_CONFIG_FILE','')
 if env.get('EWU_PUBLIC_CATALOG') != '1' or env.get('MAXHR_INTAKE_ENABLED') == '1':
  try:load_policy(policy_path, env.get('PRIVACY_CONFIG_JSON'))
  except (OSError,ValueError,TypeError,KeyError):issues.append('Reviewed privacy policy missing or incomplete')
 if env.get('MAXHR_INTAKE_ENABLED') == '1' and env.get('MAXHR_PRIVACY_REVIEWED') != '1':issues.append('MaxHR privacy review required')
 try:crm=crm_config(env)
 except (ValueError,TypeError):issues.append('CRM configuration rejected');crm=None
 database=Path(env.get('PRIVACY_DB_PATH','/data/ewu/privacy.sqlite3'))
 if not database.is_absolute():issues.append('PRIVACY_DB_PATH must be absolute')
 if env.get('EWU_ADMIN_IDS') and not all(re.fullmatch(r'[1-9][0-9]{0,18}',x.strip()) for x in env['EWU_ADMIN_IDS'].split(',')):
  issues.append('EWU_ADMIN_IDS must contain numeric user IDs')
 return dict(ready=not issues,issues=issues,crm_enabled=crm is not None,ai_enabled=False,
             paid_api_calls=False,runtime='python',database=str(database))


def maintenance(stop,env):
 # A dedicated connection per thread; no Telegram or database payloads in logs.
 while not stop.wait(60):
  try:
   if env.get('EWU_PUBLIC_CATALOG')=='1' and not (env.get('PRIVACY_CONFIG_FILE') or env.get('PRIVACY_CONFIG_JSON')):continue
   policy=load_policy(env.get('PRIVACY_CONFIG_FILE',''),env.get('PRIVACY_CONFIG_JSON'))
   store=Store(env.get('PRIVACY_DB_PATH','/data/ewu/privacy.sqlite3'),policy)
   try:Journey(store).cleanup();flush(store,env)
   finally:store.close()
  except Exception:
   import logging
   logging.warning('maintenance_or_crm_unavailable')


def main():
 parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true');args=parser.parse_args()
 result=preflight(os.environ)
 if args.check:
  print(json.dumps(result,ensure_ascii=False,indent=2));return 0 if result['ready'] else 2
 if not result['ready']:
  print('EWU startup blocked: '+', '.join(result['issues']),flush=True);return 2
 lock=Path(result['database']).parent/'polling.lock';lock.parent.mkdir(parents=True,exist_ok=True)
 # Advisory OS lock; released on crash, works across deployments sharing volume.
 from polling_lock import acquire
 with acquire(lock):
  stop=threading.Event();worker=None
  try:
   from recovery import snapshot
   result_backup=snapshot(os.environ.get('EWU_BACKUP_ROOT','/data'))
   print('recovery_backup_verified databases='+str(len(result_backup['databases'])),flush=True)
   worker=threading.Thread(target=maintenance,args=(stop,dict(os.environ)),daemon=True);worker.start()
   from bot import run
   try:run()
   except Exception:
    print('EWU runtime unavailable; exception details suppressed to protect credentials',flush=True)
    return 2
  finally:
   stop.set()
   if worker:worker.join(timeout=12)
 return 0

if __name__=='__main__':raise SystemExit(main())
