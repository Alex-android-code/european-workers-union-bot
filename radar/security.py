"""Password and session primitives. No credentials are stored in browser storage."""
import hashlib
import hmac
import secrets
import time
from datetime import datetime,timedelta,timezone
from .core import Forbidden,digest,now

def password_hash(password,salt=None):
    if not isinstance(password,str) or not 12<=len(password)<=256:raise ValueError('Password must be 12-256 characters')
    salt=salt or secrets.token_hex(16)
    result=hashlib.scrypt(password.encode(),salt=bytes.fromhex(salt),n=16384,r=8,p=1,maxmem=64*1024*1024).hex()
    return 'scrypt$'+salt+'$'+result

def verify_password(password,encoded):
    try:
        _,salt,_=encoded.split('$')
        return hmac.compare_digest(password_hash(password,salt),encoded)
    except (ValueError,TypeError):return False

class LoginLimiter:
    def __init__(self):self.failures={}
    def allow(self,key):
        current=time.monotonic();self.failures={k:[v for v in values if current-v<900] for k,values in self.failures.items() if values and current-values[-1]<900}
        if len(self.failures)>10000:self.failures.pop(next(iter(self.failures)))
        return len(self.failures.get(key,[]))<5
    def failed(self,key):self.failures.setdefault(key,[]).append(time.monotonic())
    def success(self,key):self.failures.pop(key,None)

def create_session(radar):
    token=secrets.token_urlsafe(32);csrf=secrets.token_urlsafe(32)
    expires=(datetime.now(timezone.utc)+timedelta(hours=8)).isoformat(timespec='seconds')
    with radar.connect() as db:db.execute('INSERT INTO sessions VALUES(?,?,?)',(digest(token),digest(csrf),expires))
    return token,csrf

def validate_session(radar,token,csrf=None):
    if not token:raise Forbidden('Потрібен вхід')
    with radar.connect() as db:row=db.execute('SELECT * FROM sessions WHERE token_hash=? AND expires_at>?',(digest(token),now())).fetchone()
    if row is None:raise Forbidden('Сесію завершено')
    if csrf is not None and not hmac.compare_digest(row['csrf_hash'],digest(csrf)):raise Forbidden('Захист CSRF')
    return 'recruiter'
