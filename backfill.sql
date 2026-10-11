-- Run after migration. Fail closed on any ambiguous historical identity.
BEGIN;
SET LOCAL lock_timeout='3s';
LOCK TABLE ewu_applications,candidates IN SHARE ROW EXCLUSIVE MODE;
DO $$ BEGIN
 IF EXISTS (SELECT a.id FROM ewu_applications a JOIN candidates c
   ON c.source='EWU Telegram' AND c.telegram_chat=a.telegram_id::text
   AND c.phone=a.phone AND c.full_name=a.full_name
   WHERE a.kind='candidate' GROUP BY a.id HAVING count(*)>1)
 OR EXISTS (SELECT c.id FROM candidates c JOIN ewu_applications a
   ON c.source='EWU Telegram' AND c.telegram_chat=a.telegram_id::text
   AND c.phone=a.phone AND c.full_name=a.full_name
   WHERE a.kind='candidate' GROUP BY c.id HAVING count(*)>1)
 THEN RAISE EXCEPTION 'Ambiguous backfill identity: private review required'; END IF;
END $$;
UPDATE candidates c SET ewu_application_id=a.id FROM ewu_applications a
 WHERE a.kind='candidate' AND c.source='EWU Telegram'
 AND c.telegram_chat=a.telegram_id::text AND c.phone=a.phone AND c.full_name=a.full_name
 AND c.ewu_application_id IS NULL;
INSERT INTO ewu_sync_jobs(application_id,completed_at)
 SELECT a.id,CASE WHEN EXISTS(SELECT 1 FROM candidates c WHERE c.ewu_application_id=a.id) THEN now() ELSE NULL END
 FROM ewu_applications a WHERE a.kind='candidate'
 ON CONFLICT(application_id) DO NOTHING;
COMMIT;
