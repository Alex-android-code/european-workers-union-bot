"""Rights over existing records remain available without enabling a new intake."""
import json
import sqlite3
from pathlib import Path
from maxhr import now


def handle_right(path,user,action):
    if not Path(path).is_file():return dict(applications=[],privacy_events=[])
    db=sqlite3.connect(path,timeout=15)
    try:
        tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if action in ('/withdraw','/delete_data'):
            with db:
                if 'intake_sessions' in tables:db.execute('DELETE FROM intake_sessions WHERE user_id=?',(user,))
                if 'crm_outbox' in tables and 'applications' in tables:
                    db.execute("UPDATE crm_outbox SET status='suppressed',last_error='processing_paused' WHERE application_id IN (SELECT id FROM applications WHERE user_id=?) AND status='pending'",(user,))
                if 'privacy_events' in tables:
                    old=db.execute('SELECT revision,version,locale,notice FROM privacy_events WHERE user_id=? ORDER BY id DESC LIMIT 1',(user,)).fetchone()
                    if old:db.execute('INSERT INTO privacy_events(user_id,action,revision,version,locale,notice,at) VALUES(?,?,?,?,?,?,?)',(user,'withdrawn' if action=='/withdraw' else 'deletion_requested',*old,now()))
                if action=='/delete_data':
                    db.execute('CREATE TABLE IF NOT EXISTS deletion_requests(user_id INTEGER PRIMARY KEY,requested_at TEXT NOT NULL,status TEXT NOT NULL DEFAULT "pending")')
                    db.execute('INSERT INTO deletion_requests(user_id,requested_at) VALUES(?,?) ON CONFLICT(user_id) DO NOTHING',(user,now()))
            return dict(request='recorded',external_copies='require_controller_review')
        applications=[]
        if 'applications' in tables:
            for r in db.execute('SELECT id,kind,data,at FROM applications WHERE user_id=?',(user,)):
                applications.append(dict(id=r[0],kind=r[1],data=json.loads(r[2]),created_at=r[3]))
        events=[]
        if 'privacy_events' in tables:
            events=[dict(action=r[0],version=r[1],locale=r[2],at=r[3]) for r in db.execute('SELECT action,version,locale,at FROM privacy_events WHERE user_id=? ORDER BY id',(user,))]
        statuses=[]
        if 'candidate_journey' in tables and 'applications' in tables:
            statuses=[dict(id=r[0],status=r[1],revision=r[2]) for r in db.execute('SELECT j.application_id,j.status,j.revision FROM candidate_journey j JOIN applications a ON a.id=j.application_id WHERE a.user_id=?',(user,))]
        return dict(applications=applications,privacy_events=events,statuses=statuses)
    finally:db.close()
