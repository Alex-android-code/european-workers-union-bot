"""One-time, consistent SQLite backup before this release starts any workers."""
import hashlib
import json
import os
import sqlite3
from pathlib import Path
from maxhr import now

RELEASE='maxhr-complete-20261124-v1'
def snapshot(root):
    root=Path(root);target=root/'recovery'/RELEASE
    marker=target/'manifest.json'
    if marker.exists():return json.loads(marker.read_text())
    target.mkdir(parents=True,exist_ok=True,mode=0o700)
    files=[]
    for source in root.rglob('*'):
        if not source.is_file() or source.is_symlink() or target.parent in source.parents:continue
        with source.open('rb') as stream:magic=stream.read(16)
        if magic!=b'SQLite format 3\x00':continue
        relative=str(source.relative_to(root));name=hashlib.sha256(relative.encode()).hexdigest()[:12]+'.sqlite3'
        destination=target/name
        old=sqlite3.connect(f'file:{source}?mode=ro',uri=True);new=sqlite3.connect(destination)
        try:
            old.backup(new)
            if new.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise RuntimeError('Backup verification failed')
        finally:old.close();new.close()
        os.chmod(destination,0o600)
        files.append(dict(original=relative,backup=name,bytes=destination.stat().st_size,sha256=hashlib.sha256(destination.read_bytes()).hexdigest()))
    result=dict(release=RELEASE,created_at=now(),databases=files)
    temp=target/'manifest.tmp';temp.write_text(json.dumps(result,indent=2));os.chmod(temp,0o600);temp.replace(marker)
    return result
