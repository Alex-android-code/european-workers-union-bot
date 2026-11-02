# EWU — RODO / GDPR: DFG controller draft

Status: DRAFT — not a published privacy notice or approved legal policy. Do not activate candidate intake from this document.

## Confirmed by project owner
- Controller: DFG SPÓŁKA Z OGRANICZONĄ ODPOWIEDZIALNOŚCIĄ
- Registered address: ul. Grzybowska 2/31, 00-131 Warszawa, Poland
- NIP: 5253018257
- REGON: 529707307
- KRS: 0001128310
- Contact for data-subject rights: vip.didkovsky5@gmail.com
- Service: EWU Telegram recruitment bot

## Before activation — verify and approve
1. Actual controller role of DFG, processor agreements with Telegram, Railway, Google and recruitment partners, and whether the stated contact is authorized for DFG.
2. Specific recruitment purposes, lawful bases per purpose (Article 6 GDPR), necessity and handling of any special-category data.
3. Candidate data categories, recipients/employers, any third-country transfers and safeguards.
4. Concrete retention schedule for applications and audit logs, external copies, backups, and erasure requests.
5. Rights and complaint notice (Polish UODO), optional vs required fields, human review/no automated decisions.
6. Public HTTPS privacy policy URL with full accurate notices in uk/pl/ru/en/de/es/pt/uz.
7. Private Railway PRIVACY_CONFIG_JSON only after approved policy; never commit personal records, tokens or secrets.

## Safe technical release
Current railway_start.py requires EWU_START_ALLOWED=1, EWU_MAINTENANCE=0 and load_policy() success. No fake notices, placeholder URLs or arbitrary legal bases should be used to bypass the gate. Leave CRM candidate transmission off until Google Sheets and deletion process are verified.

Source of registration data: screenshot provided by owner, not independently verified in KRS.

## Retention implementation decision (2026-11-02)
- Active recruitment: retain while the specific application is genuinely being processed; close promptly when the recruitment ends.
- Future vacancies: optional, separate opt-in with a proposed maximum of 365 days, **not currently implemented**; do not treat general RODO acknowledgement as marketing/future-recruitment consent.
- Pending deletion requests: preserve as actionable requests until handled, not as an excuse to retain the entire application.
- Employment/personnel records: separate system and statutory rules; do not apply candidate-bot TTL to employee records.
- Technical gap confirmed: `Store.purge()` uses a single `application_retention_days` age threshold for all applications, irrespective of candidate journey status. `Journey.cleanup()` removes associated local journey/outbox records after application purge, but this does **not** erase previously synchronized Google Sheets copies. This is not sufficient to claim full GDPR-compliant retention/deletion.
- Required next change: explicit purpose/status and separate future-vacancy opt-in, closure-based expiry, rights-request workflow for external copies, and tested retention cleanup. Keep CRM write disabled until those checks pass.
