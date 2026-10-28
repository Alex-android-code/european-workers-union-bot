-- Non-destructive application rollback: do NOT drop schema or candidate history.
-- Disable EWU_V2_ENABLED in the reviewed target environment, return to the previously
-- approved artifact/consumer, and keep these tables for reconciliation. This file
-- deliberately performs no DROP/DELETE. Never run runtime rollback automatically.
SELECT version FROM ewu2_schema_version WHERE version=1;
