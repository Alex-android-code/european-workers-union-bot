"""Recruiter API; anonymous public endpoints use an explicit vacancy projection."""
import json
import logging
from pathlib import Path
from fastapi import FastAPI,Request,Response
from fastapi.responses import HTMLResponse,JSONResponse
from .core import Settings,Radar,Refused,Forbidden,STATUS_LABELS,source_tag,dump,uid,now,digest
from .security import verify_password,create_session,validate_session,LoginLimiter

STATIC=Path(__file__).with_name('static')

def create_app(settings=None):
    settings=settings or Settings();radar=Radar(settings);limiter=LoginLimiter()
    app=FastAPI(title='EWU Кандидатний радар',docs_url=None,redoc_url=None,openapi_url=None)
    app.state.radar=radar
    @app.exception_handler(Refused)
    async def refused(request,error):return JSONResponse({'error':str(error)},status_code=409)
    @app.exception_handler(Forbidden)
    async def forbidden(request,error):return JSONResponse({'error':str(error)},status_code=403)
    @app.exception_handler(Exception)
    async def unknown(request,error):
        logging.error('radar_request_failed type=%s',type(error).__name__)
        return JSONResponse({'error':'Не вдалося виконати запит'},status_code=500)
    @app.middleware('http')
    async def headers(request,call_next):
        try:
            if int(request.headers.get('content-length','0'))>64000:return JSONResponse({'error':'Завеликий запит'},status_code=413)
        except ValueError:return JSONResponse({'error':'Некоректний запит'},status_code=400)
        response=await call_next(request)
        response.headers['Cache-Control']='no-store';response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        response.headers['Referrer-Policy']='no-referrer'
        if settings.secure:response.headers['Strict-Transport-Security']='max-age=31536000'
        return response
    async def body(request):
        raw=await request.body()
        if len(raw)>64000:raise Refused('Завеликий запит')
        try:value=json.loads(raw)
        except (ValueError,UnicodeDecodeError):raise Refused('Некоректний JSON')
        if not isinstance(value,dict):raise Refused('Очікується об’єкт')
        return value
    def actor(request,write=False):
        if write:
            # Exact configured origin prevents cross-site writes; cookies alone never authorize mutations.
            if not settings.origin or request.headers.get('origin')!=settings.origin:raise Forbidden('Недозволене джерело запиту')
            if not request.headers.get('x-csrf-token'):raise Forbidden('Захист CSRF')
        return validate_session(radar,request.cookies.get('radar_session',''),request.headers.get('x-csrf-token','') if write else None)
    @app.get('/health')
    async def health():return {'service':'candidate-radar','status':'ok','intake_enabled':settings.ready,'bot_enabled':settings.bot_enabled}
    @app.get('/')
    async def index():return HTMLResponse((STATIC/'index.html').read_text())
    @app.get('/app.js')
    async def script():return Response((STATIC/'app.js').read_text(),media_type='application/javascript')
    @app.get('/style.css')
    async def style():return Response((STATIC/'style.css').read_text(),media_type='text/css')
    @app.get('/api/public/vacancies')
    async def public_jobs():return {'vacancies':radar.jobs()}
    @app.post('/api/public/match')
    async def match(request:Request):return {'vacancies':radar.match(await body(request))}
    @app.post('/api/login')
    async def login(request:Request):
        if not settings.origin or request.headers.get('origin')!=settings.origin:raise Forbidden('Недозволене джерело запиту')
        if settings.secure and request.url.scheme!='https':raise Forbidden('Потрібен HTTPS')
        if len(settings.secret)<32 or not settings.admin_hash:raise Forbidden('Вхід ще не налаштований власником')
        data=await body(request)
        if set(data)!={'password'}:raise Refused('Некоректний вхід')
        key=radar.keyed_hash(request.client.host if request.client else 'unknown')
        if not limiter.allow(key):return JSONResponse({'error':'Забагато спроб. Спробуйте пізніше.'},status_code=429)
        if not verify_password(data['password'],settings.admin_hash):limiter.failed(key);raise Forbidden('Невірні дані входу')
        limiter.success(key);token,csrf=create_session(radar)
        with radar.connect() as db:radar.audit(db,'recruiter_login',None,'recruiter')
        response=JSONResponse({'csrf':csrf});response.set_cookie('radar_session',token,httponly=True,secure=settings.secure,samesite='strict',max_age=28800,path='/')
        return response
    @app.get('/api/session')
    async def session(request:Request):
        actor(request)
        # Issue a fresh CSRF proof on reload; invalidate previous tabs' old proof intentionally.
        import secrets
        csrf=secrets.token_urlsafe(32)
        with radar.connect() as db:db.execute('UPDATE sessions SET csrf_hash=? WHERE token_hash=?',(digest(csrf),digest(request.cookies['radar_session'])))
        return {'csrf':csrf,'intake_enabled':settings.ready,'statuses':STATUS_LABELS,'preview':getattr(settings,'preview',False)}
    @app.post('/api/logout')
    async def logout(request:Request):
        actor(request,True)
        with radar.connect() as db:db.execute('DELETE FROM sessions WHERE token_hash=?',(digest(request.cookies['radar_session']),))
        response=JSONResponse({'ok':True});response.delete_cookie('radar_session');return response
    @app.get('/api/admin/vacancies')
    async def admin_jobs(request:Request):actor(request);return {'vacancies':radar.admin_jobs()}
    @app.put('/api/admin/vacancies/{jid}')
    async def save_job(jid:str,request:Request):
        who=actor(request,True);radar.save_job(who,jid,await body(request));return {'ok':True}
    @app.get('/api/admin/applications')
    async def applications(request:Request,q:str='',vacancy:str='',city:str='',status:str='',source:str=''):
        actor(request);return {'applications':radar.candidates(q,vacancy,city,status,source)}
    @app.get('/api/admin/applications/{aid}')
    async def detail(aid:str,request:Request):
        who=actor(request);result=radar.detail(aid)
        with radar.connect() as db:radar.audit(db,'application_viewed',aid,who)
        return result
    @app.patch('/api/admin/applications/{aid}')
    async def update(aid:str,request:Request):
        who=actor(request,True);data=await body(request)
        if set(data)!={'status','note','revision'}:raise Refused('Некоректні поля')
        radar.update_application(who,aid,data['status'],data['note'],data['revision']);return {'ok':True}
    @app.get('/api/admin/metrics')
    async def metrics(request:Request):actor(request);return radar.metrics()
    @app.put('/api/admin/sources/{tag}')
    async def source(tag:str,request:Request):
        who=actor(request,True);data=await body(request)
        if source_tag(tag)!=tag or set(data)!={'label','spend_grosz'} or type(data['spend_grosz'])is not int or not 0<=data['spend_grosz']<=1000000000 or not isinstance(data['label'],str) or len(data['label'])>120:raise Refused('Некоректне джерело')
        with radar.connect() as db:
            db.execute('INSERT INTO sources VALUES(?,?,?) ON CONFLICT(tag) DO UPDATE SET label=excluded.label,spend_grosz=excluded.spend_grosz',(tag,data['label'],data['spend_grosz']));radar.audit(db,'source_updated',tag,who)
        return {'ok':True,'link':'https://t.me/EWU_Jobs_Bot?start=src_'+tag}
    @app.get('/api/admin/deletion-requests')
    async def deletion_requests(request:Request):
        actor(request)
        with radar.connect() as db:return {'requests':[dict(r) for r in db.execute('SELECT id,applicant_id,requested_at,status FROM deletion_requests ORDER BY requested_at')]}
    @app.post('/api/admin/deletion-requests/{aid}/complete')
    async def erase(aid:str,request:Request):radar.erase(actor(request,True),aid);return {'ok':True}
    @app.get('/api/admin/notifications')
    async def notifications(request:Request):
        actor(request)
        with radar.connect() as db:return {'notifications':[dict(r) for r in db.execute('SELECT id,application_id,created_at FROM outbox WHERE seen=0 ORDER BY created_at DESC LIMIT 100')]}
    @app.post('/api/admin/notifications/seen')
    async def seen(request:Request):
        actor(request,True)
        with radar.connect() as db:db.execute('UPDATE outbox SET seen=1')
        return {'ok':True}
    return app
