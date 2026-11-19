# EWU Partner Vacancies — Integration Specification (2026-11-19)

## Source
Partner-provided spreadsheet: https://docs.google.com/spreadsheets/d/1JOGzOZ7Wv5RYN6VesoHIlp1aUQ3hsYnl/edit
This URL currently resolves to an Office spreadsheet hosted on Google Drive, **not** a native Google Sheet. Do not use Google Sheets API on this file. Use a permitted Drive export/download or an explicitly authorized read-only integration.

## Import contract
Read source without changing it. Map fields: ID, Статус предложения, Проект / заказчик, Город / местоположение, Кого мы ищем на работу:, Количество, Тип работы, ЗАРАБОТНАЯ ПЛАТА, Премии / доплаты, Часы / RBH, Жильё — ссылка на папку с фото и видео, Транспорт, Фотографии предприятия — ссылка, Офис (оформление).

Create normalized records with source_row, source_file_id, source_updated_at, partner_project, location, slots_reported, eligibility, pay_raw, pay_net_min, pay_net_max, hours_raw, housing_raw, transport_raw, bonus_raw, source_status, verification_status, last_verified_at, publish_allowed, and last_imported_at. Keep raw text alongside any parsed fields. Never silently infer missing pay, housing, employment contract, or eligibility.

## Lifecycle
Source status 'Активная' means reported active, not confirmed availability. Newly imported records are DRAFT_PENDING_VERIFICATION. Only VERIFIED + publish_allowed records can appear publicly. Closed records are hidden, never deleted. Missing records are flagged for manual review, not automatically deleted. Re-import must be idempotent using (source_file_id, source_row) plus content hash and preserve recruiter notes.

## Matching
Candidate preferences: location, relocation, documents/work authorization, housing need, shift constraints, languages, skills, start date. Filter on confirmed mandatory requirements, then rank by fit and explain reasons. Do not auto-reject solely based on nationality, age or gender from partner descriptions; flag potentially discriminatory restrictions for legal review. Do not transfer identity documents to public spreadsheets or Telegram groups.

## Workflow
Partner verification -> approved vacancy -> multilingual Telegram listing -> candidate consent/application -> CRM review -> partner referral -> start confirmed -> verified hours -> commission ledger. Do not send partner referrals or publish offers without approval. Commission values are contractual, not assumed from the vacancy sheet.

## Initial sample rows for validation
Amazon Nowa Niedrzwica: 20 reported slots; Empik Sochaczew: 15; Allegro Łódź: 10; InPost DC9 Wola Bykowska: 9; Allegro Piotrków Trybunalski: 6. All remain pending partner confirmation.

## Acceptance criteria
1. Source file remains unchanged.
2. Imports are repeatable with zero duplicates.
3. Closed/unverified jobs cannot be published.
4. Candidate PII is stored only in protected CRM with consent and role-based access.
5. Existing EWU candidate, employer, and legalization flows remain functional.
6. Audit logs record source updates, verification decisions, and referrals.
7. Tests cover malformed rows, duplicate imports, missing pay, status changes, and permission boundaries.

This document is a design specification, **not** an implemented importer or production deployment.
