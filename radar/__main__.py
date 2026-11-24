"""Explicit commands: server, import-maxhr, backup, restore and password-hash."""
import argparse
import getpass
import json
import logging
import os
import sqlite3
import threading
from datetime import datetime,timezone,timedelta
from pathlib import Path
from .core import Settings,Radar,dump,now

def import_maxhr(radar):
    from maxhr import download,parse_xlsx,enrich_job
    from concurrent.futures import ThreadPoolExecutor
    snapshot=parse_xlsx(download())
    with ThreadPoolExecutor(max_workers=4) as pool:jobs=list(pool.map(enrich_job,snapshot['vacancies']))
    with radar.connect() as db:
        for job in jobs:
            public=dict(title=job['name'],city=job['city'],description=job.get('description') or '',pay=job.get('salary') or '',schedule=job.get('schedule') or '',hours=job['hours'],housing=job.get('housing_details') or job['housing'],transport=job.get('transport_details') or job['transport'],bonuses=job['bonuses'],places=job['places'],requirements=[],job_type=job['job_type'])
            # Import never overwrites a reviewed public vacancy or silently publishes source changes.
            db.execute('INSERT OR IGNORE INTO vacancies(id,public_json,updated_at) VALUES(?,?,?)',(job['id'],dump(public),now()))
            db.execute('INSERT INTO vacancy_private(vacancy_id,notes,source_json) VALUES(?,?,?) ON CONFLICT(vacancy_id) DO UPDATE SET source_json=excluded.source_json',(job['id'],'Умови ще не погоджені для публікації. '+' '.join(job['issues']),dump(job)))
        for i,terms in enumerate(snapshot['commissions']):
            db.execute('INSERT INTO projects(id,title,commission_json) VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET title=excluded.title,commission_json=excluded.commission_json',('maxhr-'+str(i),terms['project'],dump(terms)))
        radar.audit(db,'source_imported',None,'operator')
    return dict(drafts=len(jobs),projects=len(snapshot['commissions']),public=len(radar.jobs()))

def restore(backup,destination):
    backup=Path(backup).resolve();destination=Path(destination).resolve()
    if destination.exists():raise ValueError('Restore only to a new destination; never overwrite a live database')
    if not backup.is_file():raise ValueError('Backup missing')
    source=sqlite3.connect(f'file:{backup}?mode=ro',uri=True)
    try:
        if source.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Backup integrity failed')
        destination.parent.mkdir(parents=True,exist_ok=True,mode=0o700);target=sqlite3.connect(destination)
        try:
            source.backup(target)
            if target.execute('PRAGMA integrity_check').fetchone()[0]!='ok' or target.execute('PRAGMA foreign_key_check').fetchall():raise ValueError('Restore validation failed')
        finally:target.close()
    finally:source.close()
    os.chmod(destination,0o600)
    return str(destination)

def background(radar,stop):
    while not stop.is_set():
        try:
            radar.cleanup()
            directory=radar.settings.database.parent/'radar_backups'
            stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
            radar.backup(directory/('radar-'+stamp+'.sqlite3'))
            days=min(radar.settings.retention or 7,7)
            cutoff=datetime.now(timezone.utc).timestamp()-days*86400
            for file in directory.glob('radar-*.sqlite3'):
                if file.stat().st_mtime<cutoff:file.unlink()
            logging.info('radar_backup_verified')
        except Exception as error:logging.error('radar_maintenance_failed type=%s',type(error).__name__)
        stop.wait(3600)

def poll(radar):
    import telebot
    from polling_lock import acquire
    from .telegram import create_bot
    # Same shared-volume lock as the existing EWU runtime; opt-in only.
    lock=Path(os.environ.get('PRIVACY_DB_PATH','/data/ewu/privacy.sqlite3')).parent/'polling.lock'
    lock.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    telebot.logger.disabled=True
    try:
        with acquire(lock):
            bot=create_bot(radar)
            identity=bot.get_me();hook=bot.get_webhook_info()
            if (identity.username or '').casefold()!='ewu_jobs_bot' or hook.url:raise ValueError('Telegram identity or webhook does not match')
            logging.info('radar_telegram_verified')
            while True:
                try:bot.polling(non_stop=False,timeout=35,long_polling_timeout=30,allowed_updates=['message','callback_query'])
                except telebot.apihelper.ApiTelegramException as error:
                    logging.error('radar_telegram_error code=%s',error.error_code)
                    if error.error_code in (401,409):return
                except Exception as error:logging.error('radar_polling_failed type=%s',type(error).__name__)
    except Exception as error:logging.error('radar_telegram_blocked type=%s code=%s',type(error).__name__,getattr(error,'error_code','none'))

def main():
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=['serve','import-maxhr','backup','restore','password-hash']);parser.add_argument('--output');parser.add_argument('--input');args=parser.parse_args()
    if args.command=='password-hash':
        from .security import password_hash
        password=getpass.getpass('New recruiter password (12+ characters): ')
        if password!=getpass.getpass('Repeat password: '):raise SystemExit('Passwords differ')
        print(password_hash(password));return
    if args.command=='restore':print(restore(args.input,args.output));return
    radar=Radar(Settings())
    if args.command=='import-maxhr':print(json.dumps(import_maxhr(radar)));return
    if args.command=='backup':print(radar.backup(args.output));return
    # The web cabinet can be reviewed with intake and polling disabled.
    from .api import create_app
    import uvicorn
    stop=threading.Event();threading.Thread(target=background,args=(radar,stop),daemon=True).start()
    if radar.settings.bot_enabled:threading.Thread(target=poll,args=(radar,),daemon=True).start()
    logging.basicConfig(level=logging.INFO,format='%(levelname)s %(message)s')
    try:uvicorn.run(create_app(radar.settings),host='0.0.0.0',port=int(os.environ.get('PORT','8000')),workers=1,access_log=False,proxy_headers=True,forwarded_allow_ips=os.environ.get('RADAR_TRUSTED_PROXY','127.0.0.1'))
    finally:stop.set()

if __name__=='__main__':main()
