# European Workers Union Bot

Production Telegram bot for EWU.

Features:
- 7 languages: UA / PL / RU / EN / DE / ES / PT
- Candidate, Employer and Legalization flows
- Persistent PostgreSQL sessions/applications/messages
- AI candidate summary and score via Railway/Vercel AI Gateway
- Automatic restart on Railway
- Secrets stored only in Railway Variables

## Privacy onboarding

Both runtimes require a reviewed external `PRIVACY_CONFIG_FILE` before intake is
available. No legal details or live credentials are supplied by default. See
[architecture, configuration and legal review](docs/PRIVACY_REVIEW.md).
Offline tests never require a Telegram token or a database connection:
`python -m unittest discover -s tests -p 'test_*.py'` and `npm ci && npm test`.
Do not deploy or start production polling as part of validation.
