# European Workforce Union — EWU

Existing Telegram recruitment bot repository. Production runtime is **not verified**:
Railway/Procfile name Python while Docker/npm name Node. Do not run both with the
same token or assume that the feature branch is deployed.

The v2 foundation is explicitly disabled by default (`EWU_V2_ENABLED` unset/0).
It adds a modular recruitment backend to the existing Python entrypoint; it does
not create a new bot, migrate production or replace GreenWork automatically.

- [Actual infrastructure audit and blockers](EWU_AUDIT.md)
- [Architecture](EWU_ARCHITECTURE.md)
- [Implementation status and limitations](EWU_IMPLEMENTATION_REPORT.md)
- [Legal checklist](GDPR_LEGAL_CHECKLIST.md)
- [CRM schema](EWU_CRM_SCHEMA.md)
- [Workflow and AI boundary](EWU_AI_WORKFLOW.md)
- [Test evidence](EWU_TEST_RESULTS.md)
- [Deployment, backup and rollback](EWU_DEPLOYMENT_PLAN.md)
- [Operations](EWU_OPERATIONS_GUIDE.md)

## Offline verification

Python 3.12 and Node >=20 are required for the current compatibility tests.
Install requirements in an isolated venv and npm dependencies with `npm ci`.
Use a supported Node LTS for new staging work; the legacy production Dockerfile
still pins Node20 pending a confirmed runtime/consolidation decision.

```sh
python -m unittest discover -s tests -p 'test_*.py'
npm test
```

Tests use synthetic data, fake Telegram/Google transports, in-memory SQLite and
PostgreSQL-compatible PGlite. They require no bot token, Google identity, live DB
or paid AI. Do not invoke bot.py, npm start or the channel publisher for tests.
A reviewed `PRIVACY_CONFIG_FILE`, DB migration, dedicated staging infrastructure
and explicit authorization are required before live integration validation.
