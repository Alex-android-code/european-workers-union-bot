# Add privacy notice onboarding before EWU Telegram intake

Both EWU bot entrypoints previously requested or recorded personal data before showing a privacy notice. This change gates questionnaires on a versioned four-language notice, distinguishes acknowledgement from consent, persists privacy decisions, blocks intake after withdrawal, and queues deletion requests without claiming deletion is complete.

Optional AI/scoring, GreenWork copies, Telegram group/admin forwarding and raw transcript storage are disabled. Legal facts must be supplied through validated external configuration; missing configuration fails closed. Python now saves minimized selected intake forms locally after acknowledgement rather than silently forwarding free text. Node retains minimized core intake behind the gate. See `docs/PRIVACY_REVIEW.md` for configuration, compatibility changes, retention behavior and legal release gates.

Validation: 24 Python tests passed (15 onboarding/intake tests and all 9 existing publisher tests); 8 Node tests passed (7 transport/transaction tests and 1 isolated in-memory PostgreSQL-compatible SQL integration test). Frozen dependency installation with `npm ci --offline --ignore-scripts` and syntax/diff checks passed. No production token, live Telegram calls, working database changes or deployment.

Review before release: legal sign-off on every translated notice, core legal basis, periods, controller/processor details, rights handling and legacy data; persistent protected storage; dedicated staging validation. This PR is not production GDPR certification. Deletion requests require an authorized operator to complete the documented procedure.
