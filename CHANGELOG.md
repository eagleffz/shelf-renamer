# Changelog

## v1.20.1

- Add `ALLOWED_ORIGINS` for explicit comma-separated HTTP(S) origins, shared by the cross-origin write guard and credentialed CORS. Wire the setting through Docker Compose and validate it at startup.

## v1.20.0

- Bind execution to signed previews; reject stale plans, duplicate destinations, overlapping paths, invalid templates, and unsafe mappings.
- Use atomic no-overwrite filesystem operations with symlink protection and mutation locking.
- Journal operations before moving files; preserve partial results and history, and report rescan failures with recovery actions.
- Preserve single-file extensions when the final template segment is empty.
- Separate current naming status from history; correct filtered selection and show hidden selections.
- Add saved template presets, metadata warnings, searchable library filters, empty/error states, and accessible controls.
- Keep batch edits across tabs, guard unsaved navigation, show per-row failures, and preserve additional ABS series memberships.
- Scope cleanup to the selected library and require a reviewed folder list.
- Replace browser-stored bearer tokens with expiring, revocable HttpOnly cookie sessions and throttle login attempts.
- Pin runtime and test dependencies separately, update vulnerable frontend dependencies, add frontend regression tests and CI lint/test gates, and use Node 24 for builds.

Upgrade notes: sessions and previews must be recreated after restart. API rename callers must provide preview tokens. The `/verify` endpoint is removed. Explicit volume maps no longer silently fall back for unmapped libraries. Keep the default single-worker deployment. Existing SQLite history is migrated automatically; back up the data volume before upgrading.
