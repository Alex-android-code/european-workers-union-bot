# EWU Scout — isolated development branch

This branch is reserved for the **EWU Scout** integration, independently from the existing production EWU bot.

Verified on 2026-10-25:
- EWU CRM sheet: `1UG_Gy-AaUbJpQOs_UdPwvIJX9eVB_u50XG8fBr7A1ws`
- Candidate columns: ID кандидата, Ім’я та прізвище, Місто, Професія
- Employer columns: ID заявки, Компанія, Локація роботи, Професія
- Local Python/SQLite MVP: dashboard, lead deduplication, matching, activity history
- Read-only CSV bridge: previews and optionally imports **into isolated Scout SQLite only**
- Eight unit tests passing in isolated runtime

Production EWU bot, PostgreSQL, Google Sheets and Telegram tokens remain untouched. Outbound messaging, cloud deployment, live Google Sheets API sync, and self-modifying production code are **not enabled**.

The runnable source package is delivered in the conversation as EWU_Scout_MVP_v2.zip. Do not commit candidate personal data or secrets.

Next engineering gate: scoped read-only Sheets OAuth and Telegram bot admin credentials, isolated test environment, explicit deployment rollback checks.
