# EWU RODO onboarding — architecture and review

## Scope and runtime audit

- Railway (`railway.toml`) and Procfile select `bot.py`: pyTelegramBotAPI, no application database. Previously `/start` asked for data immediately and arbitrary text was forwarded to `ADMIN_TELEGRAM_ID`.
- npm and Docker select `bot.js`: PostgreSQL sessions, applications and message transcripts. Previously inbound messages were persisted before `/start`; candidate answers were scored, potentially sent to AI, copied to a GreenWork candidates table and forwarded to a configurable Telegram group. Group binding had no administrator authorization.
- `scripts/ewu_channel_publisher.py` is a separate GitHub Actions publisher with its own token and at-most-once ledger. It is unchanged. Never run it without `--dry-run` for validation.
- These are two distinct applications, not redundant entrypoints to one implementation. The privacy UI and policy schema are shared; persistence adapters differ. Migrating application intake into a single reviewed service remains advisable.

## Implemented behavior

Both `/start` and `/privacy` send four complete notices (Ukrainian, Polish, Russian, Uzbek), each with Continue/Decline. Every notice contains a full-document HTTPS link, controller, contact, purposes, legal bases, retention, recipients/transfers, rights, supervisory complaint route, provision consequences and automated-decision information. No legal facts are invented. A missing or incomplete policy blocks questionnaire access; incoming message contents are neither persisted nor forwarded by the gate. Telegram necessarily delivers the sender ID/message to the bot; this is not collection-free transport.

Continue records `acknowledged`, NOT consent. Decline records `declined`. Records contain user ID, UTC timestamp, text version, content revision, locale and exact displayed notice. All four configured notices contribute to the revision, so content changes require fresh acknowledgement even if the version was not bumped. IDs and notice events are personal data too: disclose their purpose, legal basis and retention in the policy.

`/withdraw` records withdrawal and blocks further intake. There are **no active consent-based optional features** in this change: AI/profiling, GreenWork sync, group/admin forwarding and raw message transcripts are disabled/removed. No blanket consent or invented legal basis is used. Do not re-enable those features by treating acknowledgement as consent. Any future consent feature needs a distinct purpose, reviewed text, freely given opt-in, refusal path, version/time/user/action ledger and an effective withdrawal mechanism before processing.

`/delete_data` registers a durable, idempotent pending rights request and blocks intake, including attempts to re-acknowledge. It does not falsely claim that all data was erased. Python stores requests in SQLite; Node stores them in `ewu_deletion_requests`. Completion requires an authorized human procedure covering application data, older GreenWork copies, forwarded Telegram messages, processors and backups. Do not mark a request resolved merely to unblock the user. No automated production deletion is performed by this PR.

Python stores minimal, explicitly selected intake forms in the same private SQLite database after acknowledgement, with no admin forwarding. Unsolicited text outside a selected form is discarded and the response says so. Candidate forms collect name, city, phone and profession; employer/legal forms collect only basic contact and request information. Media are not downloaded. This deliberately closes the previous unreviewed admin forwarding path; there is no automatic CRM integration. Node retains the reviewed core application workflow after acknowledgement, with candidate fields reduced to name, phone, location and profession; documents, citizenship, driving and stability profiling are removed. Free-text legal questions still need operator controls against unsolicited sensitive data. Node clears partial sessions on every privacy decision; old application rows stay subject to rights/retention review.

## Required configuration (no secrets in repository)

Copy `privacy/policy.example.json` to a private deployment configuration location and fill **all** four language notices. Set `PRIVACY_CONFIG_FILE` to its absolute path; configure the same file for either runtime. The example deliberately fails validation until completed. Deployment must mount/provision the file; Docker does not embed legal configuration.

- `version`: approved text version; change it whenever policy changes.
- `core_legal_basis`: lawyer-approved `art6_1_b`, `art6_1_c` or `art6_1_f`. These are permitted choices, not a legal determination that any applies. Consent-based core processing is not supported by this flow. The translated `legal_basis` and `purposes` fields must accurately describe each activity, including onboarding evidence and rights handling. If no appropriate basis applies, do not launch intake.
- `audit_retention_days` and `application_retention_days`: approved integers 1–3650. No default retention is asserted. Explain the actual periods/triggers in every notice; review the cap against legal requirements.
- Each notice needs the actual controller identity/address, privacy contact (and DPO where applicable), purposes, bases, retention, recipients, international transfers/safeguards, rights, complaint authority/contact, mandatory/optional provision and consequences, automated decisions, and real `policy_url` (HTTPS). Validation checks structure, not legal accuracy or URL availability.
- For `rights`, explicitly explain access, rectification, erasure, restriction, portability where applicable, objection, and withdrawal where processing relies on consent. Identify the applicable supervisory authority instead of guessing jurisdiction.
- Python: `PRIVACY_DB_PATH` defaults to `/data/ewu/privacy.sqlite3`. Use a dedicated persistent directory owned by the service, restrictive volume permissions, encryption at rest/backups and one polling process. DB file mode is 0600; parent directory creation uses 0700. Do not place it on ephemeral deployment storage.
- `TELEGRAM_TOKEN` is runtime-only, never needed for tests. Node also needs a dedicated development `DATABASE_URL` for live testing. Do not use production values. `ADMIN_TELEGRAM_ID` and AI keys no longer activate processing.

Python audit/application/session expiry runs on rights/state actions; Node audit/application/session/legacy-message expiry runs during valid private updates. This is opportunistic expiry, **not** a scheduled guarantee: an idle deployment requires an operator-scheduled retention job. Pending rights requests do not silently expire; review them promptly and retain/erase completed request evidence according to the approved policy. SQLite free pages/backups and PostgreSQL MVCC/backups require the operator's secure disposal procedures.

## Security and legal release gates

Application logs use fixed event identifiers, not exception bodies or user text. Python Telegram SDK logging is disabled during runtime to avoid token-bearing URLs. Review infrastructure/HTTP/DB logs and access controls separately; this code cannot sanitize external logging systems. No uploaded media is downloaded. Configure rate limiting/abuse protection and processor agreements before production use.

Legal approval is still required for controller details, purposes and bases for each activity, special-category restrictions, retention, rights/request SLA and response channel, Telegram/hosting subprocessors and international transfers, translations (especially Uzbek), automated decision/profiling implications, historical data remediation, and backup/processor deletion. A four-language notice alone is not certification of GDPR compliance.

## Validation and rollout

Offline only; never import `bot.js` to run tests, because it is a runtime entrypoint.

```sh
cd /workspace/european-workers-union-bot
PYTHONDONTWRITEBYTECODE=1 /workspace/ewu-venv/bin/python -m unittest discover -s tests -p 'test_*.py'
npm ci --ignore-scripts --no-audit --no-fund
npm test
node --check bot.js
node --check database.js
python3 scripts/ewu_channel_publisher.py --dry-run
```

Python bot factory is tested with a fake Telegram transport, no token. Node tests use transport spies and an in-memory PostgreSQL-compatible WASM engine (PGlite); they never read `DATABASE_URL`. PGlite validates actual schema/queries, transactions, retention and durable request blocking; it does not replace a separately approved staging test on the production PostgreSQL version. No live Telegram, production DB, webhook, publication or deployment is validated here.

On approved staging rollout, provision policy and volume first. Node creates the privacy tables at runtime alongside existing `CREATE TABLE IF NOT EXISTS`; review DDL and retention DELETE statements before enabling. Review legacy records before applying chosen retention limits. Old onboarding sessions are invalid until current notice acknowledgement. There is no automatic acknowledgement migration. Rollback to old code would restore unsafe collection/forwarding; prefer disabling polling while fixing any release defect. Do not deploy automatically from this PR.
