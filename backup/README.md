# Незалежне резервування

Поточна перевірена разова копія від 11.10.2026 існує поза Railway. Цей скрипт не означає, що регулярний backup уже налаштовано.

Потрібні: погоджений незалежний S3 bucket іншого облікового запису/постачальника, публічний сертифікат шифрування, мінімальні PutObject/GetObject права без DeleteObject, PostgreSQL 18 client, OpenSSL з CMS AES-256-GCM, AWS CLI 2, bash/flock. Bucket: block public access, versioning, за потреби погоджене Object Lock retention. Приватний ключ тримати офлайн окремо від bucket і Railway; на producer його не передавати.

Запускати щодоби окремим runner у дозволеній приватній мережі PostgreSQL. Не відкривати production DB в інтернет заради резервування. Scheduler і sink наразі не створені: немає погодженого місця призначення, доступу та бюджету. Рекомендована ціль: RPO 24 години для DB dump, RTO 60 хвилин після вимірювання повного restore. Для RPO коротше потрібні WAL/PITR або частіші копії.

Кожен запуск: consistent pg_dump → шифрування потоку → upload з унікальним key та checksum → download і byte comparison → запис часу успіху. Зовнішній монітор має сповістити, якщо немає успішної копії >26 годин; destination і контакт сповіщень погодити. Скрипт повертає помилку при будь-якій невдалій стадії; перед scheduler перевірити failure alerts.

Щотижнева restore drill: завантажити копію, перевірити checksum, розшифрувати в захищеному ізольованому середовищі офлайн-ключем, pg_restore --exit-on-error на PostgreSQL 18, звірити таблиці/кількості/хеші та виконати synthetic інтеграційні тести. pg_dump не охоплює глобальні ролі й налаштування мережі: права/ролі відтворювати з окремо версіонованого infrastructure manifest без паролів. Перевірка таблиць з --no-owner --no-acl не є перевіркою ACL.

Сховище inbox теж потребує незалежних зашифрованих копій і окремого захисту EWU_INBOX_KEY: сам PostgreSQL dump не містить updates, які ще не були оброблені. Це окрема умова повної аварійної стійкості. Для нульового RPO при втраті volume потрібне синхронне незалежне durable intake перед Telegram acknowledgment; поточний локальний fsync забезпечує DB outage/restart, але не втрату самого volume.

Документація: https://www.postgresql.org/docs/18/app-pgdump.html ; https://docs.aws.amazon.com/cli/latest/reference/s3api/put-object.html
