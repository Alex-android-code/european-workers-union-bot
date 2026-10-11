-- Counts only. No names, phones, text or Telegram IDs in output.
SELECT
 (SELECT count(*) FROM ewu_applications WHERE kind='candidate') AS candidate_applications,
 (SELECT count(*) FROM candidates WHERE ewu_application_id IS NOT NULL) AS linked_candidates,
 (SELECT count(*) FROM ewu_applications a WHERE kind='candidate' AND NOT EXISTS(SELECT 1 FROM candidates c WHERE c.ewu_application_id=a.id)) AS missing_candidates,
 (SELECT count(*) FROM ewu_sync_jobs WHERE completed_at IS NULL) AS sync_pending,
 (SELECT count(*) FROM ewu_delivery_jobs WHERE sent_at IS NULL) AS delivery_pending,
 (SELECT count(*) FROM ewu_delivery_jobs WHERE sent_at IS NULL AND blocked) AS delivery_blocked,
 (SELECT count(*) FROM ewu_error_events WHERE created_at>now()-interval '24 hours') AS errors_24h;
