# EWU — staging, міграції, backup і rollback

**Production deployment не дозволений цим артефактом і не виконувався.** Невідомі production consumer/DB/GreenWork; немає затверджених юридичних даних, Sheets ID/permissions і бюджету AI.

## Послідовність release gates

1. Підтвердити Railway deployed SHA, effective builder/command, replicas, volumes, token identity і єдиний consumer. Не запускати другого poller для «перевірки».
2. Перевірити GreenWork/mobile DB contract; погодити canonical store і міграцію/звірку legacy candidate IDs. Нова schema сама не переносить старі дані.
3. Затвердити legal config усіма мовами, retention/rights/disposition, partner/Sheets/notifications scopes. Live AI залишається disabled до окремого vendor/legal/budget sign-off.
4. Виділити staging DB/volume/test bot/CRM, які не містять реальних кандидатів, production токенів або робочих даних.
5. Backup/restore rehearsal, additive migration, runtime role і owner bootstrap. Потім staging integration, acceptance tests та окреме підтвердження rollout.

## Підготовлені файли і що не перевірено

`Dockerfile.staging` — Python 3.12, non-root user, default command — synthetic tests, не polling. `compose.staging.yml` — ізольований Postgres16 volume, loopback port і TLS assets, bot service лише під explicit profile. Файли підготовлено, але Docker images не будувалися, compose не запускався; підтримка TLS-файлів/прав у конкретному runner потребує перевірки.

Перед build у managed cloud прочитати Docker runtime skill щодо inherited proxy/CA; не відключати TLS або package verification. Не використовувати production Dockerfile, який наразі Node20, для Python artifact. Не змінювати Railway builder/start command до підтвердження active runtime.

## Керування БД

Потрібні встановлені psycopg та сумісні pg_dump/pg_restore (не входять до staging image). DSN задається тільки через захищену `EWU_DATABASE_URL`, з `sslmode=verify-full` і CA trust. Жодних DSN/password у командному рядку або чаті. Задати `EWU_ENVIRONMENT=staging`; exact database name перевіряється через current_database(). Приклад назв нижче — лише ізольований test target.

```sh
# Default dry-run: ніякого підключення до БД.
python -m ewu.manage migrate
python -m ewu.worker_main

# Лише після незалежного staging-дозволу і secure env configuration:
python -m ewu.manage backup --execute --expected-db ewu_staging --artifact /secure/ewu-staging.dump
python -m ewu.manage restore-check --execute --expected-db ewu_restore_test --artifact /secure/ewu-staging.dump
python -m ewu.manage migrate --execute --expected-db ewu_staging --artifact /secure/ewu-staging.dump
python -m ewu.manage bootstrap-owner --execute --expected-db ewu_staging --owner-id APPROVED_OWNER_ID
```

Для restore-check переключити secure DSN на окремий порожній restore target; source/target збіг заборонено. Backup і manifest створюються ексклюзивно з mode0600; manifest містить SHA256/source DB, не credentials. Зберігання/шифрування/backups поза repo — обов'язок інфраструктури. Невдала команда залишає artifact для обмеженого операторського розбору; не вважати його валідним backup без manifest/check/rehearsal.

Міграція 001 та append-only guards застосовуються однією транзакцією; повторне застосування з version1 — no-op. Bot runtime лише перевіряє schema version. Privilege template 002 — окремий ручний review після provision non-owner role, без глобальних змін GreenWork schema. Bootstrap owner допускається тільки до наявності будь-яких actors; подальші grants — owner-only backend.

Жодної з цих execute-команд не виконували під час розробки. Реальний PostgreSQL backup/restore не підтверджений; synthetic SQLite restore і PG-compatible SQL replay не замінюють його.

## Worker / Sheets

Явно вказати **вже погоджений** GOOGLE_SHEETS_ID, reviewed permissions для всього файла (тільки owner/finance), approved policy.sheets_approved і `EWU_SHEETS_ACCESS_REVIEWED=1`. Використовується наявна Google identity через google.auth/AuthorizedSession, без копіювання secret-файлів. У staging потрібні `EWU_SYNC_ACTOR_ID`, `EWU_EXPECTED_DATABASE` та opt-in backend.

```sh
# Після staging authorization; не виконано під час розробки:
python -m ewu.worker_main --execute --loop
```

За відсутності reviewed transport відповідна topic лишається pending. Telegram notifications додатково потребують `EWU_ALLOW_STAGING_NOTIFICATIONS=1` та окремого staging-токена. GreenWork/Operations API destinations не вгадуються; live adapters відсутні. Worker frontend не є підтвердженням live CRM sync.

## Rollback

`migrations/001_recruitment.rollback.sql` навмисно не видаляє таблиць або даних. Application rollback: узгоджено вимкнути v2 flag/повернути попередній approved artifact, зберегти schema/evidence/outbox, звірити pending/uncertain delivery і consumer ownership. Не відновлювати стару БД поверх нових заявок автоматично. Не повертати небезпечні forwarding/privacy behavior без юридичного containment plan.

До будь-якого handoff потрібні RPO/RTO, перевірений restore, сумісність backward changes, синтетичний staging e2e, monitoring/alerting і підтвердження власника. Видалення дубльованого runtime або schema — тільки окремий reviewed PR/дозвіл.
