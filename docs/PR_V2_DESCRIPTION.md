# Add gated EWU recruitment backend and synthetic end-to-end validation

EWU currently has conflicting Python/Node startup configurations and a Node-only GreenWork database bridge. This change records the evidence and adds an explicitly disabled modular backend for the existing Python bot, without selecting or replacing a production consumer.

The backend provides canonical candidates and multiple applications, approved privacy/optional-purpose gates, scoped partner confirmations, verified vacancy matching, bounded follow-ups, arrival/start separation, finance deduplication and event-derived reporting. Transactional outbox adapters support one-way nine-tab Sheets projection, uncertain notification reconciliation and future reviewed partner delivery. AI uses a deterministic fallback with a provider/legal/consent/budget/Kill Switch boundary; no paid provider is connected.

Additive `ewu2_*` migrations, append-only evidence guards, role template, non-destructive rollback, staging-only backup/migration tools and deployment templates accompany synthetic tests, PostgreSQL-compatible SQL replay and documentation.

**Do not merge/deploy as a complete production release:** Railway consumer/DB and GreenWork/mobile contracts remain unverified; legal facts/permissions, live Sheets/partner integrations, real PostgreSQL backup/restore and staging acceptance remain blocked. The branch includes the previous RODO changes that disable legacy forwarding/GreenWork/AI, so consolidation compatibility requires explicit review.

See EWU_AUDIT.md, EWU_IMPLEMENTATION_REPORT.md and EWU_TEST_RESULTS.md for evidence, limitations and exact validation. No production token, live candidate data, paid AI, production SQL or deployment was used.
