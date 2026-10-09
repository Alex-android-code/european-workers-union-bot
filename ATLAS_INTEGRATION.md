# ATLAS Recruitment OS — integration workspace

Status: integration branch only; NOT production-ready.

## Existing systems
- EWU Telegram bot: candidate/employer intake, multilingual, PostgreSQL.
- GREENSET HR: separate recruiter bot on Vercel.
- GREENSET Recruit: Railway services greenwork-v2-test, greenwork-prod, greenwork-live, Postgres.
- ARIA: planned command interface.

## Target architecture
One multi-tenant PostgreSQL-backed recruitment core; adapters for Telegram, web, and authorized messaging APIs; recruiter console; job matching; candidate lifecycle; consent and retention controls; audit trail; human review for employment decisions.

## Non-negotiable migration constraints
1. Do not deploy this branch or modify production tokens/webhooks.
2. Inventory actual schemas and services before migration.
3. Backup databases before any schema change.
4. Keep tenant data isolated; GREENSET data and proprietary ATLAS data separate.
5. Require authorization and platform permissions for outbound posts/messages.
6. Do not auto-reject candidates based solely on AI scoring.
7. Run staging end-to-end tests before cutover.

## Acceptance flow
Vacancy created -> applicant opts in -> multilingual intake -> validated profile -> job shortlist -> recruiter approval -> arrival and start confirmation -> optional authorized timesheet integration -> analytics.

## Next engineering tasks
- Audit bot.js and database schema; extract reusable intake module.
- Inspect GREENSET Railway services and Vercel API routes.
- Design tenant-aware migrations and shared API.
- Build staging environment with synthetic test records.
- Integrate channel adapters, deduplication, and recruiter dashboard.
- Add monitoring, backups, rate limits, and GDPR workflows.
