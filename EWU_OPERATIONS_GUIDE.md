# EWU operations — безпечний runbook

## Режими

За замовчуванням EWU_V2_ENABLED не встановлено: entrypoint не підключає новий backend. `EWU_V2_ENABLED=1` потребує reviewed policy, PostgreSQL DSN з verify-full і вже застосованої schema version1. Запуск не мігрує БД, не створює Telegram identity чи Sheets файл і не змінює старі таблиці. Активний Railway consumer ще невідомий — не запускати цей режим у production зараз.

Поточні команди нового adapter:

- `/start` → мова UA/PL/RU/EN/UZ → notice → acknowledgement; `/privacy` повторює notice.
- `/profile`, `/vacancies`, `/apply VACANCY_ID`, `/on_the_way APPLICATION_ID`, `/arrived APPLICATION_ID`, `/resume APPLICATION_ID`, `/alternatives APPLICATION_ID`.
- `/my_data`, `/rectify`, `/copy_data`, `/delete_data`, `/withdraw`, `/object`, `/restrict`; requests з винятками — оператору, не automatic erasure.
- `/consent` показує тільки configured/reviewed purpose-specific тексти; refusal/withdrawal не вимикає lawful core. `/stop_reminders` вимикає нагадування окремо.
- Owner-only `/ai_off`; core залишається доступним. `/dashboard` перевіряє role й приховує finance від recruiter.
- Role-scoped `/confirm APPLICATION_ID STATUS`; `/instructions APPLICATION_ID JSON` (verified fields); `/partner JSON`, `/vacancy JSON`, `/commission JSON` — тільки відповідні authorized roles. JSON keys відповідають service signatures; не вставляти credentials або реальні документи.
- `/quality APPLICATION_ID yes/no yes/no yes/no yes/no`: conditions/rate/housing/needs_help, тільки після STARTED_WORK; приватно оператору.

Invoice/payment attestations, actor grants і recruiter assignment доступні через authenticated backend methods; окремої завершеної web admin UI немає. Не передавати actor ID/role з довільного HTTP body у майбутніх адаптерах.

## Моніторинг

Контролювати consumer count і Telegram 409 конфлікти, lag outbox pending/leased, dead/uncertain jobs, старі rights requests, vacancy expiry, overdue tasks, DB availability, AI reservations/errors і бюджет, Google quotas/429, delivery confirmation та CRM snapshot age. Readiness helper `ewu.health.readiness` не замінює справжній deployment probe. Legacy Node /api/health не перевіряє DB або polling.

Logs: тільки fixed event identifiers/aggregates, не raw exceptions, profiles, tokens, consent texts або URL із бот-токеном. Restricted forensic logs, якщо потрібні, мають свою approved retention/access policy. Telegram SDK logging у runtime вимкнене.

## Черги і невизначена доставка

Worker leases переживають restart і мають bounded retry/backoff. Sheets retries замінюють canonical snapshot без append. Telegram delivery фіксує attempted до мережі; uncertain не повторюється автоматично. Перевірити фактичну доставку через authorized operator workflow, задокументувати рішення і лише потім ручне replay/new task. Не скидати ledger наосліп. Transportless partner/Operations jobs залишаються pending: це блокер інтеграції, не успішна доставка.

Нагадування обмежені attempts/interval, перевіряють privacy/preferences перед виконанням. No-response → ON_HOLD, а не нескінченний spam. При відновленні кандидат може /profile або /resume; старі applications не перезаписуються.

## Rights / security / incidents

Оператор перевіряє scope/identity/legal exceptions, координує copy/rectification/restriction/erasure у DB/Sheets/GreenWork/Telegram/processors/backups. Pending request не означає fulfilled. Retention planner дає прострочені IDs без автоматичного видалення; approved evidence disposition ще потрібно реалізувати/затвердити. Не зберігати audit evidence безстроково лише через append-only trigger.

Database runtime role не повинен бути schema owner; append-only guards/hash verification захищають від звичайного несанкціонованого редагування, але не від привілейованого DB administrator, здатного переписати schema/весь chain. Owner може викликати verify_audit; зберігати незалежні захищені checkpoints/backups.

Інцидент: обмежити доступ/автоматичні відправки за погодженим runbook, зберегти restricted evidence, повідомити owner/DPO, перевірити recipients і визначити юридичні notification obligations. Не видаляти дані або зупиняти production автоматично. Відкликання credentials і external sharing — окреме authorized рішення, не команда бота.

## Вартість і ліміти

Платний AI не підключено; live AI calls/витрат під час робіт не було. Точні Railway/PostgreSQL/Google/AI витрати невідомі без планів і доступів. Оцінювати за формулою: hosting + DB/storage/backups + Sheets requests/quota + approved provider input/output token cost × обсяг + notification/операторські витрати. Поточний snapshot sync O(число рядків × частота подій), тому до production потрібні load/quota tests і batching; не вважати його безкоштовним або необмеженим.

AI budget у коді — persisted lifetime reservation cap і per-request bound; реальний provider також потребує власного hard billing cap/usage reconciliation. Інтеграції не активувати заради демонстрації без доступів і budget approval.
