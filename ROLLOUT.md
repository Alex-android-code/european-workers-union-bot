# План погодженого впровадження EWU → GreenWork

Ціль: GREENSET Recruit / production / greenwork-live (5f89a29a-c280-44bc-8870-bbd0896dbc75) та Postgres (beeab6e3-5149-40d4-b15f-c6ffec9af595). Окремий European Workers Union / EWU Bot не змінювати. greenwork-prod та greenwork-v2-test не використовувати як тестові без доведеної ізоляції DB/token.

## Перед ризикованим кроком

1. Перевірити актуальність main SHA і запущеного bot.js; baseline main 7780596e6dfd0b41b4417f1e64bab71e6df42daa, bot.js blob 405362409a95844d990f4387c6bb17c866b0c4b1. Перевірити всі staged Railway changes. Інші зміни не включати в rollout.
2. Зробити новий зашифрований snapshot безпосередньо перед migration, перевірити restore. Копія 11.10 — перевірений baseline, але її не заміняти доказом актуального snapshot.
3. Погодити production migration, handover greenwork-live і volume. Наявний greenwork-live не має volume. Не перепризначати три unattached volume: їх призначення/вміст не перевірені. Потрібен окремий volume /data і погоджений бюджет. Один replica, один регіон, sleep вимкнено.
4. Підготувати незалежний backup sink/scheduler і сповіщення; приватний ключ окремо. Автоматичний офсайт наразі не активований.
5. Створити EWU_INBOX_KEY як 32-byte random base64; передати лише через захищену Railway variable/secret, зберегти незалежну захищену recovery копію. Не друкувати ключ. EWU_INBOX_DIR=/data/ewu-inbox, EWU_RUNTIME_ENABLED=1; EWU_ADMIN_IDS — лише погоджені адміністратори EWU. Немає admin IDs — bind/unbind заблоковані, поточна binding збережена.

## Порядок

1. На чинній базі виконати migration.sql ОДИН раз з ON_ERROR_STOP. Весь DDL в одній транзакції, lock_timeout=3s; за timeout нічого не повторювати без повторного preflight. Migration не запускається автоматично при старті бота. Вона додаткова, не видаляє наявні таблиці/рядки.
2. Виконати backfill.sql: неоднозначні відповідності зупиняють транзакцію. Історичні candidates отримують FK до заявки, їх id/status/notes лишаються. Після backfill звірити reconcile.sql: missing_candidates=0, історичні counts не зменшилися. Нові заявки, які старий бот прийме під час migration, теж входять до backfill; за неоднозначності потрібна приватна ручна звірка.
3. Безперервне виконання старого й нового polling не допускається. Railway передає volume одному інстансу; deployment overlap має бути 0, достатнє draining для старого getUpdates/обробника. Нова версія не викликає getUpdates, поки не отримала volume flock і не пройшла startup schema/group checks. Старий код ще не має flock — тому його повний вихід перевіряти окремо до активації нової версії. Сам flock не захищає від старого чи зовнішнього poller.
4. Старий bot.js не має graceful shutdown/checkpoint. Суворо нульову паузу/нульову втрату на першому cutover підтвердити не можна: перезапуск/передача є необхідною початковою зміною. Призначити контрольоване вікно низького навантаження, зафіксувати стан незавершених сесій/заявок, дочекатися завершення поточного обробника. Не обіцяти zero downtime. Не викликати deleteWebhook або drop_pending_updates.
5. Запустити погоджений commit greenwork-live, дочекатися terminal deployment SUCCESS, перевірити один bot process, group binding, /api/health, volume persistence, відсутність нових 409. Не запускати node bot.js з консолі.
6. Відправити лише синтетичну заявку через Telegram-клієнт тестового користувача до чинного @UkrainianWelders_bot. Не підміняти її direct DB insert. Зафіксувати без PII: application UUID, CRM receipt 1, Operations message receipt, pending=0. Повторно передати вже збережений synthetic update у контрольованому replay до consumer — не запускати getUpdates окремо.
7. Збої DB/Telegram перевіряти на ізольованій копії; не зупиняти production Postgres. Перезапуск уже захищеного greenwork-live після синтетичного durable intake потребує погодженого контрольованого rollout. Всі synthetic записи/повідомлення залишити з TEST маркером; нічого не видаляти.
8. Прийняти рішення лише після реального application/CRM/Operations receipt та restore. 24-годинне спостереження за backlog, blocked delivery, error journal, disk usage і backup freshness.

## Відкат

Звичайний Railway redeploy старого bot.js НЕ безпечний: старий бот знову вставляє candidates без FK, може дублювати записи разом із trigger/worker і втрачає durable offset. Не видаляти нову schema/volume/outbox заради відкату, не restore baseline поверх production (це зітре нові дані).

Перший варіант — roll forward виправленим commit, який зберігає durable intake і receipts. Для тимчасового обмеження нового функціоналу: погоджений runtime в режимі intake-only на тому самому volume; getUpdates продовжує зберігати updates, consumer/delivery/sync вимкнені, користувачі побачать затримку відповіді. Backlog зберігається, після виправлення повторно обробляється. Перемикач EWU_PROCESSING_MODE=intake реалізований; у full режимі worker відновлює backlog. Перевірка повного production lifecycle перемикача ще потрібна. Це той самий процес, не другий poller.

За невідновного пошкодження DB: відновити encrypted dump в НОВУ ізольовану DB, перевірити hash/counts/schema/ACL, застосувати сумісні migrations, дограти durable encrypted inbox з receipts. Перемикання DATABASE_URL погодити окремо. Старі DB/volume/історію залишити. RPO для DB dump не нульовий: intake + receipt replay допомагає Telegram-заявкам, але не відновлює всі CRM-редагування після snapshot.

## Межі гарантій

Exactly-once стосується запису кандидата за ewu_application_id і транзакційного receipt update. Telegram sendMessage не підтримує idempotency key: якщо Telegram прийняв повідомлення, а відповідь/COMMIT загубилися, retry може створити друге повідомлення. Немає втрати самої заявки, але гарантія exactly-once для групового повідомлення не заявляється.

Локальний зашифрований inbox + fsync переживає недоступність PostgreSQL/рестарт за умови збереження volume/key. Не переживає втрату volume без його незалежної копії. Disk capacity треба контролювати; при fsync error fetch offset не просувається. Telegram зберігає необроблені updates обмежений час, тому тривалий outage intake потребує сповіщень і реагування.

Динамічні роботодавці/вакансії описані в додатку ТЗ. Цей rollout забезпечує фундамент доставки заявок; він не є реалізацією всього multi-employer платформи.
