# EWU → GreenWork: перевірена інтеграція для review

Код зберігає чинні мови й анкети bot.js. Новий entrypoint, transactional core, encrypted file inbox, candidate trigger/outbox, Telegram delivery outbox, retries/journal та SQL-звірка підготовлені. У production вони ще не впроваджені.

`npm ci` → `npm test`. Локальні тести: PostgreSQL 17.5 engine (PGlite), Node 20.20.2. Ті самі SQL/consumer/worker сценарії перевірені також на справжній ізольованій PostgreSQL 18 у Railway, без Telegram polling. Telegram transport у тестах — контрольований stub, не фактичний Operations.

Файли:
- bot.js — явний activation gate, перевірка mounted volume/schema/group, єдиний longpoll owner, окремі intake/consumer/sync/delivery loops, bounded redacted logs, health і graceful shutdown.
- bot-core.mjs — чинні анкети, всі записи через один tx client, всі send через outbox; admin allowlist для bind/unbind; повідомлення без HTML injection; AI має timeout.
- sync.mjs — AES-256-GCM inbox, atomic fsync перед offset, transactional receipts, stable application IDs, candidate worker/retries.
- intake-lock.mjs — POSIX flock --no-fork; lock звільняється ядром навіть після SIGKILL.
- delivery.mjs — per-chat ordered transactional outbox, backoff/rate-limit retries, blocked permanent errors, message receipts.
- migration.sql — додатковий DDL однією транзакцією; застосування вручну один раз після approval.
- backfill.sql — приватна identity звірка з fail-closed ambiguity; збереження CRM id/status/notes.
- reconcile.sql — тільки агреговані counts.
- ROLLOUT.md — конкретні production кроки, обмеження cutover і недеструктивний відкат.
- backup/ — зашифроване офсайт резервування; реальний sink/scheduler ще потрібно підключити.

Постійний mount /data, незалежний recovery ключ inbox, незалежний backup sink та approval rollout — обов’язкові перед запуском. Поки EWU_RUNTIME_ENABLED не дорівнює 1, новий entrypoint завершується до мережевих викликів. Не ставте activation flag у preview/test зі справжнім токеном.

Це підготовлений reviewed rollout candidate; успіх у production не заявлено. Повний service lifecycle з production Telegram/volume ще потребує контрольованої перевірки. Розробка multi-employer платформи винесена в ТЗ, не входить до доказів цих тестів.
