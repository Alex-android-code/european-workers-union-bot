"""Disposable UI preview. No real candidate data or Telegram credentials."""
import argparse,json,os,tempfile
from pathlib import Path
import uvicorn
from .core import Settings,Radar,dump,now
from .api import create_app
from .security import password_hash,create_session

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=int(os.environ.get('PORT','3000')));parser.add_argument('--host',default='0.0.0.0');args,_=parser.parse_known_args()
    directory=Path(tempfile.mkdtemp(prefix='radar-preview-'))
    settings=Settings(dict(RADAR_DB_PATH=str(directory/'preview.sqlite3'),RADAR_SESSION_SECRET='synthetic-preview-secret-not-production-'*2,RADAR_ADMIN_PASSWORD_HASH=password_hash('Synthetic-preview-2026!'),RADAR_PUBLIC_ORIGIN=os.environ.get('RADAR_PREVIEW_ORIGIN',''),RADAR_DEV_HTTP='1'))
    radar=Radar(settings)
    seed=json.loads(Path(__file__).parent.parent.joinpath('maxhr_catalog.json').read_text())
    with radar.connect() as db:
        for j in seed['vacancies']:
            data=dict(title=j['name'],city=j['city'],description='Опис очікує перевірки за джерелом MaxHR.',pay=(str(j['net'])+' PLN нетто/год — потребує перевірки') if j['net'] else '',schedule='',hours=j['hours'] or '',places=j['places'],requirements=[])
            db.execute('INSERT INTO vacancies(id,public_json,updated_at) VALUES(?,?,?)',('preview-'+str(j['id']),dump(data),now()))
            db.execute('INSERT INTO vacancy_private VALUES(?,?,?)',('preview-'+str(j['id']),'Попередній перегляд. Дані ще не підтверджені для публікації.','{}'))
    settings.preview=True
    preview_token,_=create_session(radar)
    app=create_app(settings)
    # Preview proxy chooses its public origin dynamically. Restricted to disposable preview mode.
    @app.middleware('http')
    async def preview_origin(request,call_next):
        if not settings.origin and request.headers.get('origin'):settings.origin=request.headers['origin']
        response=await call_next(request)
        if request.url.path=='/':response.set_cookie('radar_session',preview_token,httponly=True,samesite='strict',path='/')
        return response
    uvicorn.run(app,host=args.host,port=args.port,access_log=False)

if __name__=='__main__':main()
