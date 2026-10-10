# EWU isolated stabilization proposal

Status: review branch only. Not deployed. Not an approved replacement for the unknown laptop/Railway build. The existing Node intake is reused; the Python code, Railway configuration, branding and production variables are unchanged.

## Implemented in this branch

- Polling requires the exact opt-in `EWU_START_ALLOWED=true`; no startup profile edits or webhook deletion.
- Read-only getWebhookInfo preflight refuses a configured webhook. A dedicated PostgreSQL advisory lock prevents another copy using the same token and DB. Telegram 409 terminates this proposed process; this cannot prevent a separate legacy process using another database.
- Explicit `EWU_ADMIN_IDS` and `EWU_GROUP_IDS` allowlists protect group binding and delivery. Empty lists grant no access.
- Existing menu routing fix reused. Drafts are saved per user and questionnaire; returning to a section restores its step. /start and /resume continue an active questionnaire. /reset asks for /confirm_reset.
- Intermediate answers store last_message_id alongside session state, so replay after send failure does not advance another field.
- Final application ID derives from chat/message identity. The same final message is idempotent. A unique Telegram candidate profile is upserted independently of applications; phone-based merging is intentionally unresolved. Separate applications remain legitimate history.
- Final application, candidate profile, notification outbox, draft cleanup and session transition use one DB transaction. Recruiter delivery retries from persisted outbox, including contact requests. At-least-once delivery can duplicate a Telegram notification if send succeeded but marking delivery failed; exactly-once Telegram delivery is not promised.
- No writes to GreenWork candidates table. No automated HOT/WARM rating. Intake uses a factual local summary and does not wait for AI.
- Plain text Telegram responses prevent HTML parsing of user content. International phone validation, request/DB timeouts, redacted event-only error logs.
- Raw message history storage is disabled unless separately enabled with `EWU_STORE_MESSAGE_BODIES=true`. Questionnaire/profile data still require retention controls.
- AI chat is preserved but requires separate `EWU_AI_CHAT_ALLOWED=true`, model and AI Gateway credentials. This branch does not replace the unknown Gemini integration.
- Liveness and readiness separated. Readiness requires recent successful polling, reachable DB and an allowlisted bound recruiter group.

## Validation

`node --check bot.js`
`node --test tests/*.test.mjs`

27 isolated tests pass: navigation, full candidate/employer flow in 7 languages, resume, draft switching, reset confirmation, group authorization, plain text, phone validation, repeated answer, final-message deduplication, notification retry, contact forwarding and webhook refusal. SQL, Telegram and AI use synthetic mocks. No production secrets, networks or records are used.

## Not yet verified / completed

No real PostgreSQL transaction/DDL validation, Telegram live test, Gemini check, backup/restore test, process restart integration test, permanent error/dead-letter handling or full GDPR workflow. Database-wide candidate dedup across other channels, durable update inbox, privacy commands, translation of new operational prompts, monitoring alerts and retention scheduler still need implementation/validation. Advisory lock protects only participating copies sharing the database. The original Python stub still lacks these changes and remains an unapproved alternative entrypoint.

## Safe integration sequence

1. Obtain actual working EWU source, railway_start.py, startup metadata, and CRM target without publishing secrets.
2. Decide whether these changes are transplanted into the actual Python/Gemini implementation or whether Node is approved as the base. Do not overwrite production with this branch.
3. Select an isolated test DB/token. Back up the actual database before any DDL. New additive tables: ewu_drafts, ewu_delivery, ewu_profiles; additive column: ewu_sessions.last_message_id. These are not a migration of candidate data.
4. Align Dockerfile, Procfile, package.json, railway.toml and Railway start override only after base approval. Pin dependencies and build a reproducible release then.
5. Test live candidate/employer intake, all languages, duplicate updates, unavailable DB/Telegram/AI, backup and restore. Validate one consumer and webhook state.
6. Present exact commit, schema changes, test evidence, budget and rollback to owner before production deployment. No merge or launch is authorized by approving this preparation branch.

## Backup/rollback proposal awaiting actual database

Use a consistent SQLite backup API (if actual base is SQLite) or pg_dump (if PostgreSQL), encrypted off-volume storage, daily backups plus pre-change snapshot. Verify checksum and restore into an isolated DB; compare counts and synthetic intake. Target RPO 24h / RTO 60min, not measured. Roll code back to an immutable tested release without rolling DB backward and losing new records. Candidate exports/backups require the established processing basis and approved destination. No backup job was started by this change.
