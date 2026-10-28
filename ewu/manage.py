"""Reviewed staging tooling. Dry-run is default; never invoked by bot startup."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess

from .config import database_url
from .storage import ROOT


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument('operation',choices=['migrate','backup','restore-check','bootstrap-owner'])
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--expected-db')
    parser.add_argument('--artifact',type=Path)
    parser.add_argument('--owner-id')
    args=parser.parse_args(argv)
    if not args.execute:
        print('DRY RUN: staging only; require explicit execution, expected database and reviewed backup/target.')
        return 0
    if os.environ.get('EWU_ENVIRONMENT')!='staging' or not args.expected_db:
        raise ValueError('Staging environment and exact database name required')
    import psycopg
    dsn=database_url()
    with psycopg.connect(dsn) as connection:
        actual=connection.execute('SELECT current_database()').fetchone()[0]
        if actual!=args.expected_db:
            raise ValueError('Database identity mismatch')
        if args.operation=='backup':
            if args.artifact is None:raise ValueError('Artifact path required')
            # Exclusive creation: do not overwrite a backup or existing user file.
            fd=os.open(args.artifact,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            try:
                with os.fdopen(fd,'wb') as output:
                    result=subprocess.run(['pg_dump','--format=custom','--no-owner','--no-privileges'],stdout=output,stderr=subprocess.PIPE,
                                          env={**os.environ,'PGDATABASE':dsn},check=False)
                if result.returncode:raise RuntimeError('Backup command failed; inspect restricted operator logs')
                digest=hashlib.sha256(args.artifact.read_bytes()).hexdigest()
                metadata={'source_database':actual,'sha256':digest,'created_at':datetime.now(timezone.utc).isoformat(),'format':'pg_dump_custom'}
                manifest=args.artifact.with_suffix(args.artifact.suffix+'.manifest.json')
                with os.fdopen(os.open(manifest,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'w') as handle:
                    json.dump(metadata,handle)
            except BaseException:
                # Keep failed artifacts for operator review; never claim them as usable backups.
                raise
        elif args.operation=='restore-check':
            if args.artifact is None:raise ValueError('Backup required')
            manifest=json.loads(args.artifact.with_suffix(args.artifact.suffix+'.manifest.json').read_text())
            if manifest['source_database']==actual or hashlib.sha256(args.artifact.read_bytes()).hexdigest()!=manifest['sha256']:
                raise ValueError('Separate restore target and intact backup required')
            existing=connection.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema='public'").fetchone()[0]
            if existing:raise ValueError('Restore target must be empty')
            connection.commit()
            result=subprocess.run(['pg_restore','--exit-on-error','--no-owner','--no-privileges','--dbname','',str(args.artifact)],
                                  env={**os.environ,'PGDATABASE':dsn},stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False)
            # PGDATABASE carries the verified DSN. Pass no DSN/password on the command line.
            if result.returncode:raise RuntimeError('Restore rehearsal failed')
        elif args.operation=='migrate':
            if args.artifact is None or not args.artifact.is_file():
                raise ValueError('Reviewed backup artifact required')
            manifest=json.loads(args.artifact.with_suffix(args.artifact.suffix+'.manifest.json').read_text())
            if manifest['source_database']!=actual or hashlib.sha256(args.artifact.read_bytes()).hexdigest()!=manifest['sha256']:
                raise ValueError('Backup identity/integrity mismatch')
            existing=connection.execute("SELECT to_regclass('ewu2_schema_version')").fetchone()[0]
            if existing:
                if connection.execute('SELECT version FROM ewu2_schema_version WHERE version=1').fetchone():
                    print('Migration already applied')
                    return 0
                raise ValueError('Unexpected migration state')
            connection.execute((ROOT/'migrations/001_recruitment.up.sql').read_text())
            connection.execute((ROOT/'migrations/001_recruitment.guard.sql').read_text())
            connection.execute('INSERT INTO ewu2_schema_version VALUES(1,%s)',(datetime.now(timezone.utc).isoformat(),))
        else:
            if not args.owner_id or not args.owner_id.isdigit():raise ValueError('Explicit owner Telegram ID required')
            count=connection.execute('SELECT count(*) FROM ewu2_actors').fetchone()[0]
            if count:raise ValueError('Owner bootstrap already completed; use authorized grant_actor')
            connection.execute("INSERT INTO ewu2_actors VALUES(%s,'owner',NULL)",(args.owner_id,))
            connection.execute("INSERT INTO ewu2_actors VALUES('system-recruiter','recruiter',NULL)")
    print('Staging operation completed; live deployment not performed')
    return 0


if __name__=='__main__':
    try:
        raise SystemExit(main())
    except Exception:
        # Connection and pg_dump errors can include credentials; do not echo exception text.
        raise SystemExit('staging_operation_failed') from None
