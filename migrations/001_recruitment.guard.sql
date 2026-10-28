-- PostgreSQL append-only guards; apply after up migration, within the same transaction.
CREATE FUNCTION ewu2_reject_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'EWU append-only evidence'; END;
$$;
CREATE TRIGGER ewu2_privacy_immutable BEFORE UPDATE OR DELETE ON ewu2_privacy_records FOR EACH ROW EXECUTE FUNCTION ewu2_reject_mutation();
CREATE TRIGGER ewu2_audit_immutable BEFORE UPDATE OR DELETE ON ewu2_audit_events FOR EACH ROW EXECUTE FUNCTION ewu2_reject_mutation();
CREATE TRIGGER ewu2_history_immutable BEFORE UPDATE OR DELETE ON ewu2_recruitment_events FOR EACH ROW EXECUTE FUNCTION ewu2_reject_mutation();
