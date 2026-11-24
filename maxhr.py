"""MaxHR public XLSX catalogue. Private commissions never enter public cards."""
import hashlib
import io
import json
import os
import re
import sqlite3
import warnings
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from openpyxl import load_workbook

SOURCE_ID = '1JOGzOZ7Wv5RYN6VesoHIlp1aUQ3hsYnl'
SOURCE = f'https://drive.google.com/uc?export=download&id={SOURCE_ID}'
MAX_BYTES = 25 * 1024 * 1024

def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')

def text(value):
    if value is None: return ''
    if isinstance(value, float) and value.is_integer(): return str(int(value))
    return str(value).strip()

def safe_url(value):
    from urllib.parse import urlsplit
    if not value: return ''
    u = urlsplit(value)
    return value if u.scheme == 'https' and u.hostname and not u.username and not u.password else ''

def download(url=SOURCE):
    # This URL is operator configuration, never derived from candidate messages.
    with urlopen(Request(url, headers={'User-Agent': 'EWU-MaxHR/1.0'}), timeout=40) as response:
        body = response.read(MAX_BYTES + 1)
    if len(body) > MAX_BYTES or not body.startswith(b'PK'): raise ValueError('Invalid XLSX response')
    return body

def parse_xlsx(body):
    if len(body) > MAX_BYTES: raise ValueError('Workbook too large')
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        if sum(x.file_size for x in archive.infolist()) > 100 * 1024 * 1024: raise ValueError('Expanded workbook too large')
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', UserWarning)
        workbook = load_workbook(io.BytesIO(body), data_only=True)
    jobs, commissions, seen, recognized = [], [], set(), False
    for sheet in workbook:
        for idx, row in enumerate(sheet.iter_rows(), 1):
            values = [text(c.value) for c in row]
            if 'Статус предложения' in values and 'Город / местоположение' in values:
                recognized = True
                for cells in sheet.iter_rows(min_row=idx + 1):
                    v = [text(c.value) for c in cells]
                    if len(v) < 14 or not (v[2] or v[3]): continue
                    if v[1].casefold() not in ('активная', 'активна', 'active', 'aktywna'): continue
                    location = v[3]
                    name = v[2] or (location.split(':', 1)[-1] if ':' in location else location)
                    for needle, label in [('allegro','Allegro'),('amazon','Amazon XPO1'),('dc9','InPost DC9'),('dc2','InPost DC2'),('wws','InPost WWS'),('inpost','InPost'),('empik','Empik'),('anton rohr','Anton Rohr'),('inter cars','Inter Cars'),('carpol','Carpol'),('tedi','Tedi'),('plukon','Plukon')]:
                        if needle in (location + ' ' + v[6]).casefold(): name=label; break
                    city = location.split(':', 1)[0].split('(')[0].strip(' ,')
                    for match in ('Piotrków Trybunalski','Nowa Niedrzwica','Wola Bykowska','Ciemne','Sochaczew','Mosina','Komorniki','Natolin','Stargard','Gruszczyce'):
                        if match.casefold() in location.casefold(): city=match;break
                    # Identity is a source link, or normalized project + city. Row order is irrelevant.
                    link = safe_url(cells[6].hyperlink.target if cells[6].hyperlink else '')
                    identity = link or re.sub(r'\s+', ' ', name + '|' + city).casefold()
                    jid = hashlib.sha256(identity.encode()).hexdigest()[:16]
                    if jid in seen: raise ValueError('Duplicate project identity')
                    seen.add(jid)
                    salary = '' if re.fullmatch(r'.*\.(png|jpg|jpeg)', v[7], re.I) else v[7]
                    rates = [float(n.replace(',','.')) for n in re.findall(r'\b\d{2}[.,]\d{2}\b', salary)]
                    # Only a conservative lower bound; never rank by a student/own-housing maximum.
                    lower = min(rates) if rates else None
                    issues = []
                    if not salary: issues.append('Salary is in an image; requires clarification.')
                    if '34,50 zł/год нетто' in salary: issues.append('Source labels both own-housing rates as netto; brutto/netto needs clarification.')
                    if name == 'Allegro': issues.append('Night supplement total conflicts with the base rate; clarify with MaxHR.')
                    if name == 'Inter Cars': issues.append('25.35 / 31.40 netto categories are not specified in this table.')
                    housing_url = safe_url(cells[10].hyperlink.target if cells[10].hyperlink else '')
                    transport_url = safe_url(cells[11].hyperlink.target if cells[11].hyperlink else '')
                    jobs.append(dict(id=jid,name=name,city=city,location=location,salary=salary,hours=v[9],schedule='',description='',description_url=link,
                        housing=v[10],housing_url=housing_url,transport=v[11],transport_url=transport_url,bonuses=v[8],requirements=v[4],
                        places=int(float(v[5])) if v[5] and re.fullmatch(r'\d+(?:\.0+)?',v[5]) else None,
                        couples=bool(re.search(r'\bП\b',v[4])),housing_available=bool(v[10] or housing_url),pay_floor=lower,
                        job_type='warehouse' if any(x in (name+' '+v[6]).casefold() for x in ('inpost','allegro','amazon','empik','rohr','inter cars','tedi','magazyn','склад')) else 'production' if any(x in name.casefold() for x in ('carpol','plukon')) else 'unspecified',
                        documents=[],issues=issues))
                break
            if 'Стандартная комиссия' in values and 'Проект' in values:
                for cells in sheet.iter_rows(min_row=idx+1):
                    v=[text(c.value) for c in cells]
                    if not v[0]:continue
                    commissions.append(dict(project=v[0],base=v[1],threshold=v[2],bonuses=v[4],early=v[5],notes=v[6],guarantee_period='',stacking_confirmed=False))
                break
    workbook.close()
    if not recognized: raise ValueError('Vacancy sheet headers missing')
    # A valid all-closed sheet is an intentional empty catalogue.
    return dict(vacancies=jobs,commissions=commissions,source_id=SOURCE_ID,synced_at=now())

class Catalog:
    def __init__(self,path):
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.db=sqlite3.connect(self.path,timeout=15);os.chmod(self.path,0o600)
        self.db.execute('CREATE TABLE IF NOT EXISTS catalog_snapshot(id INTEGER PRIMARY KEY CHECK(id=1),body TEXT NOT NULL,at TEXT NOT NULL)')
        self.db.execute('CREATE TABLE IF NOT EXISTS catalog_sync(id INTEGER PRIMARY KEY,at TEXT NOT NULL,ok INTEGER NOT NULL,error TEXT)')
        self.db.commit()
    def close(self):self.db.close()
    def read(self):
        row=self.db.execute('SELECT body FROM catalog_snapshot WHERE id=1').fetchone()
        return json.loads(row[0]) if row else dict(vacancies=[],commissions=[],synced_at=None)
    def sync(self,fetch=download):
        try:
            snapshot=parse_xlsx(fetch())
            if fetch is download:
                from concurrent.futures import ThreadPoolExecutor
                with ThreadPoolExecutor(max_workers=4) as pool:
                    snapshot['vacancies']=list(pool.map(enrich_job,snapshot['vacancies']))
            with self.db:
                self.db.execute('INSERT INTO catalog_snapshot VALUES(1,?,?) ON CONFLICT(id) DO UPDATE SET body=excluded.body,at=excluded.at',(json.dumps(snapshot,ensure_ascii=False),snapshot['synced_at']))
                self.db.execute('INSERT INTO catalog_sync(at,ok) VALUES(?,1)',(now(),))
                self.db.execute('DELETE FROM catalog_sync WHERE id < (SELECT MAX(id)-100 FROM catalog_sync)')
            return True
        except Exception:
            # Preserve the entire last good snapshot, including commission terms.
            with self.db:self.db.execute('INSERT INTO catalog_sync(at,ok,error) VALUES(?,0,?)',(now(),'source_unavailable_or_invalid'))
            return False
    def select(self,city=None,min_pay=None,housing=False,couples=False,kind=None):
        return [j for j in self.read()['vacancies'] if (not city or j['city']==city) and (min_pay is None or (j['pay_floor'] is not None and j['pay_floor']>=min_pay)) and (not housing or j['housing_available']) and (not couples or j['couples']) and (not kind or j['job_type']==kind)]
    def job(self,jid):return next((j for j in self.read()['vacancies'] if j['id']==jid),None)

def generate_ad(job,platform):
    if platform not in ('Telegram','Facebook','Instagram','Threads','WhatsApp'):raise ValueError('Unknown platform')
    link='https://t.me/EWU_Jobs_Bot?start=job_'+job['id']
    lines=[f"🇪🇺 EWU × MaxHR | {job['name']} — {job['city']}",job['salary'] or 'Salary: confirm with MaxHR',f"Hours: {job['hours'] or 'confirm'}",f"Places: {job['places'] if job['places'] is not None else 'confirm'}"]
    if job['housing_available']:lines.append('Accommodation offered; price and conditions require confirmation.')
    if job['issues']:lines.append('Some terms require clarification in the source. See vacancy card.')
    lines.append(link)
    if platform=='Instagram':lines.append('#EWU #MaxHR #Praca #Polska')
    if platform=='Threads':return '\n'.join([lines[0],(job['salary'] or 'Salary: confirm')[:250],link])[:500]
    return '\n'.join(lines)

def fetch_description(url):
    """Only download documents explicitly linked by the MaxHR workbook."""
    from urllib.parse import urlsplit
    import xml.etree.ElementTree as ET
    parsed=urlsplit(url)
    if parsed.hostname not in ('docs.google.com','drive.google.com'):return ''
    match=re.search(r'/d/([A-Za-z0-9_-]+)',parsed.path)
    if not match:return ''
    did=match[1]
    urls=[f'https://docs.google.com/document/d/{did}/export?format=txt',f'https://drive.google.com/uc?export=download&id={did}']
    for source in urls:
        try:
            with urlopen(Request(source,headers={'User-Agent':'EWU-MaxHR/1.0'}),timeout=18) as response:
                body=response.read(5*1024*1024+1);mime=response.headers.get('Content-Type','')
            if len(body)>5*1024*1024:continue
            if body[:2]==b'PK':
                with zipfile.ZipFile(io.BytesIO(body)) as archive:
                    item=archive.getinfo('word/document.xml')
                    if item.file_size>8*1024*1024:continue
                    root=ET.fromstring(archive.read(item))
                ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
                return '\n'.join(''.join(p.itertext()) for p in root.findall('.//w:p',ns))
            if 'text/plain' in mime:return body.decode('utf-8-sig')
        except Exception:continue
    return ''

def excerpt(lines,patterns,limit=900):
    for pattern in patterns:
        for idx,line in enumerate(lines):
            if re.search(pattern,line,re.I):
                chosen=[line]
                for following in lines[idx+1:idx+14]:
                    if len(chosen)>1 and re.match(r'^[^\w*•]{0,4}[А-ЯІЇЄA-Z][А-ЯІЇЄA-Z\s’\-]{5,}',following):break
                    chosen.append(following)
                return '\n'.join(chosen)[:limit]
    return ''

def enrich_job(job):
    body=fetch_description(job['description_url'])
    if not body:return job
    lines=[re.sub(r'\s+',' ',line).strip() for line in body.splitlines() if line.strip()]
    job['description']=excerpt(lines,[r'обов[’\x27]?яз',r'обязанност',r'zakres.*obowiązk',r'основные задачи'],900) or '\n'.join(lines[:7])[:700]
    job['schedule']=excerpt(lines,[r'^[^\w]{0,5}граф[іи]к (?:роботи|работы)',r'граф[іи]к',r'czas pracy',r'godziny pracy'],550)
    job['housing_details']=excerpt(lines,[r'прожива',r'жиль[её]',r'zakwaterowan'],550)
    job['transport_details']=excerpt(lines,[r'транспорт',r'dojazd'],400)
    doc_salary=excerpt(lines,[r'^[^\w*•]{0,5}(?:зароб[іи]тна плата|заработная плата|зарплата|ставки|оплата)',r'зароб[іи]тна плата',r'заработная плата',r'wynagrodzen',r'ставка',r'зарплата'],700)
    job['description_salary']=doc_salary
    if doc_salary:
        document_rates={float(n.replace(',','.')) for n in re.findall(r'\b\d{2}[.,]\d{2}\b',doc_salary)}
        table_rates={float(n.replace(',','.')) for n in re.findall(r'\b\d{2}[.,]\d{2}\b',job['salary'])}
        if document_rates-table_rates:
            job['issues'].append('Linked description and workbook contain different pay figures; applicable conditions require confirmation.')
            job['pay_floor']=min(document_rates|table_rates) if document_rates|table_rates else None
    job['description_checked_at']=now()
    return job
