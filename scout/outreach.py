"""EWU Scout outreach gate: local drafts only, never sends messages."""
from datetime import datetime, timezone
from scout import connect

CHANNELS = {"telegram", "email", "whatsapp"}

def initialize(db):
    db.executescript("""CREATE TABLE IF NOT EXISTS contacts(
        lead_id TEXT NOT NULL, channel TEXT NOT NULL, address TEXT NOT NULL,
        consent_basis TEXT NOT NULL, opted_out INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY(lead_id,channel));
    CREATE TABLE IF NOT EXISTS outreach_queue(
        id INTEGER PRIMARY KEY AUTOINCREMENT, lead_id TEXT NOT NULL,
        channel TEXT NOT NULL, message TEXT NOT NULL,
        state TEXT NOT NULL DEFAULT 'draft', created_at TEXT NOT NULL);""")

def register_contact(lead_id, channel, address, consent_basis):
    if channel not in CHANNELS: raise ValueError("Unsupported channel")
    if not address.strip() or not consent_basis.strip(): raise ValueError("Address and basis required")
    with connect() as db:
        initialize(db)
        if not db.execute("SELECT 1 FROM leads WHERE id=?", (lead_id,)).fetchone():
            raise ValueError("Unknown lead")
        db.execute("""INSERT INTO contacts(lead_id,channel,address,consent_basis)
            VALUES(?,?,?,?) ON CONFLICT(lead_id,channel) DO UPDATE SET
            address=excluded.address, consent_basis=excluded.consent_basis,
            opted_out=contacts.opted_out""", (lead_id,channel,address,consent_basis))

def opt_out(lead_id, channel):
    with connect() as db:
        initialize(db)
        db.execute("UPDATE contacts SET opted_out=1 WHERE lead_id=? AND channel=?", (lead_id,channel))
        db.execute("""UPDATE outreach_queue SET state='blocked_opt_out'
            WHERE lead_id=? AND channel=? AND state IN ('draft','ready')""", (lead_id,channel))

def queue_draft(lead_id, channel, message):
    if channel not in CHANNELS: raise ValueError("Unsupported channel")
    if not message.strip() or len(message)>2000: raise ValueError("Invalid message")
    with connect() as db:
        initialize(db)
        contact=db.execute("SELECT * FROM contacts WHERE lead_id=? AND channel=?", (lead_id,channel)).fetchone()
        if not contact or contact["opted_out"] or not contact["consent_basis"].strip():
            raise PermissionError("No permission or opted out")
        cursor=db.execute("""INSERT INTO outreach_queue(lead_id,channel,message,created_at)
            VALUES(?,?,?,?)""", (lead_id,channel,message,datetime.now(timezone.utc).isoformat()))
        return {"queue_id":cursor.lastrowid,"state":"draft","sent":False}
