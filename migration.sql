-- DRAFT: apply only to an isolated restore first; production requires approval.
BEGIN;
SET LOCAL lock_timeout = '3s';
ALTER TABLE candidates ADD COLUMN ewu_application_id uuid REFERENCES ewu_applications(id);
CREATE UNIQUE INDEX candidates_ewu_application_unique ON candidates(ewu_application_id);
CREATE TABLE ewu_processed_updates (
 bot_id bigint NOT NULL, update_id bigint NOT NULL, processed_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(bot_id,update_id)
);
CREATE TABLE ewu_sync_jobs (
 application_id uuid PRIMARY KEY REFERENCES ewu_applications(id),
 attempts integer NOT NULL DEFAULT 0,
 next_attempt_at timestamptz NOT NULL DEFAULT now(),
 completed_at timestamptz,
 last_error_code text,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ewu_sync_due ON ewu_sync_jobs(next_attempt_at) WHERE completed_at IS NULL;
CREATE OR REPLACE FUNCTION ewu_enqueue_candidate() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.kind = 'candidate' THEN
  INSERT INTO ewu_sync_jobs(application_id) VALUES(NEW.id) ON CONFLICT DO NOTHING;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER ewu_enqueue_candidate_after_insert AFTER INSERT ON ewu_applications
FOR EACH ROW EXECUTE FUNCTION ewu_enqueue_candidate();

CREATE TABLE ewu_delivery_jobs (
 id bigserial PRIMARY KEY,
 bot_id bigint NOT NULL,update_id bigint NOT NULL,ordinal integer NOT NULL,
 chat_id bigint NOT NULL,payload jsonb NOT NULL,
 attempts integer NOT NULL DEFAULT 0,next_attempt_at timestamptz NOT NULL DEFAULT now(),
 sent_at timestamptz, telegram_message_id bigint,
 blocked boolean NOT NULL DEFAULT false,last_error_code text,
 created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(bot_id,update_id,ordinal)
);
CREATE INDEX ewu_delivery_due ON ewu_delivery_jobs(next_attempt_at) WHERE sent_at IS NULL AND NOT blocked;
CREATE TABLE ewu_error_events (
 id bigserial PRIMARY KEY,component text NOT NULL,
 reference_id text,error_code text NOT NULL,created_at timestamptz NOT NULL DEFAULT now()
);
COMMIT;
