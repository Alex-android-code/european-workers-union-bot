# EWU canonical data model і Google Sheets

Джерело істини — запропонована PostgreSQL namespace `ewu2_*`, після підтвердження придатності deployment. SQLite in-memory використовується для синтетичних тестів. Міграція additive, legacy `candidates`, `ewu_*` і RODO SQLite не змінюються/не імпортуються.

## Реляційні сутності

| Сутність | Таблиця / інваріанти |
|---|---|
| Candidate | ewu2_candidates; UUID text PK, UNIQUE telegram_id; language, allowlisted profile, recruiter, status, restricted, UTC timestamps |
| CandidateContact | ewu2_contacts; FK candidate, UNIQUE candidate/kind; phone поза довільним profile JSON |
| PrivacyRecord | ewu2_privacy_records; snapshot/version/revision/lang/action/user/source/UTC/hash, append-only trigger |
| Partner | ewu2_partners; окрема identity; scoped actors у ewu2_actors |
| Vacancy | ewu2_vacancies; FK partner, UNIQUE partner/external_id, verified conditions/expiry |
| Application | ewu2_applications; незалежний UUID, candidate/vacancy/partner FKs; UNIQUE candidate/vacancy |
| RecruitmentEvent | ewu2_recruitment_events; from/to/actor/UTC; immutable |
| FollowUp | ewu2_followups; application або candidate/profile target, due UTC, bounded attempts/interval; one pending per target |
| ArrivalConfirmation | ewu2_arrivals; self-report окремо від authorized confirmation |
| EmploymentStart | ewu2_employment_starts; UNIQUE application, authorized actor/time |
| Commission | ewu2_commissions; UNIQUE application, minor currency units, terms/reference/period, review/invoice/payment fields |
| AuditEvent | ewu2_audit_events; pointer-only event metadata, chain через locked audit_head |

Додатково: privacy_state/consents/rights_requests, outbox/leases, Telegram processed_updates/sessions, ai_usage reservations, delivery ledger, notification preferences, private quality reports і schema_version. SQL-індекси — у `migrations/001_recruitment.up.sql`.

Текстові UTC ISO timestamps вибрані для спільного SQL test adapter; input без timezone для domain dates відхиляється. PostgreSQL types/index strategy і навантаження треба окремо перевірити перед production migration; фізичний native UUID/timestamptz upgrade потребує наступної versioned migration, не неявного cast на робочій БД.

## Sheets: одна погоджена CRM

Google adapter використовує **наявний, явно заданий** `GOOGLE_SHEETS_ID`. Автоматичного створення ще одного файла при відсутньому ID немає. Назву EWU Recruitment CRM і ownership потрібно погодити з власником до provisioning; реальний файл у цьому середовищі не створено.

Вкладки: Candidates, Candidate_Card, Vacancies, Applications, Partners, Follow_Ups, Activity_Log, Commissions, Dashboard. Код headers/projection — `ewu/sheets.py`.

Candidates містить ID, name/phone/Telegram ID/language, city/profession/location/experience/housing/relocation/availability, restriction/recruiter/next action/latest application status. Username не збирається за замовчуванням (мінімізація). Candidate_Card вибирається явно через configured candidate ID і показує профіль, заявки, партнерів, events/arrival/start/task timestamps. Подальший контрольований UI для вибору картки і ручних правок — окремий adapter; raw редагування Sheets не імпортується в БД.

Vacancies зберігає лише підтверджені реєстрові умови, partner identity, confirmation/status. Applications не перезаписує попередні заявки. Activity_Log будується зі справжніх transition events. Commissions і Dashboard — із ledger/подій; paid не виникає від самого обчислення суми. Неперевірені quality reports не публікуються в Sheets як рейтинг.

Sync замінює canonical snapshot атомарним batchUpdate, а не append. Повтори після timeout не створюють дублі кандидатів. Рядки, прибрані з canonical projection після дозволеної disposition, не залишаються хвостом старого snapshot; Google revision history/backups потребують окремої erasure policy. stringValue/RAW semantics не виконують формули з кандидатських полів.

### Межі доступу

Партнери не отримують спільний файл. Оскільки захищена/прихована вкладка не є read access boundary, весь CRM-файл з Commissions дозволений лише owner/finance. Recruiting role може використовувати backend без фінансових полів; якщо потрібен Sheets-доступ рекрутерів, власник має юридично й технічно погодити інший механізм redacted access, не відкривати фінанси всім редакторам. Permissions реального файла ще не перевірені.

### Дані, яких не має бути в Sheets

Паспортні скани, PESEL, медичні дані, credentials, повні transcript/documents, необмежені free-text notes. Allowlist не може завадити людині ввести PII у поле name: потрібні operator policy, training, контролі експорту і процедура remediation.
