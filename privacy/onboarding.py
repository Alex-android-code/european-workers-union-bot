import hashlib
import json
import os
from pathlib import Path
import sqlite3
import uuid
from datetime import datetime, timezone, timedelta
from urllib.parse import urlsplit

LANGUAGES = ('uk', 'pl', 'ru', 'en', 'de', 'es', 'pt')
# The legacy Node runtime has a separate catalogue. Python exposes exactly
# the seven languages requested for this recovery.
UI = {k:v for k,v in json.loads(Path(__file__).with_name('ui.json').read_text(encoding='utf-8')).items() if k in LANGUAGES}
for _lang,_extra in json.loads(Path(__file__).with_name('extra_ui.json').read_text(encoding='utf-8')).items():UI[_lang].update(_extra)
FIELDS = ('controller', 'contact', 'purposes', 'legal_basis', 'retention',
          'categories', 'sources', 'recipients', 'transfers', 'rights', 'complaint', 'provision', 'automated')


def load_policy(path, raw_json=None):
    policy = json.loads(raw_json if raw_json is not None else Path(path).read_text(encoding='utf-8'))
    if not isinstance(policy.get('version'), str) or not policy['version'].strip():
        raise ValueError('Missing policy version')
    if policy.get('core_legal_basis') not in ('art6_1_b', 'art6_1_c', 'art6_1_f'):
        raise ValueError('Core processing needs a reviewed non-consent basis')
    for key in ('audit_retention_days', 'application_retention_days'):
        days = policy.get(key)
        if type(days) is not int or not 1 <= days <= 3650:
            raise ValueError('Invalid retention')
    for lang in UI:
        notice = policy.get('notices', {}).get(lang, {})
        for field in (*FIELDS, 'policy_url'):
            if not isinstance(notice.get(field), str) or not notice[field].strip():
                raise ValueError('Incomplete privacy notice')
        url = urlsplit(notice['policy_url'])
        if url.scheme != 'https' or not url.hostname or url.username or url.password:
            raise ValueError('Invalid policy URL')
        if len(render(policy, lang)) > 3900:
            raise ValueError('Privacy notice too long')
    return policy


def revision(policy):
    # Content changes invalidate acknowledgement even if the operator forgets to bump version.
    raw = json.dumps(policy, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def render(policy, lang):
    ui, notice = UI[lang], policy['notices'][lang]
    lines = [ui['title'] + ' — ' + policy['version']]
    lines += [ui[field] + ': ' + notice[field] for field in FIELDS]
    return '\n\n'.join(lines + [ui['policy'] + ': ' + notice['policy_url'], ui['note']])


class Store:
    def __init__(self, path, policy, clock=None):
        self.policy = policy
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        # The dedicated directory must not be shared with other users/services.
        self.db = sqlite3.connect(path)
        self.db.execute('PRAGMA secure_delete=ON')
        os.chmod(path, 0o600)
        self.db.execute('CREATE TABLE IF NOT EXISTS privacy_events (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, action TEXT NOT NULL, revision TEXT NOT NULL, version TEXT NOT NULL, locale TEXT NOT NULL, notice TEXT NOT NULL, at TEXT NOT NULL)')
        self.db.execute('CREATE INDEX IF NOT EXISTS privacy_user ON privacy_events(user_id,id)')
        self.db.execute('CREATE TABLE IF NOT EXISTS deletion_requests (user_id INTEGER PRIMARY KEY, requested_at TEXT NOT NULL, status TEXT NOT NULL DEFAULT "pending")')
        self.db.execute('CREATE TABLE IF NOT EXISTS intake_sessions (user_id INTEGER PRIMARY KEY, kind TEXT NOT NULL, data TEXT NOT NULL, at TEXT NOT NULL)')
        self.db.execute('CREATE TABLE IF NOT EXISTS applications (id TEXT PRIMARY KEY, user_id INTEGER NOT NULL, kind TEXT NOT NULL, data TEXT NOT NULL, at TEXT NOT NULL)')
        self.db.execute('CREATE TABLE IF NOT EXISTS data_requests (id TEXT PRIMARY KEY,user_id INTEGER NOT NULL,kind TEXT NOT NULL,at TEXT NOT NULL,status TEXT NOT NULL DEFAULT "pending",details TEXT NOT NULL DEFAULT "{}")')
        self.db.execute('CREATE TABLE IF NOT EXISTS candidate_identity (user_id INTEGER PRIMARY KEY,candidate_id TEXT NOT NULL UNIQUE,created_at TEXT NOT NULL)')
        self.db.execute('CREATE TABLE IF NOT EXISTS user_locales (user_id INTEGER PRIMARY KEY,locale TEXT NOT NULL)')
        self.db.execute('CREATE TABLE IF NOT EXISTS external_erasure_holds (application_id TEXT PRIMARY KEY,requested_at TEXT NOT NULL,status TEXT NOT NULL DEFAULT "pending")')
        self.db.commit()

    def close(self):
        self.db.close()

    def set_locale(self,user_id,lang):
        if lang not in UI:raise ValueError('Unsupported language')
        with self.db:self.db.execute('INSERT INTO user_locales VALUES(?,?) ON CONFLICT(user_id) DO UPDATE SET locale=excluded.locale',(user_id,lang))

    def locale(self,user_id):
        row=self.db.execute('SELECT locale FROM user_locales WHERE user_id=?',(user_id,)).fetchone()
        return row[0] if row and row[0] in UI else None

    def candidate_id(self,user_id):
        with self.db:
            self.db.execute('INSERT OR IGNORE INTO candidate_identity VALUES(?,?,?)',(user_id,'EWU-'+uuid.uuid4().hex,self.clock().isoformat()))
        return self.db.execute('SELECT candidate_id FROM candidate_identity WHERE user_id=?',(user_id,)).fetchone()[0]

    def purge(self):
        cutoff = (self.clock() - timedelta(days=self.policy['audit_retention_days'])).isoformat()
        with self.db:
            self.db.execute('DELETE FROM privacy_events WHERE at < ?', (cutoff,))
            application_cutoff = (self.clock() - timedelta(days=self.policy['application_retention_days'])).isoformat()
            self.db.execute('DELETE FROM intake_sessions WHERE at < ?', (application_cutoff,))
            if self.db.execute("SELECT 1 FROM sqlite_master WHERE name='crm_outbox'").fetchone():
                # Preserve a resolvable erasure reference for confirmed external
                # copies. Do not silently orphan a Google row on local expiry.
                self.db.execute('''INSERT OR IGNORE INTO external_erasure_holds(application_id,requested_at)
                  SELECT a.id,? FROM applications a WHERE a.at < ? AND EXISTS
                  (SELECT 1 FROM crm_outbox o WHERE o.application_id=a.id AND o.status='sent')''',
                  (self.clock().isoformat(),application_cutoff))
                self.db.execute('''DELETE FROM applications WHERE at < ? AND id NOT IN
                  (SELECT application_id FROM external_erasure_holds WHERE status='pending')''',(application_cutoff,))
                self.db.execute("UPDATE applications SET data='{}' WHERE id IN (SELECT application_id FROM external_erasure_holds WHERE status='pending')")
            else:self.db.execute('DELETE FROM applications WHERE at < ?', (application_cutoff,))
            self.db.execute('''DELETE FROM candidate_identity WHERE created_at < ?
              AND user_id NOT IN (SELECT user_id FROM applications)
              AND user_id NOT IN (SELECT user_id FROM data_requests WHERE status='pending')''',(application_cutoff,))
        # Pending rights requests are never silently expired; operator must resolve them.

    def record(self, user_id, action, lang):
        if lang not in UI or action not in ('presented', 'acknowledged', 'declined', 'withdrawn', 'restricted', 'deletion_requested'):
            raise ValueError('Unknown privacy action')
        self.purge()
        previous=self.db.execute("SELECT action,revision FROM privacy_events WHERE user_id=? AND action!='presented' ORDER BY id DESC LIMIT 1",(user_id,)).fetchone()
        clear_intake=(action != 'presented' and (action != 'acknowledged' or previous != ('acknowledged', revision(self.policy))))
        with self.db:
            self.db.execute('INSERT INTO privacy_events(user_id,action,revision,version,locale,notice,at) VALUES(?,?,?,?,?,?,?)',
                            (user_id, action, revision(self.policy), self.policy['version'], lang,
                             render(self.policy, lang), self.clock().isoformat()))
            if clear_intake:
                self.db.execute('DELETE FROM intake_sessions WHERE user_id=?', (user_id,))
            if action == 'deletion_requested':
                self.db.execute('INSERT INTO deletion_requests(user_id,requested_at) VALUES(?,?) ON CONFLICT(user_id) DO NOTHING',
                                (user_id, self.clock().isoformat()))

    def request(self, user_id, kind, details=None):
        if kind not in ('rectification','restriction','portability','erasure','objection'):
            raise ValueError('Unsupported rights request')
        encoded=json.dumps(details or {},ensure_ascii=False,sort_keys=True)
        old=self.db.execute('SELECT id FROM data_requests WHERE user_id=? AND kind=? AND details=? AND status="pending"',(user_id,kind,encoded)).fetchone()
        if old:return old[0]
        request_id=str(uuid.uuid4())
        with self.db:
            self.db.execute('INSERT INTO data_requests(id,user_id,kind,at,details) VALUES(?,?,?,?,?)',
                            (request_id,user_id,kind,self.clock().isoformat(),encoded))
        return request_id

    def allowed(self, user_id):
        self.purge()
        row = self.db.execute("SELECT action,revision FROM privacy_events WHERE user_id=? AND action!='presented' ORDER BY id DESC LIMIT 1", (user_id,)).fetchone()
        pending = self.db.execute('SELECT 1 FROM deletion_requests WHERE user_id=? AND status="pending"', (user_id,)).fetchone()
        return not pending and row is not None and row == ('acknowledged', revision(self.policy))


    def begin_intake(self, user_id, kind):
        if not self.allowed(user_id):
            raise ValueError('Onboarding required')
        with self.db:
            self.db.execute('INSERT INTO intake_sessions(user_id,kind,data,at) VALUES(?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET kind=excluded.kind,data=excluded.data,at=excluded.at',
                            (user_id, kind, '{}', self.clock().isoformat()))

    def intake(self, user_id):
        row = self.db.execute('SELECT kind,data FROM intake_sessions WHERE user_id=?', (user_id,)).fetchone()
        return (row[0], json.loads(row[1])) if row else None

    def save_answer(self, user_id, field, value, completed=False):
        if not self.allowed(user_id):
            raise ValueError('Onboarding required')
        session = self.intake(user_id)
        if session is None:
            raise ValueError('No active intake')
        kind, data = session
        data[field] = value[:1000]
        with self.db:
            if completed:
                encoded=json.dumps(data,ensure_ascii=False,sort_keys=True)
                for old_id,old_data in self.db.execute('SELECT id,data FROM applications WHERE user_id=? AND kind=?',(user_id,kind)):
                    if json.loads(old_data)==data:
                        if self.db.execute("SELECT 1 FROM sqlite_master WHERE name='candidate_journey'").fetchone():
                            old=self.db.execute('SELECT policy_revision,status FROM candidate_journey WHERE application_id=?',(old_id,)).fetchone()
                            if old and (old[0]!=revision(self.policy) or old[1] in ('FINISHED','CLOSED','WITHDRAWN','REJECTED','NO_SHOW','DID_NOT_START')):continue
                        self.db.execute('DELETE FROM intake_sessions WHERE user_id=?',(user_id,))
                        return old_id
                self.db.execute('INSERT INTO applications(id,user_id,kind,data,at) VALUES(?,?,?,?,?)',
                                (application_id := str(uuid.uuid4()), user_id, kind, encoded, self.clock().isoformat()))
                self.db.execute('INSERT OR IGNORE INTO candidate_identity VALUES(?,?,?)',(user_id,'EWU-'+uuid.uuid4().hex,self.clock().isoformat()))
                if self.db.execute("SELECT 1 FROM sqlite_master WHERE name='candidate_journey'").fetchone():
                    locale=self.db.execute('SELECT locale FROM privacy_events WHERE user_id=? ORDER BY id DESC LIMIT 1',(user_id,)).fetchone()[0]
                    self.db.execute('INSERT INTO candidate_journey(application_id,policy_revision,locale,updated_at) VALUES(?,?,?,?)',
                                    (application_id,revision(self.policy),locale,self.clock().isoformat()))
                    self.db.execute('INSERT INTO journey_events(application_id,status,revision,actor,at) VALUES(?,?,?,?,?)',
                                    (application_id,'NEW',1,'candidate',self.clock().isoformat()))
                    self.db.execute('INSERT INTO crm_outbox(id,application_id,revision,kind) VALUES(?,?,?,?)',
                                    (str(uuid.uuid4()),application_id,1,'upsert'))
                self.db.execute('DELETE FROM intake_sessions WHERE user_id=?', (user_id,))
            else:
                self.db.execute('UPDATE intake_sessions SET data=?,at=? WHERE user_id=?',
                                (json.dumps(data, ensure_ascii=False), self.clock().isoformat(), user_id))
        return application_id if completed else None

