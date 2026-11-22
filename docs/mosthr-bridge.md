# MostHR bridge

Optional feature, disabled unless `MOSTHR_ENABLED=true`. The full contract and launch checklist live in the private MostHR repository's `EWU_INTEGRATION.md` on the matching feature branch.

Set `MOSTHR_URL` to the HTTPS origin, `MOSTHR_BRIDGE_KEY` to a dedicated >=32-character secret shared with MostHR, and `MOSTHR_SUBJECT_SECRET` to a different stable >=32-character secret. See `.env.mosthr.example`; never commit values. A configuration/initialization failure disables only this integration.

Private-chat commands: `/jobs` (five offers per page, `/jobs 2` for the next page), a `mhr_UUID` deep link to one published offer, `/agree`, `/cancel`, `/status`. The bot uses the existing session language or Telegram language, supports all seven current languages, and keeps the existing candidate/employer/legal flows. New MostHR forms use only name, phone, city, experience and explicit availability; they bypass legacy message logs, AI, group notifications and candidate synchronization.

The candidate sees a named recipient and its privacy notice before the questionnaire. Forms expire in 24h. Submission payloads are retained in the PostgreSQL outbox for at most seven days and removed immediately on delivery or terminal refusal. Delivery metadata expires after 90 days. Review these pilot defaults and the actual controller notices before real use.

The worker polls due entries every 15 seconds; normal status checks are scheduled at 60-second intervals with exponential backoff on temporary failures. Lost acknowledgements retry the same request identity. MostHR also deduplicates per publication/candidate. Notifications are at least once; a crash between Telegram delivery and SQL commit can duplicate a message. The bot never reports successful agency delivery before MostHR acknowledges it. Manual `/status` reads the last locally confirmed stage.

Tests: `node --test tests/mosthr-bridge.test.js`; existing publisher tests: `python3 -m unittest discover -s tests -p 'test_*.py'`. For the cross-repository HTTP test run MostHR's tests with `EWU_ADAPTER_PATH=/absolute/path/to/this/mosthr-bridge.js`.

No deployment, existing-applicant transfer, public channel posting, AI analysis or new paid resource is performed by adding this code. Stage with a separate bot/token and test PostgreSQL first; never start a second poller against the production token. Rollback: set `MOSTHR_ENABLED=false` and restart the one bot process. Additive tables can remain for audit/retention; do not drop them automatically.
