"""One-way canonical DB projections. No append API, formulas or arbitrary Sheet edits."""
from urllib.parse import quote
import json

from .domain import Denied
from .service import Actor

TABS = ('Candidates','Candidate_Card','Vacancies','Applications','Partners','Follow_Ups',
        'Activity_Log','Commissions','Dashboard')
HEADERS = {
 'Candidates':['Candidate ID','Name','Phone','Telegram ID','Language','City','Profession','Desired location','Experience','Housing','Relocation','Availability','Restricted','Recruiter','Next action','Latest application status'],
 'Candidate_Card':['Field','Value'],
 'Vacancies':['Vacancy ID','Partner ID','Title','Location','Address','Rate','Payment type','Schedule','Housing','Transport','Requirements','Places','Start date','Confirmed at','Coordinator','Status'],
 'Applications':['Application ID','Candidate ID','Vacancy ID','Partner ID','Status','Created at','Updated at'],
 'Partners':['Partner ID','Name','Contact'],
 'Follow_Ups':['FollowUp ID','Application ID','Due UTC','Attempts','Limit','Status','Candidate ID','Template'],
 'Activity_Log':['Event ID','Application ID','From','To','Actor','UTC'],
 'Commissions':['Commission ID','Partner ID','Application ID','Candidate ID','Model','Rate minor','Units','Currency','Amount minor','Contract','Period','Verification','Invoice date','Due date','Payment'],
 'Dashboard':['Metric','Value'],
}


def projection(service, actor, selected_candidate_id=None):
    # Sheets has no reliable per-tab read isolation. The entire file is owner/finance only.
    service.role(actor,'owner','finance')
    db=service.db
    rows={name:[HEADERS[name]] for name in TABS}
    for c in db.all('SELECT * FROM ewu2_candidates ORDER BY id'):
        p=json.loads(c['profile'])
        phone=db.one("SELECT value FROM ewu2_contacts WHERE candidate_id=? AND kind='phone'",(c['id'],))
        permitted=not c['restricted'] and service.allowed(c['telegram_id'])
        if not permitted:p={};phone=None
        values=[c['id'],p.get('name',''),phone['value'] if phone else '',c['telegram_id'] if permitted else '',c['language'],*[p.get(k,'') for k in ('city','profession','desired_location','experience','housing','relocation','availability')],c['restricted']]
        next_action=db.one("SELECT min(due_at) AS due FROM ewu2_followups WHERE status='pending' AND (candidate_id=? OR application_id IN (SELECT id FROM ewu2_applications WHERE candidate_id=?))",(c['id'],c['id']))
        latest=db.one('SELECT status FROM ewu2_applications WHERE candidate_id=? ORDER BY created_at DESC,id DESC LIMIT 1',(c['id'],))
        values += [c['recruiter_id'] or '',next_action['due'] or '',latest['status'] if latest else c['status']]
        rows['Candidates'].append(values)
        if c['id']==selected_candidate_id:
            rows['Candidate_Card'] += [[k,v] for k,v in zip(HEADERS['Candidates'],values)]
            apps=db.all('SELECT id,status,partner_id FROM ewu2_applications WHERE candidate_id=? ORDER BY created_at',(c['id'],))
            rows['Candidate_Card'] += [['Application '+a['id'],a['status']+' / '+a['partner_id']] for a in apps]
            events=db.all('SELECT e.to_status,e.at FROM ewu2_recruitment_events e JOIN ewu2_applications a ON a.id=e.application_id WHERE a.candidate_id=? ORDER BY e.at',(c['id'],))
            rows['Candidate_Card'] += [['Event '+e['at'],e['to_status']] for e in events]
            arrivals=db.all('SELECT r.reported_at,r.confirmed_at,s.confirmed_at AS started_at FROM ewu2_arrivals r JOIN ewu2_applications a ON a.id=r.application_id LEFT JOIN ewu2_employment_starts s ON s.application_id=a.id WHERE a.candidate_id=?',(c['id'],))
            for a in arrivals:
                rows['Candidate_Card'] += [[k,a[k] or ''] for k in ('reported_at','confirmed_at','started_at')]
            tasks=db.all("SELECT due_at,status FROM ewu2_followups WHERE application_id IN (SELECT id FROM ewu2_applications WHERE candidate_id=?) ORDER BY due_at",(c['id'],))
            rows['Candidate_Card'] += [['Next action',t['due_at']+' / '+t['status']] for t in tasks]
    for v in db.all('SELECT * FROM ewu2_vacancies ORDER BY id'):
        p=json.loads(v['data'])
        rows['Vacancies'].append([v['id'],v['partner_id'],*[p[k] for k in ('title','location','address','rate','payment_type','schedule','housing','transport','requirements','places','start_date')],v['confirmed_at'],p['coordinator'],v['status']])
    mappings={
      'Applications':('ewu2_applications',['id','candidate_id','vacancy_id','partner_id','status','created_at','updated_at']),
      'Partners':('ewu2_partners',['id','name','contact']),
      'Follow_Ups':('ewu2_followups',['id','application_id','due_at','attempts','max_attempts','status','candidate_id','template']),
      'Activity_Log':('ewu2_recruitment_events',['id','application_id','from_status','to_status','actor_id','at']),
      'Commissions':('ewu2_commissions',['id','partner_id','application_id','candidate_id','model','rate_minor','units','currency','amount_minor','contract_ref','period','verification','invoice_date','due_date','payment_status']),
    }
    for tab,(table,keys) in mappings.items():
        rows[tab]+=[[r[k] if r[k] is not None else '' for k in keys] for r in db.all(f'SELECT * FROM {table} ORDER BY id')]
    dashboard=service.dashboard(actor)
    rows['Dashboard'] += [[k,v] for k,v in dashboard.items() if type(v) in (str,int,float)]
    rows['Dashboard'] += [['status.'+k,v] for k,v in dashboard['statuses'].items()]
    rows['Dashboard'] += [['conversion.'+k,v] for k,v in dashboard['conversions'].items()]
    rows['Dashboard'] += [[f"partner.{r['partner_id']}.starts",r['starts']] for r in dashboard['partner_performance']]
    rows['Dashboard'] += [[f"transition.{r['from_status']}.{r['to_status']}",r['total']] for r in dashboard['transitions']]
    for row in dashboard.get('commissions',[]):
        rows['Dashboard'].append(['commission.'+row['currency']+'.'+row['payment_status'],row['amount_minor']])
    return rows


class MemorySheets:
    """Synthetic test transport; never represents a live Google spreadsheet."""
    def __init__(self):
        self.tabs={}
        self.failures=0
    def replace(self, rows):
        if self.failures:
            self.failures-=1
            raise OSError('Synthetic Sheets failure')
        self.tabs={k:[list(row) for row in values] for k,values in rows.items()}


class GoogleSheets:
    def __init__(self, spreadsheet_id, session, *, legal_approved=False, access_reviewed=False):
        # session is an existing Google AuthorizedSession; do not extract credentials.
        if not spreadsheet_id or not spreadsheet_id.replace('-','').replace('_','').isalnum():
            raise Denied('Existing spreadsheet ID required')
        if not legal_approved or not access_reviewed:
            raise Denied('Sheets legal and file access review required')
        self.url='https://sheets.googleapis.com/v4/spreadsheets/'+quote(spreadsheet_id,safe='')
        self.session=session

    def replace(self, rows):
        response=self.session.get(self.url,params={'fields':'sheets.properties'},timeout=30)
        response.raise_for_status()
        properties=response.json()['sheets']
        ids={s['properties']['title']:s['properties']['sheetId'] for s in properties}
        if set(rows)!=set(TABS):
            raise Denied('Expected canonical CRM tabs')
        requests=[]
        next_id=max(ids.values(),default=0)+1
        for tab in TABS:
            if tab not in ids:
                ids[tab]=next_id;next_id+=1
                requests.append({'addSheet':{'properties':{'sheetId':ids[tab],'title':tab}}})
            requests.append({'repeatCell':{'range':{'sheetId':ids[tab]},'cell':{},'fields':'userEnteredValue'}})
            # stringValue prevents formula injection even for names beginning with '='.
            def cell(v):
                if type(v) in (int,float):return {'userEnteredValue':{'numberValue':v}}
                if type(v) is bool:return {'userEnteredValue':{'boolValue':v}}
                return {'userEnteredValue':{'stringValue':str(v)}}
            requests.append({'updateCells':{'start':{'sheetId':ids[tab],'rowIndex':0,'columnIndex':0},
                                           'rows':[{'values':[cell(v) for v in row]} for row in rows[tab]],'fields':'userEnteredValue'}})
        response=self.session.post(self.url+':batchUpdate',json={'requests':requests},timeout=30)
        response.raise_for_status()
        # One atomic batch replaces projections: retries do not append duplicate candidates.
