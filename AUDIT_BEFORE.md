# Pre-change audit — 9 October 2026

Scope: active `run.py` / `app` application. Nested historical project copies are not deployment entry points. Archive configuration secrets were excluded from the working copy. No production service, email, or database was contacted.

Architecture: Flask 3, Jinja templates, SQLAlchemy, Flask-Login, Flask-WTF, Alembic; Bootstrap plus compiled portal CSS, vanilla JavaScript. Blueprint modules contain large controllers with duplicated query/sort logic. Existing services handle sessions, documents, blotters, email, and audit. Models already use primary/foreign keys and timestamp mixins. HTML form redirects and JSON endpoints coexist; converting all responses would break existing clients.

## Critical
- Profile images are accepted by extension without checking content. Requirements allow several document/image types without content verification; identification uploads do not have an image-only policy.
- Official approval activates unverified accounts and uses the resident birth date as the temporary password; it also manufactures email verification.
- Session lifecycle enforcement omits messaging/geocoding blueprints, despite role decorators on their routes.

## High
- Purok POST bypasses its existing form; raw name uniqueness allows case/whitespace variants. Flush happens outside integrity-error handling.
- Blotters use random references, newest-first sorting, and no duplicate-submission association.
- Requirement uploads have no owner download/view endpoint, replacement UI, or removal action.
- Existing tests: 16 passed, 9 failed. Several failures concern stale registration fixtures (missing required terms consent), absent approval callbacks, and a test using an unset PASSWORD environment variable.
- Bundled SQLite file has no `puroks` table. No live records were supplied for duplicate/orphan analysis.

## Medium
- Notification bell is a link in resident workspace; no shared polling panel for all roles.
- Real database Event model exists but dashboard calendar is absent.
- Chatbot exposes provider name in widget and serialized message sender.
- Sidebar exists in each workspace; resident header duplicates primary navigation. Layout caps usable width and stacks multiple theme overrides.
- Global after-request audit commits independently and suppresses audit failures; important services need transaction-local audit events.
- Some modules process direct form values rather than their validators; DRRM/collection/business workflows need broader negative-path coverage.

## UI completion checklist, recorded before edits
- [ ] Secure profile upload / preview / replace / remove.
- [ ] ID JPEG/PNG content validation and authorized view/replace/remove.
- [ ] Notification dropdown, count, read actions, loading/error/empty states.
- [ ] Calendar timezone, month controls, current date, actual event data.
- [ ] Configurable chatbot identity.
- [ ] Working approved-document download link.
- [ ] Purok labels, validation, edit/archive, empty state, pagination.
- [ ] Backend FIFO blotter queue and duplicate association history.
- [ ] Remove disabled Hold/Transfer, SMS, QR-pass affordances unless implemented.
- [ ] Map export currently announces coming soon; connect to browser print.
- [ ] Replace visible official-information TODO strings only with verified configuration or honest unavailable text.
- [ ] Responsive/keyboard/visual browser validation.

No draggable dashboard cards were found. Map markers and file-drop targets have legitimate drag behavior and should be preserved. Existing SVG symbol icons and left-side navigation should be reused.

## Validation plan
Use isolated SQLite test databases and temporary storage; exercise role/ownership denial, expired sessions, malformed and oversized uploads, Purok case/space/number duplicates, duplicate blotter association, FIFO order, notification ownership/read counts, calendar permissions/month boundaries, authentication and registration. Run migrations on scratch databases and compare metadata. Browser-check desktop/mobile when a browser is available. SMTP, external AI and deployment database require environment-specific acceptance; do not report them as tested.
