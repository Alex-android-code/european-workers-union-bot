# EWU recovery — implementation and production blockers

Status: **not deployed; production integration is not complete**. This document
supersedes the earlier recovery notes for the changes on this branch only.

## Findings from this session

- The existing Railway service is marked SUCCESS and has one configured replica.
  Its source configuration points to PR #8 head `576f2ddd0ab3e9656322623cf14dd36cfa79e035`.
  This is a configured source, not proof of the source inside the current image.
- Runtime logs say `EWU start locked: explicit cutover approval required.` Build
  logs show Railpack/Python 3.11 and a different dependency set from the Python
  Dockerfile in PR #8. The actual running files and commit were not inspected.
- The existing /data volume is Ready and uses about 32.16 MB out of 500 MB.
  The volume backup list is empty. Its files and SQLite schemas were not read.
- Railway CLI authentication completed. SSH and the volume-files API both need
  ssh.railway.com, which this execution environment cannot resolve. Therefore
  no production SQLite backup or process inventory was performed.
- Railway OAuth reads expose variable names, not their values. A broad raw-value
  CLI request was rejected by automatic security review. No secrets were copied
  into code, test fixtures or this document.
- Creation of a new Google Sheet failed with storageQuotaExceeded. After the
  owner authorized reuse of the existing private EWU CRM, its owner/privacy
  metadata were verified and a pre-edit XLSX export was saved privately. An
  atomic addSheet request failed with PERMISSION_DENIED. No spreadsheet edits
  were applied. No existing sheets or data were removed.
- No Railway service configuration, deployment, token, production data, GreenWork
  or ARIA was changed. No paid model calls were added.

## Implemented on this branch

1. Python exposes exactly UK/PL/RU/EN/DE/ES/PT. The legacy Node catalogue is left
   untouched. /start offers language selection, then one privacy notice. Choice
   is persisted when reviewed policy configuration is available.
2. Separate presented/acknowledged events retain notice revision, locale, exact
   text and UTC time. A forged acknowledgement cannot bypass first presentation.
   Showing /privacy does not revoke an existing acknowledgement. Optional
   marketing/future-recruitment processing remains disabled.
3. Missing or incomplete privacy configuration blocks new collection. A privately
   cached last reviewed policy lets existing rights commands work after a restart
   when current configuration is lost; this cache cannot enable new collection.
   Notice validation now includes data categories and sources.
4. Stable Candidate ID, transactional application/journey/outbox writes and exact
   repeat-form deduplication. New policy revisions and terminal applications do
   not incorrectly reuse an old application.
5. /privacy, /my_data, /status, /withdraw, /delete_data plus /correct, /restrict,
   /export_data and /object. Rectification/erasure/objection/restriction requests
   are durable and identity-scoped. Registering a request is not a false claim
   that erasure or rectification in every system has already completed.
6. Canonical twelve-status model with seven-language labels and legacy-status
   compatibility. Coordinator transitions check role, expected revision and
   allowed next state. Confirmed travel requires a human-approved plan.
7. Nine-tab CRM schema, local workbook, Apps Script operational projection,
   HMAC authentication, target-sheet/receipt checks, idempotent delivery and
   controlled status-command ingestion. Private notes remain in SQLite because
   protected spreadsheet ranges do not hide information from file viewers.
8. An installable on-edit trigger can capture status requests only if Google
   supplies an editor identity matching an active owner/coordinator. Python
   independently checks the explicit Telegram admin allowlist. Missing editor
   identity is rejected. Commands are committed with notifications atomically.
   Telegram has no send idempotency key: uncertain deliveries are held rather
   than blindly retried. Operators must review sending/uncertain notifications.
9. SQLite online-backup, schema inventory and restore-to-new-path utilities.
   Existing files are never overwritten by restore preparation. Startup takes a
   migration checkpoint before opening stores, once per release to avoid filling
   a small volume with copies on every restart. These utilities have only been
   tested against synthetic local files, not the production volume.
10. Expired local forms with confirmed external copies retain an erasure reference
    and lose their form fields instead of silently orphaning a Google row.
    External erasure remains pending and prevents new export of that application.
    CRM startup requires explicit review of the external rights/backup procedure.

## Validation

- `python -m unittest discover -s tests -p 'test_*.py' -q`: 62 tests.
- `npm test`: 10 legacy Node privacy/PGlite tests.
- `node --test tests/crm-operational.test.mjs`: 9 Apps Script emulator tests,
  including the original five bridge tests.
- `git diff --check` and Python compilation checked.

Tests use synthetic identities, temporary real SQLite files and a Google API
emulator. They cover seven languages and three forms, notice bypass, repeat
registration, persistent queue/restart, outage/retry, signed receipts, atomic
rollback, stale/unauthorized status commands, notification suppression, local
backup/restore and retention erasure references. **They are not a successful
real Telegram → Railway → Google → Telegram end-to-end test.**

## Remaining work and release gates

- Confirm controller postal address, privacy contact, purposes/legal bases,
  recipients/transfers and retention for applications, audit, rights requests and
  backups. The owner selected the individual-controller model. Do not populate
  legal notices with invented details or enable collection before review.
- Restore Google write authorization, or use an owner-authorized signed-in
  browser fallback. Reuse of the existing CRM is approved, but its API write
  failed. Add the nine operational tabs without touching legacy tabs, apply
  dropdowns/filters/roles/protection, verify privacy and read back the result.
- Install all three Apps Script files (`Code.gs`, `commands.gs`, `operational.gs`)
  under the owner, set private properties and authorize the installable on-edit
  trigger. The web app and trigger have not been deployed in this session.
- Finish and test external erasure, correction, retention and backup handling.
  Pending rights requests must be resolved in every actual recipient system.
  There is no claim of automated complete deletion across legacy systems,
  sheet revision history, external recipients or backups.
- `CRM_V2_ENABLED=1` and `CRM_V2_REVIEWED=1` plus URL/secret/sheet ID are still
  required. Nine-tab projection additionally needs `CRM_OPERATIONAL_ENABLED=1`;
  reverse commands need `CRM_BIDIRECTIONAL_ENABLED=1`. Apps Script separately
  needs OPERATIONAL_REVIEWED/BIDIRECTIONAL_REVIEWED. All remain off until live
  verification. `CRM_EXTERNAL_RIGHTS_REVIEWED=1` is a release gate, not a claim
  that code alone completes the external rights process.
- Before any deployment, obtain and verify a production backup. Railway native
  snapshots are incremental billed storage; no snapshot was created without
  explicit approval of that cost. Alternatively restore permitted SSH access
  and use an online SQLite backup on the existing volume.
- Verify the real runtime files, all legacy DB schemas and polling processes.
  Do not assume a healthy container proves a healthy Telegram bot.
- Run the real synthetic end-to-end test, restart/outage/retry/erasure tests,
  confirm data preservation and only then mark recovery complete.

## Rollback

This branch is isolated from Railway's configured source branch; publishing it
does not constitute a production cutover. Keep the old volume and deployment.
The failed Google batch was atomic and added no tabs. Its private pre-edit export
is available for recovery. For a future release, record the verified image and
backup before cutover. Restore into a new SQLite path first and validate it;
never overwrite a running database. Apply all completed erasure decisions before
restoring access to old data from backups. Do not reactivate an old intake that
bypasses privacy gates.

Official references used for review:
- https://eur-lex.europa.eu/eli/reg/2016/679
- https://www.uodo.gov.pl/pl/492/2464
- https://docs.railway.com/volumes/backups
- https://docs.railway.com/integrations/api/manage-volumes

No certification or guarantee of legal compliance is implied by passing tests.
