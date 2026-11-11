# Revised Barangay Management System

This release contains the active Flask application from the supplied archive, its migrations, and automated tests. The original archive and older nested project copies have not been modified. See SYSTEM_AUDIT_REPORT.md for verified changes and remaining limitations.

## Civic Emerald interface and profiles

All five application layouts now share the Civic Emerald component layer, local Bootstrap 5.3.3, responsive navigation and a persistent light/dark preference. My profile & account includes role-aware information tabs, permitted contact editing, actual completeness and private profile-photo upload, preview, crop, replacement and removal. Registration and authorized resident records share the same stored photos. Profile photos accept JPEG, PNG and WebP; government IDs and evidence remain JPEG/PNG. See [FRONTEND_UPGRADE_REPORT.md](FRONTEND_UPGRADE_REPORT.md) for the audit, page inventory, permissions, verification results and exact Windows run instructions. This frontend/profile upgrade needs no additional database migration.

## Original document workflow

The resident request page now uses a single document selector and automatic resident-record summary. The initial ID/residency/cedula/purpose block was removed at the user's request. Intake creates a pending request; incomplete certificate information is confirmed by staff before issuance; request approval and in-person payment are separate steps. This change requires no database migration.

The seven supplied official certificate/application designs now support authenticated resident autofill, verified approval, private PDF export, printing/release history, atomic numbering, and token-based public verification. See [DOCUMENT_WORKFLOW_SETUP.md](DOCUMENT_WORKFLOW_SETUP.md) for administrator setup, role flows, renderer installation, and migration details. Supabase PostgreSQL remains the database.

## Local setup

Use Python 3.12 or newer. From this folder:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt -r requirements-dev.txt
Copy-Item .env.example .env
python -m flask --app 'app:create_app' db upgrade heads
python create_admin_account.py
python run.py
```

Enter a private random SECRET_KEY in .env. Leave DATABASE_URL blank for local SQLite. The interactive administrator command requires an existing migrated schema; it never silently creates one. Do not use development default accounts for a deployment. The default account seeder is restricted to development/testing.

## Existing database migration

Back up the database and private storage before migrating. Stop application writers. The Purok migration is a7c20d9e6410; the latest registration migration is b8d31f04c720. It refuses ambiguous legacy Purok duplicates before altering the schema and lists conflicting database IDs. Review household/resident references before manually consolidating any duplicate. Never delete a geographic record simply to make migration pass.

Historical blotter cases are preserved and do not receive new matching fingerprints automatically. New exact duplicate submissions use the original case; different or uncertain incidents remain separate.

SQLite migrations temporarily disable foreign keys on the migration connection to recreate tables, then check relationships and restore enforcement. Normal application connections enforce foreign keys.

## Configuration

Configure SMTP_HOST, SMTP_USERNAME, SMTP_PASSWORD, SMTP_FROM_EMAIL, and HTTPS APP_BASE_URL before resident email verification or credential delivery. Resident approval requires a verified email by default. Keep that setting enabled.

Configure SYSTEM_TIMEZONE, BARANGAY_NAME, and CHATBOT_NAME as appropriate. Image uploads accept JPEG/PNG up to 5 MB and 20 megapixels. Government IDs are stored privately and served through authenticated ownership/staff checks. Scans of other supporting requirements currently use the same JPEG/PNG policy.

The chatbot has a local FAQ fallback. An external AI response requires a configured GEMINI_API_KEY and a valid provider model. Live AI and external map services were not validated in this release. Barangay contact, office-hour, and DPO details still need authoritative values; public pages show clear unavailable states rather than invented information.

## Tests

```powershell
python -m pytest tests -q -p no:cacheprovider -p no:tmpdir
```

Run `python tools/verify_migrations.py` to reproduce the migration checks on a new disposable SQLite database; it never selects the configured production database.

Tests create only synthetic local records. Test storage lives in .test-storage and may be removed after testing. The tests do not prove every module's production workflow or live integrations.

## Deployment

Set FLASK_CONFIG=production, a random SECRET_KEY of at least 32 characters, DATABASE_URL, private persistent STORAGE_ROOT/LOG_FILE, HTTPS APP_BASE_URL, and DOCUMENT_VERIFICATION_BASE_URL. Configure SMTP privately. Apply migrations and provision a real administrator before starting the service.

On Linux:

```sh
gunicorn -c gunicorn.conf.py wsgi:app
```

The Docker entry point also uses wsgi:app. Mount persistent storage outside the release directory, use TLS through a reverse proxy, and back up both database and files. The source contains no production credentials or resident uploads. Do not deploy the Flask development server. PostgreSQL migration, real email delivery, legal certificate wording/signatures, live integrations, backup restoration, and concurrent workload checks remain deployment gates.

Any credentials previously included in the supplied archive's environment examples should be rotated before reuse.

## Extended resident registration (October 9, 2026)

The registration wizard now saves birthplace, optional religion/education/household relationship, house/lot/block and street/landmark, residency duration, self-declared special categories, and emergency contact. It accepts an optional profile photo, required proof of residency, and optional PhilSys card image. Images must be valid JPEG/PNG, at most 5 MB and 20 megapixels each. The entire multipart request is capped at 16 MB by MAX_REQUEST_BYTES. Verification images are stored outside public assets and viewable only by the resident owner or authorized officials/administrators, with view audits.

New registrations require birthplace, Purok, address components, residency duration, and proof of residency. Religion, education, household relationship, categories, emergency contact, profile photo and PhilSys card are optional. An emergency contact number and name must be supplied together when used. Special categories are declarations requiring staff review; they do not automatically approve benefits. Existing residents remain valid with null values for the new fields.

Migration b8d31f04c720 follows a7c20d9e6410 and adds 13 nullable resident columns. Upgrade with `python -m flask --app 'app:create_app' db upgrade heads`. Downgrade removes the added registration values; back up before using it. The configured Supabase database was upgraded to b8d31f04c720 and passed startup schema validation; existing resident, user and household row counts were preserved. No live registration or email was submitted for verification.

Verification: 90 automated tests passed (67.49 seconds); all 17 new registration tests passed again after the final form layout changes. Fresh full migration and populated downgrade/re-upgrade passed on disposable SQLite databases. Tests cover persistence, required fields, invalid values, decoded image validation, cleanup on rejection, private access, and optional-field rendering. Browser inspection confirmed the new identity fields; complete interactive/mobile registration remains a manual deployment check.

Barangay Clearance upload checklist update (October 9, 2026):
Removed the Community Tax Certificate (cedula) and 2 pcs. 1x1 recent ID photo upload cards from new and existing clearance requests, resident and staff screens, verification and approval checks. Historical requirement rows and stored files are preserved. Other document checklists and valid ID checks remain active. No database migration is needed.
30 focused checklist, intake and original-document workflow tests passed in 39.27 seconds. Browser clearance submission confirmed only the active valid-ID card; no horizontal overflow at 1440px.

Document review, approval and in-person payment update (October 9, 2026):
Request evidence displays an inline private image and a full-size View link. If a request has no separate ID upload, it uses that resident's registration PhilSys ID; a request-specific upload takes priority. Registration proof can also satisfy the matching residency checklist. File existence, safe filenames, ownership, staff roles and private/no-store responses are enforced.
Staff may confirm ID, identity and document eligibility and approve a pending or reviewed request in one form, without collecting payment or completing certificate-specific fields first. Approval saves review and audit history and does not issue the certificate. At the barangay, staff complete and confirm the real certificate information, record any actual cash payment and official receipt, then generate/print/release the certificate. No online payment is involved. Existing final certificate completeness, eligibility, signatory, fee, numbering and payment checks remain. Recheck approval is available if records/evidence/fee change before issuance. No database migration is required.
34 focused review, checklist, intake and original certificate tests passed in 45.37 seconds. The final fee/reverification refinements passed the four review tests again in 5.62 seconds. Browser approval succeeded before payment; registration ID loaded; responsive checks at 320, 375, 768, 1024 and 1440px showed no overflow. Preview screenshot uses synthetic test data only.

Private image 404 fix (October 9, 2026):
Relative STORAGE_ROOT and LOG_FILE paths now resolve against the project directory, independent of the process working folder. Existing request and registration images are read from the configured private storage root first, then the two supported historical project/parent instance layouts. Filenames, extensions, contained paths, ownership, staff authorization and no-store responses remain enforced. Existing files and database records are not moved or deleted. The latest live request ID file was found in the parent instance layout and is now resolved from the project instance configuration as well. An older request references a file absent from both supported directories; missing files still return 404 rather than displaying unrelated images.
The full-size image route was verified in the browser with a synthetic 800x480 PNG: fully decoded, no 404. The updated live server runs on port 5001. The separate older port-5000 process could not be stopped because Windows returned Access denied; it must be restarted by its owner to load the new code.

Direct printing update (October 9, 2026):
Removed the approved-request Prepare certificate input form. The Print document POST action creates the original printable certificate from saved resident/request data and opens its print preview automatically. Missing supplemental values remain blank instead of requiring another form or inventing data. Printing still requires an approved, unchanged review, available verified evidence, active signatory and confirmed fee/actual in-person receipt where applicable. Repeated print actions reuse the issued certificate/control number. The normal detailed-generation API retains its existing completeness checks. Physical printing is confirmed separately for release history.
Fixed certificate preview embedding: only the authenticated original certificate endpoint allows same-origin framing, while other pages retain frame-ancestors none and all other security headers remain. Browser test confirmed the original clearance visibly renders in the frame after Print document. 24 review/original-certificate tests passed in 35.53 seconds. All browser examples used synthetic data; no real request was issued during verification.

Pending-fee printing fix (October 9, 2026):
Direct Print document no longer requires fee configuration or payment first. Approved and verified requests may be printed while the fee or cash payment is pending. The paper uses actual recorded payment/receipt data only; missing amount, receipt number and receipt date remain blank. Unknown fees are not treated as a confirmed free service. Staff may record in-person cash receipts after printing. Actual fee confirmation and payment settlement occur before final release. Existing strict generation endpoints retain their prior checks.
26 document-review and original-certificate tests passed in 38.00 seconds. Browser check reproduced an approved request with no FeeConfiguration and no payment, clicked Print document, and successfully displayed the original certificate without a fee error; payment fields were blank. No real certificates were generated during testing.


## Attendance and incident operations
See [ARDUINO_INCIDENT_SETUP.md](ARDUINO_INCIDENT_SETUP.md) for personnel/RFID enrollment, development mode without a reader, wiring, bridge commands, complaints, verified hotline management, referrals and production setup. Supabase PostgreSQL is retained. New additive migration head: `d7a91e8b420c`.
