import hashlib
import json
import os
from pathlib import Path
import sqlite3
import uuid
from datetime import datetime, timezone, timedelta
from urllib.parse import urlsplit

UI = json.loads(Path(__file__).with_name('ui.json').read_text(encoding='utf-8'))
FIELDS = ('controller', 'controller_address', 'contact', 'purposes', 'legal_basis', 'retention',
          'recipients', 'transfers', 'rights', 'complaint', 'provision', 'automated', 'ai_use')


def load_policy(path):
    policy = json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(policy, dict) or not isinstance(policy.get('notices'), dict):
        raise ValueError('Invalid privacy configuration')
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
        if not isinstance(notice, dict):
            raise ValueError('Invalid privacy notice')
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
    if policy.get('effective_at'):
        lines.append(ui['effective_at'] + ': ' + policy['effective_at'])
    lines += [ui[field] + ': ' + notice[field] for field in FIELDS]
    return '\n\n'.join(lines + ['Polityka prywatności: ' + notice['policy_url'], ui['note']])


class Store:
    def __init__(self, path, policy, clock=None):
        self.policy = policy
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        # The dedicated directory must not be shared with other users/services.
        self.db = sqlite3.connect(path)
        os.chmod(path, 0o600)
        self.db.execute('CREATE TABLE IF NOT EXISTS privacy_events (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, action TEXT NOT NULL, revision TEXT NOT NULL, version TEXT NOT NULL, locale TEXT NOT NULL, notice TEXT NOT NULL, at TEXT NOT NULL)')
        self.db.execute('CREATE INDEX IF NOT EXISTS privacy_user ON privacy_events(user_id,id)')
        self.db.execute('CREATE TABLE IF NOT EXISTS deletion_requests (user_id INTEGER PRIMARY KEY, requested_at TEXT NOT NULL, status TEXT NOT NULL DEFAULT "pending")')
        self.db.execute('CREATE TABLE IF NOT EXISTS intake_sessions (user_id INTEGER PRIMARY KEY, kind TEXT NOT NULL, data TEXT NOT NULL, at TEXT NOT NULL)')
        self.db.execute('CREATE TABLE IF NOT EXISTS applications (id TEXT PRIMARY KEY, user_id INTEGER NOT NULL, kind TEXT NOT NULL, data TEXT NOT NULL, at TEXT NOT NULL)')
        self.db.commit()

    def close(self):
        self.db.close()

    def purge(self):
        cutoff = (self.clock() - timedelta(days=self.policy['audit_retention_days'])).isoformat()
        with self.db:
            self.db.execute('DELETE FROM privacy_events WHERE at < ?', (cutoff,))
            application_cutoff = (self.clock() - timedelta(days=self.policy['application_retention_days'])).isoformat()
            self.db.execute('DELETE FROM intake_sessions WHERE at < ?', (application_cutoff,))
            self.db.execute('DELETE FROM applications WHERE at < ?', (application_cutoff,))
        # Pending rights requests are never silently expired; operator must resolve them.

    def record(self, user_id, action, lang):
        if action not in ('acknowledged', 'declined', 'withdrawn', 'deletion_requested'):
            raise ValueError('Unknown privacy action')
        self.purge()
        with self.db:
            self.db.execute('INSERT INTO privacy_events(user_id,action,revision,version,locale,notice,at) VALUES(?,?,?,?,?,?,?)',
                            (user_id, action, revision(self.policy), self.policy['version'], lang,
                             render(self.policy, lang), self.clock().isoformat()))
            self.db.execute('DELETE FROM intake_sessions WHERE user_id=?', (user_id,))
            if action == 'deletion_requested':
                self.db.execute('INSERT INTO deletion_requests(user_id,requested_at) VALUES(?,?) ON CONFLICT(user_id) DO NOTHING',
                                (user_id, self.clock().isoformat()))

    def allowed(self, user_id):
        self.purge()
        row = self.db.execute('SELECT action,revision FROM privacy_events WHERE user_id=? ORDER BY id DESC LIMIT 1', (user_id,)).fetchone()
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
                self.db.execute('INSERT INTO applications(id,user_id,kind,data,at) VALUES(?,?,?,?,?)',
                                (str(uuid.uuid4()), user_id, kind, json.dumps(data, ensure_ascii=False), self.clock().isoformat()))
                self.db.execute('DELETE FROM intake_sessions WHERE user_id=?', (user_id,))
            else:
                self.db.execute('UPDATE intake_sessions SET data=?,at=? WHERE user_id=?',
                                (json.dumps(data, ensure_ascii=False), self.clock().isoformat(), user_id))
