# Official document workflow — Supabase PostgreSQL

This feature extends the existing app. The database remains Supabase PostgreSQL, as requested. Do not create a replacement database or reset Alembic history.

## Installation and migration

From PowerShell, enter the folder containing `run.py`, `app`, and `migrations`:

```powershell
cd C:\Users\SERIES\Desktop\DAD\barangay-system
python -m pip install -r requirements.txt
python -m flask --app "app:create_app" db upgrade heads
python run.py
```

The new additive revision is `c9e42a15d831`, following `b8d31f04c720`. It adds request verification and approval metadata, additional request data, authorized signatories, atomic control-number sequences, immutable issuance snapshots, verification tokens, and PDF/revocation metadata. Existing residents, accounts, uploads, payments, requests, and previously generated artifacts are retained. Never use `flask db stamp` to conceal a missing migration.

Keep the existing `.env`, including the Supabase `DATABASE_URL`, `SECRET_KEY`, and private `STORAGE_ROOT`. This release ZIP contains `.env.example`, not your credentials or private files. Start only one server on the chosen port; an old process continues to run its previously imported Python code until restarted.

## Required administrator setup

1. Open **Document Types → Original templates and approved signatories**, or `/official/document-settings` with an administrator account.
2. Enter the actual approved issuing official's full name, designation, and effective dates. The reference's sample signature name is not automatically authorized. Deactivate an expired or superseded signatory here.
3. Open **Fees** and enter the actual effective fee schedule for each document, including an explicit zero-fee schedule where appropriate. First Time Jobseeker certification always costs zero, regardless of a general fee setting. An unconfirmed default zero fee does not authorize issuance of other documents.
4. Check each active document's mapping to its original SCN template. A type already used in requests cannot be reassigned to a different certificate.
5. Set actual office contacts in `.env` if they should appear in the original footer:

```dotenv
BARANGAY_CONTACT_PHONE=
BARANGAY_CONTACT_EMAIL=
DOCUMENT_VERIFICATION_BASE_URL=https://your-actual-portal-domain
```

Use the actual reachable portal origin for `DOCUMENT_VERIFICATION_BASE_URL`. New QR codes point to `/verify/<opaque-token>`. Do not include `/verify` itself in the configured base URL. For local testing, use the same origin and port as the running app. The reference's `0900-000-0000` sample phone is not printed in issued certificates.

## Resident workflow

Open **Document Requests → Request a document**. Selecting a document loads its required fields. Identity and address come from the authenticated resident's database record and are displayed for review. Only missing values and document-specific information are requested. Existing registered identity corrections use the existing profile correction process. Approximate residency ranges are not silently converted into an exact number of years.

Submit the request, then upload the required evidence as JPEG/PNG images. Mandatory checklists follow the supplied forms; renewal applications require the previous business permit, and unverified clearance applicants require residency evidence. Staff may request additional evidence, including conditional documents in the original forms. Follow the **Needs Correction → Correct information** link to resubmit corrections. Replacing evidence or correcting information invalidates its earlier verification.

Residents can track their own requests and view their own uploaded evidence. Official certificate preview, PDF, printing, approval, release, and revocation endpoints require authorized staff or administrator roles. Official certificate download remains a registered resident route but refuses printable official output; residents collect the signed and sealed certificate from the barangay.

## Staff workflow

1. Open **Document Requests**. Search by resident name/request number and filter by type, status, and submission dates. Counts show pending, approved, rejected, ready for printing, and released requests.
2. Open a request and select **Under Review**. Review the resident data, document-specific details, supporting records, and uploaded pictures. **View populated application** uses the corresponding original application layout.
3. Confirm identity, every mandatory uploaded requirement, and each document-specific eligibility check. Enter the verification findings and select an active authorized signatory. Save verification. Uploading an image alone never certifies eligibility.
4. Record an actual official receipt/payment where a fee applies. Do not enter fabricated receipt numbers.
5. Approve, reject with a reason, or request corrections with instructions. Approval generates the correct original certificate and advances to **Ready for Printing** in the same transaction. If verified identity, evidence, purpose, signatory, or fees changed, fresh verification is required.
6. Use **Preview Certificate**, **Generate PDF**, or **Print Certificate**. The print page contains the original A4 certificate only; navigation and controls are excluded from print output. Print on A4 at 100% scale with background graphics enabled and browser headers/footers disabled.
7. Select **Confirm printed** after printing. Opening or cancelling a browser print dialog does not claim that a physical copy was printed. Apply the handwritten signature and official dry seal in the preserved areas, then **Release document**. Reprinting a released certificate records a reprint event without undoing release.

Statuses are Pending, Under Review, Needs Correction, Approved, Rejected, Ready for Printing, Printed, and Released. Legacy Processing and Ready for Release records remain recognized for compatibility. Every transition, verification, PDF export, print confirmation, receipt, release, and revocation is recorded with its actor and timestamp. An administrator can revoke a generated certificate with a reason; revoked certificates cannot be printed or released again.

## Original designs and validity

All fourteen Jinja layouts were derived from the supplied HTML, with the supplied PDF used for visual comparison. Logos, watermark artwork, borders, colors, wording, A4 dimensions, applicant photo/thumbmark boxes, handwritten signature areas, and QR location are retained. The original Liberation font families are included to prevent platform font substitution. Header/field/requirement containers use equivalent flow rules that render consistently in the browser and PDF renderer.

The seven certificate mappings are SCN-IND, SCN-RSD, SCN-BIZ, SCN-CLR, SCN-GMC, SCN-SPE, and SCN-FTJ. Indigency, Residency, Clearance, and Good Moral use six calendar months. Business permits expire on December 31 of the issuance year. Solo Parent and First Time Jobseeker certificates use one calendar year, including leap-day handling. These periods follow the provided templates; the legacy `validity_days` field does not override their wording.

Issuance uses the approved date in Asia/Manila. Control numbers use `SCN-TYPE-YEAR-000001`, with an atomic PostgreSQL upsert and unique constraints. Approval/issuance and sequence allocation share one transaction. A resident row lock also serializes first-time benefit checks. A first-time jobseeker grant cannot be issued a second time, including through another type mapped to SCN-FTJ.

Personal data and the approved signatory are frozen in the issuance snapshot and private HTML artifact. Later profile or signatory changes do not rewrite issued certificates. Public QR verification discloses only document authenticity facts, distinguishes Valid, Expired, Revoked, Not issued, and Not found, and does not expose resident names, addresses, birth dates, uploaded images, or contact information. Prepared/printed certificates become publicly valid only after official release. Existing document-number verification remains available for legacy issued documents.

## PDF runtime

Windows includes the official standalone WeasyPrint 70.0 renderer under `tools/pdf-runtime/onedir/weasyprint`. Its download SHA-256 was checked against the official GitHub release asset. It renders the same original HTML, embedded artwork, and supplied font files to a single A4 PDF. Exports are stored privately and reused. An optional `DOCUMENT_PDF_RENDERER` path can select another installation; `DOCUMENT_PDF_BROWSER` selects a Chrome/Chromium fallback.

On Linux, install WeasyPrint and its native Pango/font dependencies following the [official installation instructions](https://doc.courtbouillon.org/weasyprint/stable/first_steps.html). The Windows executable is not selected on Linux. Configure `DOCUMENT_PDF_RENDERER` to the installed `weasyprint` executable if it is not on PATH.

The reference originals are retained under `reference_documents`. Editable Jinja bindings are under `app/templates/documents/original`. The font license is under `app/static/fonts/document-original/LICENSE.txt`; renderer provenance is under `tools/pdf-runtime/UPSTREAM.txt`. No digital signature or official dry seal is applied automatically.

## Verification and tests

```powershell
python -m pip install pytest
python -m pytest -q -p no:cacheprovider -p no:tmpdir
python tools/verify_migrations.py
```

The document tests cover all seven original certificates/applications, authenticated resident binding, verification gates, pending/rejected refusal, corrections, ownership and staff/admin permissions, calendar expiry, fee schedules/receipts/FTJ exemption, first-time benefit reuse, immutable issued artifacts, changed-data re-verification, transaction rollback, concurrent atomic numbering, PDF output, and public QR states.

Visual QA rendered all fourteen original layouts and a long-name/long-address certificate. Each had one A4 page, with the original artwork, body text, QR/signature areas, and complete application footer visible. The concurrent numbering regression uses a disposable SQLite database; PostgreSQL uses the corresponding atomic `ON CONFLICT ... DO UPDATE ... RETURNING` operation. Migration QA upgrades a fresh database and verifies populated downgrade/re-upgrade and foreign-key preservation. Production records and credentials are never used as test fixtures.

The ZIP provides complete files at their project-relative paths. `FILE_MANIFEST.json` lists file hashes, `ROUTE_INVENTORY.json` lists routes, and `TEST_RESULTS.txt` records completed checks. The module code is in `app/documents/engine.py`, `workflow.py`, `routes.py`, and `verification.py`; the new model fields are in `app/models/services.py`; the migration is in `migrations/versions/c9e42a15d831_official_templates.py`. Existing resident/staff routes and pages were integrated in place.

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
