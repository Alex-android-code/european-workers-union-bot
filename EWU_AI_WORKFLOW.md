# EWU recruitment workflow та AI boundary

## Стани й підтвердження

`NEW → PRIVACY_COMPLETED → PROFILE_IN_PROGRESS → PROFILE_COMPLETE → MATCHED → INTERESTED → SUBMITTED_TO_PARTNER → PARTNER_REVIEW → ACCEPTED → START_DATE_CONFIRMED → TRAVEL_PLANNED → ON_THE_WAY → ARRIVED → CHECKED_IN → STARTED_WORK`.

Дозволені branches: REJECTED після partner submission/review/acceptance; CANCELLED/ON_HOLD для non-terminal станів; ON_HOLD → INTERESTED за дією кандидата. Фактична transition matrix — `ewu/domain.py`, не довільний LLM output.

Кандидат існує до вибору вакансії. Після /apply створюється Application і перевірені вже наявні privacy/profile facts записуються як bootstrap transitions цієї заявки; реальний час ознайомлення зберігається окремо в privacy ledger. Не трактувати bootstrap timestamps як історичний час первинного заповнення профілю.

Кандидат може повідомити ON_THE_WAY/ARRIVED; тільки scoped partner/owner може підтвердити ACCEPTED/CHECKED_IN/STARTED_WORK. Travel instructions потребують перевірених address/arrival_at/coordinator/transport/packing. Self-report прибуття не створює employment/commission. Партнерська delivery queue не означає partner receipt; PARTNER_REVIEW і ACCEPTED потребують окремої авторизованої дії.

## AI

Поточна runnable реалізація — deterministic multilingual анкета плюс verified vacancy fallback. Provider port `rank(request,max_cost_minor)` опційний; live LLM, природномовний production-діалог і конкретний платний vendor не підключені/не перевірені. Це не видається за завершеного AI-рекрутера.

Provider отримує лише registry IDs/conditions і обмежений untrusted job preference, без імен, телефонів, Telegram ID чи даних інших кандидатів. Відповідь — IDs і cost, а не нові умови. Невідомі/повторні IDs, додаткові fields або неправильний cost → fallback/human handoff. Displayed rates/conditions завжди читаються з реєстру. Provider не має SQL/tools для змін, role assignment або юридичних рішень.

Потрібні одночасно: owner Kill Switch enabled, approved AI legal basis, за потреби purpose-specific consent, explicit budget approval, positive lifetime budget і per-request cap. Reservation у БД переживає restart. Помилка/невизначена вартість консервативно витрачає reservation; автоматичного reset бюджету немає. Реальні provider token limits/billing hard caps мають бути налаштовані і протестовані окремо перед live використанням; adapter contract сам не гарантує поведінку зовнішнього постачальника.

`/ai_off` owner-only; backend ai_switch зберігає стан без зупинки polling/core/CRM. Відмова від optional consent не блокує lawfully available core workflow. Prompt injection обмежується мінімальним input і allowlist output, а не лише інструкцією в prompt.

## Worker, альтернативи, якість

Confirmed-only matches можна повторно запитати після REJECTED/closed/stale vacancy або зміни бажання без повторної анкети. Новий vacancy → окремий Application; інший partner не отримує дані автоматично. Повністю автономний background alternative outreach не активовано до погодження transfer/communication policy.

Незавершений profile створює candidate ID і bounded profile reminder task; повтори не дублюють pending task. Application follow-ups також bounded (1–3 attempts, interval >=12h), exhaustion → ON_HOLD і operator task. /stop_reminders не блокує core service. Worker повторно перевіряє privacy і notification preference перед відправкою. Telegram uncertain delivery не retry-иться наосліп.

Quality feedback після STARTED_WORK — структуровані boolean answers, private operator review; жодних автоматичних публічних employer ratings. Hourly/one-time commission потребує confirmed start, approved contract/rate/units/period; інші моделі — майбутнє розширення.
