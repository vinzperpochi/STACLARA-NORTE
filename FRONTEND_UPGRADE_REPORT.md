# Civic Emerald frontend and profile upgrade

### Subsequent document request UI update

The initial request page now has a single document selector, live fee summary, registered resident record and submit/back actions. The duplicate selector, ID/residency/cedula inputs, purpose textarea and Load document fields instruction were removed at the user's request. Initial intake creates a genuine pending request with empty supplementary details; no certificate data is fabricated. Existing evidence checks, correction workflow, verification and approval gates remain in force. Nine new intake regression cases and eighteen existing original-document cases passed together: **27 passed in 36.68 seconds**. Browser checks verified fee switching, a synthetic pending request submission and no horizontal overflow at five target widths. The earlier full-suite results below apply to the preceding frontend release; the later intake change used these focused tests. No schema change is required.

Implemented October 9, 2026 in the existing Flask application. Supabase PostgreSQL remains the configured live database. The working source is `outputs/barangay-system`; the installed project is `C:\Users\SERIES\Desktop\DAD\barangay-system`. This report distinguishes shared component upgrades from individually rebuilt pages and browser verification from automated backend tests.

## Audit and inventory

The baseline contains 130 HTML templates, 160 routes and 34 CSS/JavaScript assets. The final application contains 134 HTML templates, 163 routes and 37 CSS/JavaScript assets, plus locally bundled Bootstrap 5.3.3. `FRONTEND_INVENTORY_BASELINE.json` records the initial template/asset/route inventory and findings. `FRONTEND_INVENTORY.json` records the final inventory, baseline findings and their implementation. `ROUTE_INVENTORY.json` lists final endpoints and methods.

The actual security roles are System Administrator, Barangay Official and Resident. Officials and staff share the existing official workspace; no extra roles or accounts were invented. Role permissions remain server-enforced.

The audit found conflicting final styles across layouts, a resident layout missing Bootstrap, an image-only profile page without information tabs, initials displayed despite stored photos, photo references that could diverge between linked users and residents, missing compact navigation/theme preferences, and a need to isolate official print layouts. During verification, fixes also addressed the profile-preview URL policy, role layout title context, mobile login tabs and hints, staff file-input width, tablet registry filters, and an unused terms template referencing an undefined datetime filter.

## Unified design system

`app/static/css/civic-premium.css` is the final shared component layer in all five root layouts: public/base, authentication, resident, official/staff and administrator. Existing utility classes remain for compatibility; the new layer owns semantic colors, controls, typography, cards, tables, navigation, dialogs and responsive behavior. Bootstrap CSS and its JavaScript bundle are local assets with their license.

Brand tokens are forest `#073E14`, emerald `#0A5C1E`, primary `#12902B`, bright `#22B33A`, lime `#4CD62B`, gold `#FFD328`, warning `#FDF4D8`, mint `#E7F8E9`, page `#FAFDF9`, card white, ink `#11291A`, muted `#5F7265`, border `#E2EDE3` and error `#D93025`. Locally bundled Inter is used consistently. Dark mode changes semantic backgrounds and readable text while retaining the emerald/gold identity. The preference persists on the device.

Rounded emerald navigation has gold active items, real identity/photo blocks, expandable groups, desktop compact mode and existing permission-filtered links. Mobile uses the existing drawer with added focus handling, keyboard trapping and Escape support. Shared cards, buttons, validation, pagination, badges, modals, notifications and loading indicators use the same style. Tables retain genuine columns in labelled, keyboard-focusable horizontal scroll regions. Motion respects the reduced-motion preference.

## Pages and modules

Individually rebuilt or integrated content includes the common role-aware profile, all three dashboard greetings and photo/completeness summaries, the resident document catalog with effective configured fees and request links, registration photo selection/removal, staff resident forms, resident registry photo rows, household member cards, administrator users and official account directory photos, and login welcome content.

Secondary pages inherit the component upgrade through their existing root layout: residents and details; households and members; Puroks; account approvals; correction requests; document request lists/details/forms/settings; business clearances; collections; blotter and maps; health/welfare/DRRM; queue; analytics and report exports; audit logs; roles/permissions; system settings; notifications/messaging; help/privacy; and authentication/recovery/change-password. Existing filters, actions and routes remain attached to their backend handlers. No fake dashboard figures, chart datasets or export controls were introduced.

The fourteen original A4 front/back certificate/application templates deliberately do not load the global interface stylesheet. Their official content, print dimensions, PDF renderer, numbering, approval and verification workflow remain separate.

## Bootstrap 5 profiles and allowed editing

`app/templates/profile_management.html` supplies Bootstrap tabs and responsive two-column fields, becoming one column on mobile. Personal information, contact details and account security apply to all accounts. Address and household tabs appear for linked residents; official details appear for linked appointments. Values, ages, household membership, status, registration date and last login come from stored records. Empty values are clearly marked instead of invented.

Edit/cancel mode, inline validation and unsaved-change warnings cover permitted contact updates. Residents can update their own emergency contact name, relationship and number. Officials can update their own official contact number. Registered identity, email, residential address, household membership, roles and appointment details retain the existing correction/administrative process. Administrators without an associated resident or official record receive their real account details rather than fabricated personal data. Account security links to the existing change-password and privacy workflows.

Completeness is calculated from saved fields, not a fixed progress bar. Resident criteria: full name, birth date, sex, civil status, nationality, address, contact number, email and profile photo. Official criteria: full name, position, contact number, email and photo. Unlinked account criteria: username, email and photo. Optional educational/religious/employment data is not required to achieve completeness.

## Profile picture implementation and registration

The authenticated photo editor supports file selection, drag/drop, immediate preview, optional square crop, zoom and horizontal/vertical repositioning, save, cancel, replacement and confirmed removal. The preview uses a FileReader data URL compatible with the existing image security policy. The server independently validates and applies the crop; cancelling does not save a picture.

Profile uploads accept JPEG, PNG and WebP, up to 5 MB and 20 megapixels. Pillow checks actual decoded format, normalizes EXIF orientation, validates finite crop values and bounds, strips metadata, resizes to at most 1600×1600 and re-encodes the image under a generated filename. SVG, malformed, forged and oversized uploads are rejected. Registration evidence and government IDs retain their narrower JPEG/PNG policy.

Files live in persistent private `STORAGE_ROOT/profile_photos`, outside static assets. The existing user/resident filename columns are synchronized after profile and staff replacements. Old files are removed after a successful database commit. Headers, dashboard heroes, profile cards, household members and authorized directories serve the same persisted picture. Initials provide the no-photo fallback. Responses prohibit caching of private photos.

Registration uses the same secure image helper, creates linked user/resident photo references, supports optional selection removal and retains server validation and transaction rollback. Staff-created and edited resident images use the same format policy and update linked account references.

## Backend and database

Existing `GET/POST /workspace/profile` and `GET /workspace/profile-photo` now serve the tabbed profile and photo workflow. Added endpoints:

- `POST /workspace/profile/details`: validates account-owned permitted fields, rejects protected/extra submitted fields, saves contact details and creates an audit entry.
- `GET /workspace/residents/<id>/photo`: restricted to resident management permission, the owner or a member of the same non-null household.
- `GET /workspace/users/<id>/photo`: restricted to account-directory permission or the owner.

Existing session checks, CSRF enforcement and RBAC apply. The target account is derived from the authenticated session; callers cannot supply a different account ID for profile changes. Photo filenames pass the existing private-path guard.

This upgrade changes no database models and requires no new migration. The previously applied Supabase migration head remains `c9e42a15d831`. Existing migrations stay in the release for fresh installations. Do not recreate tables or stamp an unknown revision to apply this frontend update.

## Verification results

The full regression suite passed **139 tests in 129.18 seconds**. It covers registration/activation, invalid and duplicate records, private uploads, sessions, role restrictions, safe contact updates, image cropping and WebP persistence, CSRF, reports, original certificate autofill/approval/printing/PDF/status workflow and import/startup regressions. Pytest emitted one Windows cache-write warning; tests themselves passed. After final template refinements, **40 targeted tests passed in 36.42 seconds** with the cache provider disabled.

All **134 templates compiled**. **69 authenticated static GET checks passed**, including expected permission denials and no-photo responses; report routes were tested with valid report parameters. Evidence is in `FRONTEND_ROUTE_CHECKS.json`. JavaScript files passed Node syntax checks.

Browser QA used synthetic records and private temporary storage, not production residents. **100 page/viewport combinations** passed document-overflow checks at 320, 375, 768, 1024 and 1440px. The matrix covers login, registration, recovery, all three role profiles and dashboards, resident documents/household, staff residents/add-resident/document requests/reports, administrator users/official accounts/reports/settings, and change password. See `FRONTEND_RESPONSIVE_CHECKS.json`. Tables scroll within their own container where needed.

Manual browser checks covered real photo selection/preview/crop/save/refresh, contact persistence, role-aware profile data, fallback avatars, tab switching, theme switching, compact navigation, group expansion, mobile drawer focus/Escape and photo-dialog cancellation. A fresh profile page emitted no browser error logs. The separate QA server runs sequentially because its test fixture uses one in-memory SQLite connection; this does not change the production application or Supabase configuration.

## Remaining limits

This is a shared-component upgrade across the application with individually rebuilt key pages, not a replacement of every existing template. All templates compile and the static routes were checked; every populated dynamic detail page and every module action was not manually exercised at every viewport. Automated workflow tests provide additional coverage. Cross-browser Safari/Firefox testing, a full screen-reader/WCAG conformance audit, sustained concurrent production load, real SMTP delivery and live external map/AI integrations were not performed. Existing authoritative office/contact/signatory settings must still come from the barangay. Missing optional settings are not filled with invented details. Production records were not modified for UI QA.

## Exact Windows run instructions

The installed Desktop project keeps its existing `.env`, Supabase connection and private instance storage. Open PowerShell in the project root, rather than running individual blueprint files:

```powershell
Set-Location 'C:\Users\SERIES\Desktop\DAD\barangay-system'
$env:STORAGE_ROOT = 'C:\Users\SERIES\Desktop\DAD\instance'
$env:LOG_FILE = 'C:\Users\SERIES\Desktop\DAD\instance\logs\document-server.log'
$env:HOST = '127.0.0.1'
$env:PORT = '5001'
python run.py
```

If the updated server is already listening on 5001, use that instance or stop it before launching another copy. Open `http://127.0.0.1:5001/auth/login`. After login, My Profile opens `/workspace/profile`. Use Change picture to upload/crop/save or remove a picture. Use Contact details → Edit contact details for permitted updates. Existing civil resident records and correction requests remain available.

For a fresh ZIP extraction, create/activate a virtual environment, install `requirements.txt` and `requirements-dev.txt`, copy `.env.example` to `.env`, configure private credentials and persistent storage, and run `python -m flask --app 'app:create_app' db upgrade heads` from the project root before creating a real administrator. Do not replace the live `.env` with the example. The original document renderer/setup instructions remain in `DOCUMENT_WORKFLOW_SETUP.md`.

Run verification from the project root with `python -m pytest tests -q -p no:cacheprovider`. The runnable ZIP excludes credentials, private uploads, test databases, caches and environment folders and includes the interface assets, backend, migrations, tests, original document templates and Windows PDF runtime.

Document review, approval and in-person payment update (October 9, 2026):
Request evidence displays an inline private image and a full-size View link. If a request has no separate ID upload, it uses that resident's registration PhilSys ID; a request-specific upload takes priority. Registration proof can also satisfy the matching residency checklist. File existence, safe filenames, ownership, staff roles and private/no-store responses are enforced.
Staff may confirm ID, identity and document eligibility and approve a pending or reviewed request in one form, without collecting payment or completing certificate-specific fields first. Approval saves review and audit history and does not issue the certificate. At the barangay, staff complete and confirm the real certificate information, record any actual cash payment and official receipt, then generate/print/release the certificate. No online payment is involved. Existing final certificate completeness, eligibility, signatory, fee, numbering and payment checks remain. Recheck approval is available if records/evidence/fee change before issuance. No database migration is required.
34 focused review, checklist, intake and original certificate tests passed in 45.37 seconds. The final fee/reverification refinements passed the four review tests again in 5.62 seconds. Browser approval succeeded before payment; registration ID loaded; responsive checks at 320, 375, 768, 1024 and 1440px showed no overflow. Preview screenshot uses synthetic test data only.

Direct printing update (October 9, 2026):
Removed the approved-request Prepare certificate input form. The Print document POST action creates the original printable certificate from saved resident/request data and opens its print preview automatically. Missing supplemental values remain blank instead of requiring another form or inventing data. Printing still requires an approved, unchanged review, available verified evidence, active signatory and confirmed fee/actual in-person receipt where applicable. Repeated print actions reuse the issued certificate/control number. The normal detailed-generation API retains its existing completeness checks. Physical printing is confirmed separately for release history.
Fixed certificate preview embedding: only the authenticated original certificate endpoint allows same-origin framing, while other pages retain frame-ancestors none and all other security headers remain. Browser test confirmed the original clearance visibly renders in the frame after Print document. 24 review/original-certificate tests passed in 35.53 seconds. All browser examples used synthetic data; no real request was issued during verification.

Pending-fee printing fix (October 9, 2026):
Direct Print document no longer requires fee configuration or payment first. Approved and verified requests may be printed while the fee or cash payment is pending. The paper uses actual recorded payment/receipt data only; missing amount, receipt number and receipt date remain blank. Unknown fees are not treated as a confirmed free service. Staff may record in-person cash receipts after printing. Actual fee confirmation and payment settlement occur before final release. Existing strict generation endpoints retain their prior checks.
26 document-review and original-certificate tests passed in 38.00 seconds. Browser check reproduced an approved request with no FeeConfiguration and no payment, clicked Print document, and successfully displayed the original certificate without a fee error; payment fields were blank. No real certificates were generated during testing.
