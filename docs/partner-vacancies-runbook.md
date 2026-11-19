# Partner vacancies runbook

Feature branch only until reviewed. Production main is untouched.

1. Obtain a partner-authorized export of the Office spreadsheet as JSON array of objects keyed by the original header names. The spreadsheet is NOT a native Google Sheet; do not assume Sheets API access.
2. Review export for hidden personal data and remove it.
3. Set DATABASE_URL in the secure execution environment. Do not commit credentials or raw applicant data.
4. Run `node scripts/import-partner-vacancies.js /secure/path/rows.json`. Repeat imports are idempotent by source ID + row ID.
5. All new or modified vacancies remain unverified. A trusted coordinator must verify the partner's availability and terms before approving. Approval example:
```sql
UPDATE ewu_partner_vacancies SET verified=true,publish_allowed=true,verified_at=now()
WHERE source_id='1JOGzOZ7Wv5RYN6VesoHIlp1aUQ3hsYnl'
AND source_row='<verified row ID>' AND source_active=true;
```
6. Only verified, publish_allowed, active jobs appear in Telegram /jobs. Closing or changing a vacancy hides it or revokes verification.
7. Run `node --test test/partner-vacancies.test.js` and `node --check bot.js` before merging.
8. Confirm Docker image includes partner-vacancies.js and test existing /start, application and employer flows in staging.

**Current limits:** no automatic Office-file polling, no verified live vacancy slots, no automatic candidate referral. Do not claim those features are live.
