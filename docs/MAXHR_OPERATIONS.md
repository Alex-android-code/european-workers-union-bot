# EWU × MaxHR production release — 2026-11-24

## Deployment scope and recovery point

Only repository Alex-android-code/european-workers-union-bot and Railway project
`e0aecd30-fe93-4f4f-9c66-120dab0ce919`, service
`ac403c8e-4a8f-404f-a760-20a5dd4dd0fc`, production environment
`1df87997-4a59-4519-8c3a-ac16086cf51d` are in scope.

Previous source: `fix/ewu-recovery-rodo-crm-20261102` at
`576f2ddd0ab3e9656322623cf14dd36cfa79e035`. Recovery branch:
`recovery/ewu-production-20261124`. Previous Railway deployment:
`f2e418a4-b99d-4052-8c71-63ec9b175c99`. That image reported SUCCESS but
logs showed its start lock was active: it is a rollback point, not proof of a
working polling process. Prepared changes were based on
`ac82255f626fba17ce317e42883935c7bfb38a98`.

## Runtime and persistent storage

Dockerfile.ewu builds Python 3.12 with pinned pyTelegramBotAPI and openpyxl.
Start: `python railway_start.py`. There must be one replica and zero deployment
overlap. A nonblocking OS lock on the existing privacy DB directory additionally
prevents two containers sharing the volume from polling simultaneously.
Telegram HTTP 409 or 401 exits the process; exception details are suppressed.
The previous Node runtime and tests remain available, but are never launched
alongside the Python poller.

`/data` remains the existing persistent Railway volume. No volume replacement,
new service or paid resource is required. The new public catalogue defaults to
`/data/ewu/maxhr.sqlite3`; existing application paths are not changed.

Before starting any workers, recovery.py snapshots every SQLite database under
/data with the SQLite backup API and verifies integrity. A private manifest and
backups are in `/data/recovery/maxhr-complete-20261124-v1/`. They remain on the
existing volume and are not copied into GitHub. This is a pre-release recovery
point, not an off-platform disaster recovery service.

## Public catalogue

The source file is an XLSX workbook in Drive, not a native Google Sheet:
`1JOGzOZ7Wv5RYN6VesoHIlp1aUQ3hsYnl`. Download uses Drive's public file download
endpoint. Workbook parsing reads headers, actual statuses and hyperlink targets.
An empty active row is ignored. Closed/paused jobs disappear atomically after a
successful sync. IDs derive from stable source links, independent of row order.
Unknown new projects are supported. Failed downloads/parses preserve the entire
last good catalogue. Successfully parsed all-closed workbooks produce an empty
catalogue intentionally. Syncs start on a 900-second schedule; the worker uses
its own SQLite connection. No ChatGPT scheduled automation is involved.

Public linked job descriptions are downloaded only from Google document/Drive
hosts. Description, schedule and housing excerpts are attributed to the source.
Different rates across workbook and linked descriptions are flagged. An image
filename is never interpreted as salary. Salary filters use conservative known
numeric lower bounds, not a promise of take-home pay. Missing fields and
ambiguous terms require confirmation. Source vacancy requirements and terms
remain verbatim, in the source language; menus and navigation have all seven
requested languages plus retained Uzbek. There are no model calls.

On the initial live source check: 11 filled active vacancies; 17 commission rules.
Allegro has differing base/night rates across sources. InPost WWS labels two
own-housing amounts as net. Tedi's table rate is an image. Those are not silently
corrected or presented as confirmed rates.

MaxHR's official contact page was checked on 2026-11-24:
https://maxhr.eu/kontakt/ . Public handoff goes to that page; EWU does not forward
candidate data or send a message automatically. The EWU owner contact uses the
owner-supplied number from session context.

## Configuration and privacy

Production public mode:

- EWU_PUBLIC_CATALOG=1
- EWU_START_ALLOWED=1
- EWU_MAINTENANCE=0
- MAXHR_INTAKE_ENABLED=0
- MAXHR_PRIVACY_REVIEWED=0
- MAXHR_DB_PATH=/data/ewu/maxhr.sqlite3
- MAXHR_CONTACT_VERIFIED=1
- MAXHR_CONTACT_URL=https://maxhr.eu/kontakt/
- EWU_COORDINATOR_URL=https://wa.me/48884804706

Existing TELEGRAM_TOKEN and private credentials remain on Railway and are never
committed or printed. Administrator user IDs come from EWU_ADMIN_IDS, with a
positive numeric ADMIN_CHAT_ID fallback. Group IDs never grant admin access.
Production logs indicate only whether an admin is configured.

Browsing does not require privacy acknowledgement and never saves incoming
free text, contact attachments or documents. Navigation state is kept in bounded
memory and expires after 30 minutes. New applications are disabled, regardless
of old consent callbacks. No personal data goes to an AI service.

Activation later requires BOTH MAXHR_INTAKE_ENABLED=1 and
MAXHR_PRIVACY_REVIEWED=1, plus a complete reviewed PRIVACY_CONFIG_FILE or
PRIVACY_CONFIG_JSON accepted by the existing policy validator. Do not fabricate
a policy to unlock intake. Explicit acknowledgement is required, and privacy
revision changes invalidate it. The form asks first name, last name, phone and
the selected job only. Only explicitly configured document requirements add
presence questions; values are yes/no/unknown. No document attachments, numbers,
birth dates, addresses or bank details are collected.

Existing /my_data, /withdraw and /delete_data work without activating new intake.
Data access is scoped to the Telegram sender. Deletion is a durable request;
external copies require controller follow-up. No false immediate deletion claim
is made. Existing reviewed retention and CRM protections remain in place. If the
legal configuration is unavailable, retention settings are not invented.

## Private administration

`/admin` displays commands in a private chat to authorized administrators only.
`/admin_stats`, `/admin_export` (CSV counts), `/admin_commissions`, `/admin_sync`
and `/admin_ad JOB_ID PLATFORM` work in public-catalogue mode. Platforms:
Telegram, Facebook, Instagram, Threads, WhatsApp. Generated ads are drafts;
there is no publication, mass messaging or paid-ad call.

Application updates use the existing privacy DB and require its reviewed policy:

- /admin_status APPLICATION_ID STATUS REVISION
- /admin_history APPLICATION_ID
- /admin_finance APPLICATION_ID COMMISSION_INDEX
- /admin_payment APPLICATION_ID CONFIRMED_GROSZ PAID_GROSZ REVISION

Use /admin_commissions to see zero-based source commission indices. The operator
must select the applicable source project; no ambiguous name match assigns fees.
Amounts are integer grosz. Expected commission is populated only for an
unambiguous base amount. A project colour or 900/700 band stays unresolved.
Early-hour payments and 3+1 bonuses are displayed separately and never added to
the base automatically. Unknown guarantee periods remain unknown. Confirmed,
paid and outstanding balances are separate and every payment change is audited.
Confirmations and payments represent operator-recorded events, not bank transfers.

New workflow: NEW → SCREENING → SENT_MAXHR → AWAITING_EMPLOYMENT → EMPLOYED →
HOURS_24 → HOURS_100 → COMMISSION_CONFIRMED → COMMISSION_PAID, with REJECTED
and WITHDRAWN exits. Previous statuses and arrival-plan functions are retained.
Concurrent/stale revisions are rejected. Duplicate normalized phone + job
applications are rejected without disclosing another applicant.

## Recovery

1. Disable polling: set EWU_MAINTENANCE=1 and redeploy the same service; wait for
   its old container to stop. Never start a second poller to diagnose the first.
2. For a code-only rollback, reconnect the service to the recovery branch/commit
   above, preserving the existing volume and variables. The old version requires
   its reviewed privacy policy to start; leave it locked if that is unavailable.
3. Restore a database only if integrity checks or verified data loss require it.
   With polling stopped, inspect manifest.json to match original paths to backup
   names. Make a fresh SQLite backup of current data first. Restore only the
   affected database using the SQLite backup API; retain owner-only permissions.
   A pre-release restore loses subsequent writes, so do not restore automatically
   for a code failure. Do not copy a live database file over another live DB.
4. Run PRAGMA integrity_check, verify row counts, start one replica, inspect
   recovery_backup_verified, maxhr_sync, telegram_verified and telegram_poll_ok.

Validation commands: python -m compileall -q (explicit source files),
python -m unittest discover -s tests -p 'test_*.py', npm test,
node --test tests/crm-bridge.test.mjs. New tests cover live-shape XLSX parsing,
closed/paused jobs, unavailable/malformed sources, ID stability, filters,
all languages/menu buttons, callback bounds, disabled intake, synthetic enabled
intake, document answer limits, rights isolation, admin access, statuses,
duplicates, commission non-stacking, optimistic concurrency and backup/restart.

## Verified deployment result and access blocker

Deployment `75b1982e-2aa7-43b9-8f31-efa273db9552`, code commit
`d07bae5b94fd383f97367972a6a03cd70c960094`, was built by Railway. Runtime
logs confirm live sync of 11 jobs and the production-image smoke check
(8 languages, 152 responses, persisted catalogue integrity OK, intake disabled).
The same volume retained all 11 jobs over container restarts.

Telegram getMe fails with HTTP 401 Unauthorized using the existing TELEGRAM_TOKEN.
No bot identity or live user conversation could be verified. The launch process
exits and Railway retries according to its existing policy; a platform SUCCESS
status alone is not evidence that the bot is online. The 15-minute background
worker is implemented and source-sync tests pass, but a sustained production
15-minute cycle cannot be verified while credential validation stops startup.
The next required action is replacing TELEGRAM_TOKEN for this service in the
Railway dashboard with a valid token for EWU_Jobs_Bot; do not paste it into chat
or GitHub. Updating the variable normally redeploys the pinned source.

The one-time pre-release manifest found zero SQLite files under /data. It does
not establish whether old candidate history exists in a different backing store.
No historical candidate files were deleted or migrated. Preservation of any
pre-existing external history is not claimed as verified.

Validation after the final code change: 63 Python tests and 16 Node tests passed.
This includes the existing 42 Python regression tests; 9 Node privacy/menu tests,
1 PostgreSQL/PGlite test and 6 signed CRM bridge integration tests. Syntax checks
passed. All form tests used synthetic data. CRM and financial mutations require
the reviewed privacy configuration; public-mode statistics, commission terms
and draft-ad commands are implemented, but live admin access remains unverified
until the Telegram credential works. There was no paid advertising, broadcasting,
new Railway resource or change to ARIA, MostHR or GreenSet.
