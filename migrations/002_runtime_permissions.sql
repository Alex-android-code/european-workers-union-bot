-- Operator-reviewed privilege template, NOT run by application/migration 001.
-- A separate login member of an existing ewu2_runtime role must be provisioned
-- securely by the DB administrator. No passwords, role creation or global/public
-- schema changes are included. Review compatibility with the actual DB first.
REVOKE ALL ON ewu2_privacy_records, ewu2_audit_events, ewu2_recruitment_events FROM PUBLIC;
GRANT SELECT, INSERT ON ewu2_privacy_records, ewu2_audit_events, ewu2_recruitment_events TO ewu2_runtime;
GRANT SELECT ON ewu2_schema_version TO ewu2_runtime;
GRANT SELECT,INSERT,UPDATE,DELETE ON ewu2_actors,ewu2_settings,ewu2_candidates,ewu2_contacts,
 ewu2_partners,ewu2_vacancies,ewu2_applications,ewu2_privacy_state,ewu2_consents,ewu2_rights_requests,
 ewu2_followups,ewu2_arrivals,ewu2_employment_starts,ewu2_commissions,ewu2_quality_reports,
 ewu2_audit_head,ewu2_outbox,ewu2_processed_updates,ewu2_sessions,ewu2_ai_usage,
 ewu2_notification_preferences,ewu2_deliveries TO ewu2_runtime;
