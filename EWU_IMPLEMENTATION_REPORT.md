# EWU v2 — implementation report

## Результат і release status

Гілка: `feat/ewu-v2-foundation`, базується на RODO-коміті `643f4a0`; main перевірено на `947a44f`. Це **перевірена офлайн-реалізація foundation**, а не завершена production AI-система. Є runnable code, synthetic e2e, migrations, adapters і runbooks. Критерії §23, що потребують live infrastructure/legal approval, не виконані й не приховані.

Жодного production consumer не зупинено/запущено, токенів не використовували, Railway/GreenWork/робочі БД/Google Sheets не змінювали. Нову Telegram identity не створювали. Платний AI не підключено.

## Матриця фаз

| Фаза | Реалізоване / перевірене | Залишок / блокер |
|---|---|---|
| 1 Аудит | EWU_AUDIT з refs, конфігами, dependency/evidence/access inventory | Railway/deployed SHA/consumer/duplicates/GreenWork/mobile невідомі |
| 2 RODO/security | 5 мов, language-first adapter, notice/optional purposes, rights, RBAC, append-only/hash checks, TLS gate | Реальні legal facts/DPA/DPIA/permissions/evidence disposition не затверджені |
| 3 DB/CRM | additive 26-table schema; PostgreSQL adapter, canonical candidate IDs, 9-tab projection, atomic Google adapter/retry | Немає schema audit/migration реальної БД; не створено/не перевірено live spreadsheet |
| 4 Vacancies/workflow | partner-scoped registry/import, expiry, applications, status matrix, event audit | HRWork/API/GreenWork mappings і live partner transports відсутні |
| 5 AI/followups | verified-registry fallback, provider boundary, legal/consent/budget/Kill Switch, bounded candidate/application followups | Live model і природномовний діалог не реалізовані як перевірена функція; vendor/legal/budget не погоджені |
| 6 Arrival/start | verified instructions, self arrival, scoped check-in/start, notifications ledger | Live Operations routing, фактична доставка/підтвердження не перевірені |
| 7 Finance/dashboard/quality | confirmed-start-only money ledger, dedup, invoice/payment attestation, event-derived dashboard, private boolean feedback | Договірні terms/financial permissions та billing workflow реального партнера невідомі |
| 8 Tests/staging/rollback | synthetic transport e2e, actual SQL replay on PG-compatible engine, guards, backup/rollback tooling, staging templates | Docker build, psycopg-to-live-PG, pg_dump/restore, Google/Telegram staging, monitoring/alerts не перевірені |

## Змінені компоненти

- `ewu/`: backend domain/storage/service, Telegram adapter, AI, Sheets, registry import, outbox/notifications/partner ports, health/security, opt-in config і staging tools.
- `migrations/`: additive up/guards, non-destructive application rollback та окремий permissions template.
- `bot.py`: opt-in routing до того самого backend, graceful polling shutdown; не автоматична консолідація/міграція.
- `privacy/`: EN, address/AI/effective-date disclosure fields, voluntary-purpose labels і fail-closed example config.
- `tests/`: negative/positive domain/transport scenarios, synthetic e2e, SQLite restore, PostgreSQL migration/guard/SQL replay; старі suites збережені.
- `requirements.txt`: pinned psycopg і google-auth; жодних embedded credentials.
- `Dockerfile.staging`, `compose.staging.yml`, `.env.example`, `.dockerignore`: staging-only templates/default synthetic command.
- `.github/workflows/privacy-tests.yml`: offline CI definition на Node20 compatibility і Node24; actual Actions run не підтверджено через API Forbidden.
- Дев'ять root-документів із §22 плюс PR description; результати в EWU_TEST_RESULTS.md.

## Суттєві обмеження

1. Не обрано/не підтверджено єдиний production runtime. Python і Node зберігаються; Node/GreenWork compatibility не можна вважати зайвою.
2. Порівняно з main, базова RODO-гілка вимикає legacy GreenWork/group/admin/AI paths. Ця гілка **не є дозволом безумовно зливати або розгортати** їх видалення. Потрібні contract audit і погоджений handoff.
3. Новий namespace не є міграцією legacy records. Немає доказу, що дані вже узгоджені між SQLite/ewu_*/candidates/Sheets; reconciliation обов'язкова до активації.
4. Google adapter працює з явно заданим існуючим CRM ID, не створює дубль наосліп. Файл/ownership/permissions/справжні записи ще не перевірені. Великий snapshot, Sheets quotas і serialization lock потребують load tests.
5. Natural-language AI/provider, автоматичний live partner submission, Operations routing і mobile CRM не підключені. Не вважати synthetic transports живими сервісами.
6. Automated multi-period hourly settlements, bank verification, повна web/partner admin UI і контрольований Sheets→DB editor — майбутні адаптери. Поточний money ledger має одну узгоджену commission на application; financial attestation не доводить банківську оплату.
7. Retention planner не виконує erasure; права — durable operator requests плюс processing restriction. Повна deletion/disposition у зовнішніх копіях та append-only evidence потребує юридично погодженої реалізації й інфраструктурних доступів.
8. In-memory restore перевірено; реальні PostgreSQL backups/restore, encryption at rest, non-owner role і disaster recovery залишаються release blockers.

## Залежності від власника / secure settings

Потрібні read-only Railway inventory/logs і GreenWork/mobile contracts; dedicated staging DB/identity і reviewed migration/backup; затверджені notices, recipients/retention/grounds; existing Sheets ID/owner і придатна Google identity/scopes; partner/Operations authorization mapping; optional AI vendor/terms/budget. Секрети вводяться лише secure settings, не в чат або PR.

API GitHub повертає Forbidden: Git reads/push і PR API мають різні permissions. PR creation outcome повідомляється окремо після фактичної спроби; посилання на compare page не видається за створений PR.
