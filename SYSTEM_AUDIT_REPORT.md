# Barangay Management System — audit and revised release

Date: 9 October 2026. Input: yay.zip and the user-authored pasted request. The request was treated as the task instruction; project documents were inspected as project material. The original ZIP was not modified.

This is a tested revised application with substantial integrity, security, workflow, and interface fixes. It is not a certification that every subsystem is production ready. Section G identifies the remaining work and deployment checks explicitly.

## A. Architecture Before

The active application is Flask 3 with Jinja, Flask-SQLAlchemy, Flask-Login, Flask-WTF, Flask-Migrate/Alembic, Bootstrap, compiled Tailwind, and browser JavaScript. The ZIP also contained older nested project copies and local runtime artifacts. The active entry point was run.py and the root app package; nested copies were not treated as alternate runtime dependencies.

The administrator, official, and resident controllers mixed large amounts of request parsing, persistence, file handling, and presentation logic. Sorting helpers were duplicated and accepted arbitrary model attributes. Numeric form coercion could quietly convert malformed inputs into defaults. Most constraints relied on application code, while SQLite connections did not consistently enforce foreign keys.

Purok names had no canonical identity across case, whitespace, and numeric variants. New blotters lacked an exact-incident association mechanism and stable first-in ordering. Auditing could commit separately after the response, so it was not atomic with the underlying change. Upload policies were inconsistent and included unsupported image/document formats. Approval used predictable birthdate credentials and could manufacture email verification. Shared notification/calendar/profile controls were incomplete or inconsistent.

The bundled SQLite file did not contain the active application's tables. No live production dataset was available. The original targeted test suite had 16 passes and 9 failures; several failures reflected obsolete approval expectations and incomplete registration fixtures, alongside real security/workflow issues.

## B. Architecture After

The working Flask application and existing modules remain. New focused modules centralize normalization, decoded-image handling, safe sorting, strict numeric parsing, persistence validation, permission checks for shared features, and account-owned workspace APIs. Exact blotter submission logic now lives in a transaction-local service.

New modules include app/normalization.py, image_uploads.py, querying.py, form_values.py, model_validation.py, permissions.py, workspace.py, and blotter/submissions.py. Shared notification/calendar components, workspace.js, and workspace.css serve all three role layouts.

Audit records now join the data transaction through SQLAlchemy flush hooks. A rollback discards both the change and its audit. Existing role decorators remain on the established modules; this is an incremental refactor, not a claim that every legacy controller has been decomposed or that editable database Permission records drive every authorization decision.

The clean release contains the active application, migrations, tests, secure configuration example, and necessary account provisioning tools. It excludes real environment files, databases, uploaded IDs, local logs, caches, virtual environments, and older nested project copies. Those original files remain in the supplied archive.

## C. Database Changes

Migration a7c20d9e6410 follows f6b4d8e9c914.

- Purok.name_key: non-null canonical identity with a unique constraint.
- Purok.purok_number: optional numeric identity with a unique constraint.
- Purok checks: normalized trimmed display/name key, no repeated spaces, name length 2–100, numeric range 1–9999.
- User.profile_photo_filename: account profile image reference.
- BlotterCase.incident_fingerprint: optional unique exact-incident fingerprint.
- Blotter queue index: status and database ID.
- SQLite application connections: foreign-key enforcement enabled.

Existing relationships and record IDs were preserved; no production records were deleted or automatically merged. Migration preflight reports conflicting legacy Purok IDs and stops before schema changes. Non-conflicting Purok display names are canonicalized during backfill. Historical blotters retain their references and have no automatically inferred fingerprint.

SQLite batch migrations temporarily disable foreign keys only on the migration connection, check integrity before/after migration, then restore enforcement. Fresh upgrade, latest rollback/re-upgrade, duplicate refusal, canonical backfill, and preservation of linked household references were verified on scratch databases. Downgrade removes the new fields; it does not undo display-name normalization or restore dropped profile/fingerprint values. Always retain a backup.

The database guarantees uniqueness of stored canonical keys/numbers. Direct manual SQL must supply canonical identity correctly; application validation is the authority for parsing variants. Universal numeric/date constraints across every legacy table were not added.

## D. Backend Changes

- Purok create/edit/search/pagination/archive/restore validate canonical names and catch database conflicts safely. Archived identities cannot be recreated as duplicates.
- Staff have a read-only Purok registry; administrator mutation routes remain protected.
- Exact repeated new complaints associate with the original case and add an event/audit record. Association requires the same complainant, respondent, category, dates, location, Purok, narrative, and coordinates after normalization. Missing location/narrative keeps submissions separate. Unrelated incidents are not merged.
- New case references use the database ID rather than count-based allocation. Lists and live insertion preserve ascending submission order; active queue position uses the same order.
- Shared workspace endpoints return the signed-in user's notifications, unread count, timestamps, read updates, own profile images, and real published calendar events in the configured timezone.
- Image uploads enforce extension plus MIME agreement, decoded JPEG/PNG content, 5 MB, 20 megapixels, randomized names, and metadata-stripping re-encoding. Government IDs remain in private storage.
- Residents can upload/view/replace/remove their own requirements during pending/review; later processing states lock edits. Foreign owners receive 404. Required uploads must be present before processing/approval.
- Resident/official approval credentials are random temporary passwords with first-login change. Resident approval requires email verification by default. Administrator generic user creation includes confirmation and enforces configured minimum length.
- Administrators cannot deactivate themselves through the toggle route or delete an administrator through the official-account deletion route.
- Session expiry now covers messaging, geocoding, and workspace endpoints. Invalid session user IDs are handled safely.
- Common validators enforce required mapped values, string lengths, finite/nonnegative numbers, resident date bounds and household/Purok consistency, business date/status rules, incident dates/coordinates, and event time order.
- Numeric request inputs reject malformed/infinite values rather than silently substituting zero. Sorting accepts mapped columns only.
- Validation/conflict/CSRF/oversize failures have friendly HTML or JSON responses. Internal exceptions are logged instead of exposing database details in resident/user error messages.
- Dashboard-data returns actual database counts. Transaction-local automatic audits cover ordinary entity create/update/delete; sensitive field values are not copied into those generic records.
- The Docker entry point uses the production wsgi:app. Production rejects missing/default/short secrets. Development account seeding is blocked in production. The environment example contains no credentials.

## E. Frontend Changes

All role headers include the upper-right notification bell, unread badge, owned notification panel, read controls, timestamps, and polling without page refresh. Only the bell is the panel trigger. Panels have loading/error/empty states.

Dashboard layouts keep the sidebar on the left and put the real calendar on the right at desktop width. Smaller screens stack content. Calendar month navigation, Today, timezone/date labels, event rendering, and automatic refresh are included. No fake schedules were introduced.

Own profile image pages provide preview, upload, replacement, and removal. Private requirement pages expose real view/replacement/removal controls and generated-document downloads. Resident forms now use labelled WTForms fields with field errors, valid household choices, and image previews; elderly birth dates are supported.

Administrator navigation now includes authorized Residents, Blotter, and Documents links. KPI cards use less cramped grids. Sidebar scrolling, focus outlines, icon fallbacks/aliases, and mobile header spacing were improved. Redundant resident top navigation was removed while preserving sidebar features.

The chatbot shows a configurable barangay identity instead of provider branding. Unsupported disabled Hold/Transfer/SMS/QR controls were removed from the relevant queue/dashboard UI; functioning queue actions remain. Incident map printing uses the browser print flow. Recent audit rows come from the database. False two-factor login wording and invented office-hour/contact placeholders were replaced with accurate sign-in/unavailable states.

## F. Completed and Verified Features

The automated tests verify Purok canonical duplicate rejection and database conflicts, administrator edit/archive, staff view/mutation denial, malformed-image rejection, valid image upload/replace/remove, private image ownership, requirement locks, notification ownership/read counts, calendar publication/timezone/month bounds, exact blotter association, separate unrelated/uncertain complaints, FIFO display, audit creation, session expiry, and all three shared dashboard layouts.

Additional end-to-end checks verify user creation/self-protection; CSRF rejection; audit rollback; resident creation/edit with household linkage; and document ID upload → review → processing → approval → generated document → private download → release, with resident notifications. Local FAQ chatbot replies and configured branding were tested. The tested full document chain does not establish the legal adequacy of its certificate wording or signatures.

## G. Unfinished Items and Required Verification

1. **Production database and concurrent workload.** The configured Supabase PostgreSQL schema was subsequently repaired and upgraded, with existing row counts preserved. Concurrency, full production lifecycle, and backup restoration remain unverified. Remaining work: run upgrade/backup restoration against a staging clone, exercise simultaneous duplicate submissions and writers, measure query latency, and check all existing data against new validation. Recommended implementation: isolated staging tests using production-like data and explicit database backups.
2. **SMTP, email verification delivery, and external AI/maps.** Credentials and operational services were not validated. SMTP success/failure logic is tested with mocks; actual inbox delivery, provider availability, map tiles/geocoding, and external AI responses remain unverified. Configure private credentials and test from the deployment host. An outbox/job service should make email delivery retryable and avoid sending credentials before the database transaction is durably committed.
3. **Complete regression coverage of every module/action.** The suite covers the new and changed critical workflows and static portal route rendering. It does not establish every financial, welfare, DRRM, report-export, backup/restore, correction, hearing/settlement, and legacy editing path end-to-end. Remaining work: role-specific operational fixtures and lifecycle tests, including illegal status transitions and rollback behavior. Rendering a page is not proof its mutations work.
4. **Complete architectural decomposition and dynamic permissions.** Large legacy blueprints still exist. The new matrix secures shared APIs and supplements existing role checks, but editable database Permission records are not a complete dynamic authorization system. Remaining work: move additional mutations into services and reconcile the role/permission administration UI with a documented authoritative policy, without widening resident access.
5. **Calendar event administration.** The shared calendar reads real published Event records. A new complete event-management workflow was not implemented or tested here. Remaining work: authorized create/edit/publish/archive controls and event lifecycle tests if this is required operationally.
6. **Authoritative contact/privacy/legal configuration.** No verified hotline, hall address, office hours, DPO contact, official FOI form, or approved certificate text was supplied. Pages show unavailable states. Remaining work: enter approved values, centralize public settings, and review privacy/retention wording and certificate signatory processes with the barangay.
7. **Historical blotter association and ID lifecycle.** Historical fingerprints were intentionally not inferred or merged. Existing legacy uploads may include older formats; new uploads are JPEG/PNG. Remaining work: reviewed legacy matching/cleanup tools, secure storage permissions, retention rules, malware scanning if required, and verification of existing files. Avoid automated fuzzy merges of case history.
8. **Mobile interactions and accessibility breadth.** Desktop layout and mobile stacking were visually inspected; desktop notification panel behavior was checked. Browser automation did not reliably verify the mobile drawer interaction. Remaining work: manual drawer/keyboard/focus checks, all role forms/tables, tablet widths, screen readers, and long real record values. No blanket claim of console-error-free behavior is made.
9. **Ancillary artifacts and unsafe old utilities.** Older nested project copies, obsolete setup/reset utilities, and source SQL snapshots were not refactored into this clean release. They remain in the original ZIP. Use the included revised runtime/migrations and provisioning tools. Do not run arbitrary old reset scripts against a live database.

## H. Testing Results

Testing used Python 3.14 with Flask, SQLAlchemy, Pillow, and pytest on Windows. The release targets Python 3.12+; Python 3.12 still needs deployment verification. Subsequent live Supabase migration/startup checks passed; the full application suite used synthetic SQLite fixtures.

The final release test command is:

```powershell
python -m pytest tests -q -p no:cacheprovider -p no:tmpdir
```

Final clean-release result: **90 passed, 0 failed**, in 67.49 seconds, including the rendered-form CSRF assertions after the final delete-form repair.

Route inventory: 141 application routes; the delivered ROUTE_INVENTORY.json records the current routes. A test iterates all static administrator/official/resident/workspace GET routes and asserts no 5xx responses. The inventory includes 55 such GET routes. This does not imply each route returns 200 without required inputs.

Additional checks: Python compilation; full fresh SQLite migration chain; latest downgrade/re-upgrade; duplicate legacy Purok refusal without deletion; canonical backfill; household-reference preservation and foreign_key_check; desktop/mobile screenshot inspection. Synthetic QA databases/files remained separate from production. The original archive was left untouched.

Earlier failing assertions were corrected to reflect secure random credentials, actual approval routes, required consent, and mocked email behavior. A test mock initially patched the global secrets module and collided with session tokens; its scope was narrowed to the administrator module. Final results, rather than intermediate failures, determine the shipped status.

## I. Security Review

Improved areas include private decoded-image storage, ownership checks, CSRF (including the repaired official-account delete form), role guards, session expiry, random temporary credentials, real email verification, production secret checks, controlled development seeding, safe sorting/numeric validation, enabled SQLite foreign keys, and atomic audit records.

Credential-like values were found in the supplied environment example and removed from the revised one. If those values were ever real, rotate the affected credentials before deployment. No real credentials, databases, resident uploads, or original runtime logs are shipped in the clean ZIP.

Remaining concerns include deployment TLS/storage ACLs, live SMTP/integration verification, production concurrency, manual SQL normalization bypasses, unreviewed legacy actions, file retention, immutable/auditable backup storage, and legally approved document wording. Generic audit coverage does not itself prove every special workflow action has the required operational audit detail. This was a targeted code/security review, not a penetration test or compliance certification.

## J. Useful Future Improvements

Prioritize a PostgreSQL staging gate and full lifecycle tests for financial, welfare, DRRM, and case operations. Add a durable email outbox and background file cleanup. Consolidate public barangay settings and operational event administration. Then split remaining large mutation controllers into transaction-owned services, reconcile dynamic permission management, and add performance measurements before introducing caches or additional frontend frameworks.

Keep a documented migration/backup restoration procedure and avoid automatic historical case merging. A release is ready for production only after the remaining operational gates are actually verified.

## Extended resident registration (October 9, 2026)

The registration wizard now saves birthplace, optional religion/education/household relationship, house/lot/block and street/landmark, residency duration, self-declared special categories, and emergency contact. It accepts an optional profile photo, required proof of residency, and optional PhilSys card image. Images must be valid JPEG/PNG, at most 5 MB and 20 megapixels each. The entire multipart request is capped at 16 MB by MAX_REQUEST_BYTES. Verification images are stored outside public assets and viewable only by the resident owner or authorized officials/administrators, with view audits.

New registrations require birthplace, Purok, address components, residency duration, and proof of residency. Religion, education, household relationship, categories, emergency contact, profile photo and PhilSys card are optional. An emergency contact number and name must be supplied together when used. Special categories are declarations requiring staff review; they do not automatically approve benefits. Existing residents remain valid with null values for the new fields.

Migration b8d31f04c720 follows a7c20d9e6410 and adds 13 nullable resident columns. Upgrade with `python -m flask --app 'app:create_app' db upgrade heads`. Downgrade removes the added registration values; back up before using it. The configured Supabase database was upgraded to b8d31f04c720 and passed startup schema validation; existing resident, user and household row counts were preserved. No live registration or email was submitted for verification.

Verification: 90 automated tests passed (67.49 seconds); all 17 new registration tests passed again after the final form layout changes. Fresh full migration and populated downgrade/re-upgrade passed on disposable SQLite databases. Tests cover persistence, required fields, invalid values, decoded image validation, cleanup on rejection, private access, and optional-field rendering. Browser inspection confirmed the new identity fields; complete interactive/mobile registration remains a manual deployment check.
