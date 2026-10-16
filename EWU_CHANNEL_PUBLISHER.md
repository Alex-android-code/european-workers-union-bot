# EWU @EWUpraca — safe publisher

This is an independent GitHub Actions publisher. It does **not** start Telegram
polling, read candidates, touch the EWU Railway volume, or redeploy the existing bot.

## Activation (owner-controlled)

1. In GitHub repository Settings > Secrets and variables > Actions, create a
   repository secret named `EWU_TELEGRAM_BOT_TOKEN` using the Telegram bot token.
   Never paste tokens into chat, commits, vacancy JSON or channel posts.
2. Keep `vacancies/approved.json` as `[]` until a real vacancy is confirmed.
3. Add a verified vacancy to that list with a unique `id`, `status:
   "approved"`, `approved: true`, `employer_verified: true`, a
   nonempty `approved_by`, future `valid_until` in `YYYY-MM-DD` format,
   and Russian (or other approved) `text`.
4. Workflow: Actions > EWU approved vacancy publisher > Run workflow, or wait
   for one of three scheduled UTC checks. Only **one** offer posts per run.

Example JSON record, **documentation only** (not a real vacancy):
```json
{
  "id": "example-0001",
  "status": "approved",
  "approved": true,
  "employer_verified": true,
  "approved_by": "EWU operator",
  "valid_until": "2026-12-31",
  "text": "Пример вакансии. Проверенные условия работы."
}
```

## Safety

- Posts contain only an approved job text, not candidate names, phones or documents.
- Every post links to the confirmed EWU Telegram bot:
  https://t.me/UkrainianWelders_bot
- A vacancy must be approved, employer-verified and not expired.
- A persistent ledger is committed **before** sending to avoid accidental
  automatic duplicate posts after uncertain network outcomes.
- If a post is marked `attempted` but no post appears in Telegram, review the
  channel and GitHub Actions logs before manually resetting that ledger entry.
- GitHub Actions must be allowed to write to the repo's default branch, as it
  commits the delivery ledger. If branch protection prevents this, posting
  deliberately stops before sending.
- GitHub's public repository will expose the approved vacancy texts; never
  place candidate personal data here.
- GitHub Actions cron is best effort, not guaranteed to execute on the minute.

## Current limitations

Nothing will publish until the secret is configured **and** approved vacancies
are added. New/edited GreenWork vacancies are not synced automatically yet.
An authorized feed integration should be added after confirming GreenWork's
real API and approval model. No claim of live activation is made.
