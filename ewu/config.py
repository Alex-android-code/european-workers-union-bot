"""Explicit opt-in. No automatic database migration, identity changes or new Telegram bot."""
import os
from urllib.parse import urlsplit,parse_qs
from privacy.onboarding import load_policy
from .storage import Database
from .service import Recruitment
from .telegram import TelegramRecruitment
from .domain import Denied


def database_url():
    dsn=os.environ.get('EWU_DATABASE_URL','')
    parsed=urlsplit(dsn)
    if parsed.scheme not in ('postgres','postgresql') or not parsed.hostname:
        raise Denied('Explicit PostgreSQL DSN required')
    if parse_qs(parsed.query).get('sslmode')!=['verify-full']:
        raise Denied('Verified PostgreSQL TLS required')
    return dsn


def configured_backend():
    if os.environ.get('EWU_V2_ENABLED')!='1':return None
    policy=load_policy(os.environ.get('PRIVACY_CONFIG_FILE',''))
    # Validate the reviewed policy before opening any database connection.
    provisional=Recruitment(None,policy)
    provisional.legal()
    db=Database.postgres(database_url())
    path=os.environ['PRIVACY_CONFIG_FILE']
    return TelegramRecruitment(Recruitment(db,policy),policy_loader=lambda:load_policy(path))
