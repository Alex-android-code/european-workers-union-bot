# EWU — результати перевірок

Дата: 2026-10-28. Branch: feat/ewu-v2-foundation. Дані виключно synthetic; жодної доставки реальним кандидатам/партнерам або production SQL.

## Виконано

| Перевірка | Результат |
|---|---|
| Python unittest discover `test_*.py` | 49 passed, 0 failed, 0 skipped: 9 існуючих publisher + 15 RODO/intake + 25 v2 backend/transport/security tests |
| Node `tests/privacy.test.js` | 7 passed, 0 failed/skipped |
| Node `tests/privacy-pg.test.js` | 3 passed, 0 failed/skipped: legacy SQL integration, new migration/guards/permissions/rollback, full Python scenario SQL replay |
| pip check | No broken requirements found |
| Node syntax (bot.js, privacy/node.js) | Passed |
| git diff --check | Passed |

Команди (локальний venv; CI використовує python після install requirements):

```sh
PYTHONDONTWRITEBYTECODE=1 /workspace/ewu-venv/bin/python -m unittest discover -s tests -p 'test_*.py'
EWU_TEST_PYTHON=/workspace/ewu-venv/bin/python npm test
/workspace/ewu-venv/bin/python -m pip check
node --check bot.js
node --check privacy/node.js
git diff --check
```

Очікувані `privacy_configuration_unavailable` у negative tests — фіксовані event names без даних, не failures. Перший development run migration test виявив неправильний test expectation кількості таблиць; його виправлено під фактичну схему, потім перевірено актуальні 26 таблиць та guards/permissions. Невдалий development run не зарахований як passed.

## Наскрізний сценарій §20

`RecruitmentTests.test_full_twenty_step_synthetic_scenario` використовує fake Telegram transport того самого adapter, MemorySheets і delivery spies:

1. /start і вибір мови;
2. поточний notice та acknowledgement;
3. мінімальна анкета, Candidate ID;
4. одна CRM-картка без дублю після повторного /start;
5. verified vacancy match через fallback (не live model);
6. interest/Application ID;
7. partner submission outbox і authorized review/acceptance;
8. verified instructions і bounded reminder;
9. self arrival без employment;
10. окремі authorized check-in та actual work start;
11. оновлена CRM/Dashboard;
12. одна approved-terms commission, статус UNPAID;
13. audit/recruitment history і збереження identity після повторного запуску adapter.

У тесті є всі двадцять логічних контрольних точок специфікації, але Telegram, Sheets, partner API та AI зовнішні межі замінені synthetic/fallback adapters. Це **не** демонстрація live Google spreadsheet або природномовного AI.

Той самий сценарій експортує лише synthetic SQL/params і відтворює їх на PostgreSQL-сумісному PGlite з реальними up/guard migrations; перевіряє фінальні STARTED_WORK, canonical candidate, employment і UNPAID commission. Це сильніше за mock DB, але не замінює psycopg/network/TLS/version/load тест реальної PostgreSQL.

## Негативні/стійкі сценарії

Без notice/approval/current revision немає intake. Відмова від optional purpose не блокує core. Withdrawal/delete/object/restrict блокують нову обробку; pending requests не видаються за fulfilled. Перевірені role/partner isolation, false arrival vs start, невідомі/stale vacancies, finance access/duplicates, AI hallucinated IDs/PII minimization/budget/Kill Switch/consent, Google failure/retry/formula injection, Telegram duplicate state updates, uncertain notification no-retry, bounded profile/application followups, audit mutation rejection/hash verification, staging dry-run/no-I/O і TLS/webhook-secret guards.

Synthetic SQLite backup/restore зберігає identity/history; non-destructive migration rollback залишає evidence в PGlite. Реальний pg_dump/pg_restore tooling підготовлений, але не запусканий і не підтверджений.

## Не виконано / release blockers

- Railway logs/deployment/consumer/replicas inventory, Telegram webhook/polling conflicts.
- Real PostgreSQL migration/role/TLS/backup/restore і load tests.
- Docker build або compose startup.
- Live Google Sheets file, ownership/scopes, quotas та permissions; HRWork import mapping.
- GreenWork/mobile/Operations transports і delivery confirmations.
- Paid AI vendor, natural-language dialogue quality і real billing cap.
- Реальні юридичні notices/DPA/DPIA, automatic evidence disposition та повна зовнішня erasure procedure.
- GitHub Actions run: API Forbidden; CI definition не означає executed CI.

Підсумок: 59 офлайн-тестів пройшли. Жоден із перелічених live checks не замінено нульовим test run або позначено як готовий без виконання.
