"""Single-runtime startup; verify configuration without network using --check."""
import argparse
import json
import os
import re
import threading
import hashlib
from pathlib import Path
from privacy.onboarding import load_policy, Store
from recruitment import Journey
from crm_sync import config as crm_config, flush
from operations import snapshot_volume
from datetime import datetime, timezone
from crm_commands import import_commands, drain_notifications
from crm_operational import flush_operational


def preflight(env):
 issues=[]
 if not env.get('TELEGRAM_TOKEN'):issues.append('TELEGRAM_TOKEN missing')
 if env.get('EWU_START_ALLOWED')!='1':issues.append('EWU_START_ALLOWED must equal 1')
 if env.get('EWU_MAINTENANCE','1')!='0':issues.append('EWU_MAINTENANCE must equal 0')
 policy_path=env.get('PRIVACY_CONFIG_FILE','')
 try:load_policy(policy_path, env.get('PRIVACY_CONFIG_JSON'))
 except (OSError,ValueError,TypeError,KeyError):issues.append('Reviewed privacy policy missing or incomplete')
 try:crm=crm_config(env)
 except (ValueError,TypeError):issues.append('CRM configuration rejected');crm=None
 if crm is not None and env.get('CRM_EXTERNAL_RIGHTS_REVIEWED')!='1':
  issues.append('External erasure, retention and backup procedure requires review')
 database=Path(env.get('PRIVACY_DB_PATH','/data/ewu/privacy.sqlite3'))
 if not database.is_absolute():issues.append('PRIVACY_DB_PATH must be absolute')
 if env.get('EWU_ADMIN_IDS') and not all(re.fullmatch(r'[1-9][0-9]{0,18}',x.strip()) for x in env['EWU_ADMIN_IDS'].split(',')):
  issues.append('EWU_ADMIN_IDS must contain numeric user IDs')
 return dict(ready=not issues,polling_ready=not [i for i in issues if i!='Reviewed privacy policy missing or incomplete'],issues=issues,crm_enabled=crm is not None,ai_enabled=False,
             paid_api_calls=False,runtime='python',database=str(database))


def maintenance(stop,env):
 # A dedicated connection per thread; no Telegram or database payloads in logs.
 while not stop.wait(60):
  try:
   policy=load_policy(env.get('PRIVACY_CONFIG_FILE',''),env.get('PRIVACY_CONFIG_JSON'))
   store=Store(env.get('PRIVACY_DB_PATH','/data/ewu/privacy.sqlite3'),policy)
   try:
    Journey(store).cleanup()
    if env.get('CRM_OPERATIONAL_ENABLED')=='1':flush_operational(store,env)
    else:flush(store,env)
    if env.get('CRM_BIDIRECTIONAL_ENABLED')=='1':
     import_commands(store,env)
     import telebot
     telebot.logger.disabled=True
     drain_notifications(store,telebot.TeleBot(env['TELEGRAM_TOKEN'],threaded=False).send_message)
   finally:store.close()
  except Exception:
   import logging
   logging.warning('maintenance_or_crm_unavailable')


def main():
 parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true');args=parser.parse_args()
 result=preflight(os.environ)
 if args.check:
  print(json.dumps(result,ensure_ascii=False,indent=2));return 0 if result['ready'] else 2
 if not result['polling_ready']:
  print('EWU startup blocked: '+', '.join(result['issues']),flush=True);return 2
 lock=Path(result['database']).parent/'polling.lock';lock.parent.mkdir(parents=True,exist_ok=True)
 # Advisory OS lock; released on crash, works across deployments sharing volume.
 from polling_lock import acquire
 with acquire(lock):
  # Snapshot all SQLite files on the EWU volume before opening/migrating them.
  root=Path(os.environ.get('RAILWAY_VOLUME_MOUNT_PATH',os.environ.get('EWU_DATA_DIR',str(lock.parent))))
  # One migration checkpoint per code release. Creating a full copy on every
  # crash/restart would exhaust a small Railway volume.
  code=b''.join((Path(__file__).parent/name).read_bytes() for name in ('railway_start.py','bot.py','recruitment.py','crm_operational.py','crm_commands.py','operations.py','privacy/onboarding.py','privacy/ui.json','privacy/extra_ui.json'))
  release=hashlib.sha256(code).hexdigest()[:20]
  backup=root/'backups'/('before-release-'+release)
  if (backup/'manifest.json').is_file():manifest=json.loads((backup/'manifest.json').read_text())
  else:manifest=snapshot_volume(root,backup)
  print('startup_backup_verified databases='+str(len(manifest['databases'])),flush=True)
  if not result['ready']:print('collection_blocked privacy_configuration_required',flush=True)
  print('polling_starting runtime=python crm='+str(result['crm_enabled']).lower(),flush=True)
  stop=threading.Event();worker=threading.Thread(target=maintenance,args=(stop,dict(os.environ)),daemon=True);worker.start()
  try:
   from bot import run
   run()
  finally:stop.set();worker.join(timeout=12)
 return 0

if __name__=='__main__':raise SystemExit(main())
