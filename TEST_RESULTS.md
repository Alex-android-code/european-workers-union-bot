# Перевірки 11.10.2026

Node 20.20.2 + isolated PostgreSQL 18: **8/8 pass** після виправлення flock --no-fork. Запущено через Railway Console у /tmp/ewu-runtime-tests, database ewu_integration_v2, Unix socket /tmp/ewu-restore-20261011/socket, port 55432, listen_addresses=''. Production Postgres не зупинявся. Під час тесту зупинявся/запускався тільки окремий тестовий cluster; intake файли пережили недоступність DB й були дограні. Жодного getUpdates у тестах.

1. Stable application identity: replay стабільний, наступна заявка має інший UUID.
2. Encrypted intake: fsync checkpoint, duplicate ingestion, рестарт, acknowledgment збереження.
3. Corruption/conflicting payload: fail closed.
4. Частковий запис batch/disk failure: offset не просувається.
5. Повна чинна анкета → application → candidate job → один CRM candidate → два фінальні delivery jobs (group та користувач). PostgreSQL outage/reopen й duplicate update не втрачають заявки і не додають кандидата. Telegram delivery — stub.
6. Rollback update/app/outbox; candidate constraint failure → SQLSTATE journal + retry; Telegram 429 → retry; раннє невідправлене повідомлення блокує лише свій chat; replay не перезаписує ручні CRM status/notes.
7. Один intake owner, друга спроба lock відхилена; SIGKILL звільняє lock; successor відновлюється без видалення файлів.
8. Історичний backfill зберігає CRM id/status/notes; неоднозначна identity відхиляється транзакційно.

Додаткова локальна перевірка Node 20.20.2 + PostgreSQL 17.5 engine (PGlite): **9/9 pass**, включно з activation guard — непогоджений preview завершується до викликів Telegram. Це не тест роботи production Telegram або production lifecycle сервісу.

Окремо backup відновлено на PostgreSQL 18: всі 10 вихідних таблиць звірені за count/content fingerprints. Нова міграція та backfill на свіжій відновленій копії: candidate_applications=4, linked_candidates=4, missing_candidates=0, sync_pending=0. Production read-only перевірка після тестів: 6 applications, 4 candidates, 0 колонок candidates.ewu_application_id — production migration не застосована.

Не проведені: справжня заявка Telegram → Operations → нова CRM integration в production; deployment/volume mount graceful handover; незалежний scheduled backup sink/recovery key separation; full restore ACL; втрата volume; load tests. 8/8 ізольованих тестів не замінюють ці перевірки.
