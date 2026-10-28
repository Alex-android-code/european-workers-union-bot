"""Explicit partner-scoped sheet import; table presence is never a new confirmation."""
from datetime import datetime,timedelta
from .domain import Denied


def import_rows(service,actor,partner_id,records,*,source_reviewed=False,max_age_hours=72):
    if not source_reviewed:raise Denied('Approved source mapping required')
    scope=service.role(actor,'owner','recruiter','partner')
    if scope['role']=='partner' and scope['partner_id']!=partner_id:raise Denied('Partner scope denied')
    if type(max_age_hours) is not int or not 1<=max_age_hours<=168:raise Denied('Confirmation window required')
    accepted,needs_confirmation=[],[]
    for record in records:
        try:
            confirmed=datetime.fromisoformat(record['confirmed_at'])
            expires=datetime.fromisoformat(record['expires_at'])
            stale=(confirmed.tzinfo is None or expires.tzinfo is None or confirmed>service.clock()
                   or confirmed<service.clock()-timedelta(hours=max_age_hours) or expires<=service.clock())
        except (KeyError,ValueError,TypeError):stale=True
        if stale:
            needs_confirmation.append(record.get('external_id','invalid'))
            # Do not silently keep a previously imported vacancy matchable.
            with service.db.transaction():
                previous=service.db.one('SELECT id FROM ewu2_vacancies WHERE partner_id=? AND external_id=?',(partner_id,record.get('external_id','')))
                if previous:
                    service.role(actor,'owner','recruiter','partner')
                    role=service.role(actor,'owner','recruiter','partner')
                    if role['role']=='partner' and role['partner_id']!=partner_id:raise Denied('Partner scope denied')
                    service.db.execute("UPDATE ewu2_vacancies SET status='NEEDS_CONFIRMATION' WHERE id=?",(previous['id'],))
                    event=service.audit('vacancy.import_stale',actor,previous['id'])
                    service.enqueue('sheets',previous['id'],'vacancy-stale:'+event)
                    service.enqueue('partner_confirmation',previous['id'],'stale:'+previous['id']+':'+service.now())
            continue
        accepted.append(service.vacancy(actor,partner_id,record['external_id'],record['data'],min(expires,confirmed+timedelta(hours=max_age_hours)).isoformat(),confirmed.isoformat()))
    return {'imported':accepted,'needs_confirmation':needs_confirmation}
