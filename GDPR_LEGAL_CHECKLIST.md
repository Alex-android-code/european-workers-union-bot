# GDPR / RODO — юридична перевірка до активації

Технічні тести не є підтвердженням юридичної відповідності. Власник/юрист має заповнити й затвердити `PRIVACY_CONFIG_FILE`; приклад навмисно невалідний. Нове ядро вимкнене за замовчуванням.

## Controller та інформаційний обов'язок

- [ ] Реальне найменування controller, юридична адреса, privacy contact і DPO, якщо потрібен.
- [ ] Версія та effective_at з timezone; approved notice UA/PL/RU/EN/UZ. Особлива перевірка узбецького перекладу.
- [ ] Цілі та підстави окремо для recruitment, contact, evidence, rights, notifications, partner transfer, CRM, AI і commissions.
- [ ] Обґрунтування art6_1_b/c/f там, де застосовується; LIA для legitimate interest. Не приймати consent за замовчуванням.
- [ ] Наслідки ненадання, категорії recipients, фактичні строки/тригери retention, права, компетентний наглядовий орган і complaint route.
- [ ] Доступна повна HTTPS Polityka prywatności; юридична точність і доступність URL перевіряються людиною.

## Consents / AI / передавання

- [ ] Optional purposes мають власний approved текст усіма мовами, добровільні grant/refuse/withdraw. Відмова не блокує core service.
- [ ] Якщо AI потребує consent, purpose `ai_profile` має бути окремо погоджений; інша підстава теж потребує юридичного висновку.
- [ ] AI provider, disclosure, budget, retention/training terms та можливість human review погоджені; автономні юридично значущі рішення заборонені.
- [ ] Partner transfer scope, lawful basis та обов'язки controller/processor погоджені до `partner_transfer_approved=true`.
- [ ] DPA/controller-to-controller terms для партнерів, Google, Railway/DB/backup/AI provider; роль і умови Telegram.
- [ ] Перевірка international transfers, SCC/TIA/adequacy та субпроцесорів, де потрібно.
- [ ] DPIA threshold assessment; DPIA і профілювання/automated decision assessment, якщо потрібні.

## Права, retention та інциденти

- [ ] Процедури access, rectification, portability/copy, erasure, restriction, objection, withdrawal; identity verification та response SLA.
- [ ] Pending rights request передається оператору; не вважати request виконаним або identity автоматично достатньою для всіх юридичних дій.
- [ ] Erasure inventory: legacy ewu_*, candidates/GreenWork, SQLite, Sheets, Google revision history, Telegram forwards, processors, exports і backups.
- [ ] Legal holds/finance retention і disposition audit evidence. Append-only таблиці не повинні зберігати особисті дані безстроково: потрібна окрема approved admin retention/redaction процедура. У цій версії automated erasure evidence не реалізовано; planner лише позначає прострочені картки.
- [ ] Обмеження partner data доступом лише до своїх submitted applications. Весь файл Sheets доступний лише approved owner/finance: Google Sheets не забезпечує read-isolation фінансової вкладки від інших редакторів цього самого файла.
- [ ] Encryption at rest, transport TLS, secrets rotation, мінімальні scopes, runtime non-owner DB role, restricted logs/backups.
- [ ] План breach response: виявлення, containment без стирання доказів, controller/DPO escalation, оцінка notification deadlines, повідомлення постраждалих/органу за рішенням відповідальної особи.
- [ ] Тест із синтетичними даними; нова lawful intake processing не активується до всіх необхідних погоджень.

`legal_review_approved`, `sheets_approved`, `partner_transfer_approved`, `notifications_approved`, `ai_approved` — технічні release gates, а не автоматичні юридичні висновки. Немає підстав заповнювати їх true лише для проходження тесту в реальній конфігурації.
