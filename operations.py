"""Local SQLite backup, verification and non-destructive restore preparation.

No credentials or row contents are returned. Run inside the Railway container
to reach its mounted volume; running locally does not back up production.
"""
import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import uuid
from contextlib import closing


def backup_database(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if not source.is_file() or source == destination:
        raise ValueError('Existing source and distinct backup path required')
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if destination.exists():
        raise FileExistsError('Backup already exists')
    temporary = destination.with_name(destination.name + '.partial-' + uuid.uuid4().hex)
    try:
        with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True, timeout=30)) as src:
            with closing(sqlite3.connect(temporary)) as dst:
                src.backup(dst)
                if dst.execute('PRAGMA integrity_check').fetchone() != ('ok',):
                    raise ValueError('Backup integrity check failed')
        os.chmod(temporary, 0o600)
        with temporary.open('rb') as stream:
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
        return dict(source=str(source), backup=str(destination),
                    sha256=hashlib.sha256(destination.read_bytes()).hexdigest(),
                    bytes=destination.stat().st_size, integrity='ok')
    finally:
        temporary.unlink(missing_ok=True)


def snapshot_volume(root, destination):
    root, destination = Path(root).resolve(), Path(destination).resolve()
    if not root.is_dir():
        raise ValueError('Data volume unavailable')
    destination.mkdir(parents=True, exist_ok=False, mode=0o700)
    files=[]
    for path in sorted(root.rglob('*')):
        if not path.is_file() or path.is_symlink() or destination in path.parents:
            continue
        if any(part in ('backups', '.backups') for part in path.relative_to(root).parts):
            continue
        with path.open('rb') as stream:
            is_database = stream.read(16) == b'SQLite format 3\x00'
        if is_database:
            files.append(backup_database(path, destination/path.relative_to(root)))
    manifest=dict(created_at=datetime.now(timezone.utc).isoformat(), databases=files,
                  scope='SQLite files only; documents and policy secrets are not copied')
    target=destination/'manifest.json'
    target.write_text(json.dumps(manifest,indent=2),encoding='utf-8');os.chmod(target,0o600)
    return manifest


def inventory(root):
    result=[]
    for path in sorted(Path(root).rglob('*')):
        if not path.is_file() or path.is_symlink() or 'backups' in path.parts:
            continue
        with path.open('rb') as stream:
            if stream.read(16) != b'SQLite format 3\x00':
                continue
        with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)) as db:
            tables=[row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
            result.append(dict(path=str(path), bytes=path.stat().st_size,
                               integrity=db.execute('PRAGMA quick_check').fetchone()[0],
                               tables={name:[row[1] for row in db.execute('PRAGMA table_info('+ '"'+name.replace('"','""')+'"'+')')] for name in tables}))
    return result


def main():
    p=argparse.ArgumentParser();s=p.add_subparsers(dest='action',required=True)
    a=s.add_parser('inventory');a.add_argument('root')
    a=s.add_parser('backup');a.add_argument('root');a.add_argument('destination')
    a=s.add_parser('prepare-restore');a.add_argument('backup');a.add_argument('new_path')
    args=p.parse_args()
    if args.action=='inventory':out=inventory(args.root)
    elif args.action=='backup':out=snapshot_volume(args.root,args.destination)
    else:out=backup_database(args.backup,args.new_path)
    print(json.dumps(out,indent=2))


if __name__=='__main__':main()
