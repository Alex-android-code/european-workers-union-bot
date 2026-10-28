"""Readiness snapshot for an owner-controlled future HTTP/monitoring adapter."""

def readiness(service):
    try:
        version=service.db.one('SELECT version FROM ewu2_schema_version WHERE version=1')
        service.legal()
        dead=service.db.one("SELECT count(*) AS n FROM ewu2_outbox WHERE status='dead'")['n']
        return {'ready':bool(version) and not dead,'database':bool(version),'legal':True,'dead_jobs':dead}
    except Exception:
        return {'ready':False,'database':False,'legal':False,'error':'readiness_failed'}
