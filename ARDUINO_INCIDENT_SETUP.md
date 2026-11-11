# Attendance and incident operations

The existing Supabase PostgreSQL database is retained, as requested. XAMPP/MySQL is not required. Revision `d7a91e8b420c` follows `c9e42a15d831` and adds 22 tables without altering existing tables. Existing document requests, residents, account roles and uploaded files remain in place.

## Windows startup

Run from the project root, never from inside `app`:

```powershell
Set-Location C:\Users\SERIES\Desktop\DAD\barangay-system
python -m pip install -r requirements.txt
python -m flask --app 'app:create_app' db upgrade heads
python run.py
```

Keep the existing `.env` DATABASE_URL and SECRET_KEY. Set `PORT=5001` if using the current desktop preview URL. The standard run.py checks the complete schema before starting. Do not stamp over an unknown Alembic revision or recreate existing tables. Pure-Python pyserial and pypdf are bundled in `vendor/python`; requirements also declares them for a normal virtual environment install.

## Personnel enrollment and permissions

1. Administrator opens **Personnel & RFID**. Enter first/last name, choose the barangay role, set the first work schedule, and use the scan modal to attach the card. Optional details include employee ID (otherwise generated), department, contact details, employment status and photo. One Save commits profile, first schedule and card together. The previous separate Personnel Management creation page redirects here.
2. Select scheduled weekdays and effective date. In the personnel detail page configure grace minutes, absence cutoff, minimum session length, number of sessions, flexible/overnight shifts and optional PIN. End old schedules when adding replacements so historical calculations remain valid.
3. Staff attendance views and exports cover their own profile. Administrators manage all personnel, devices, schedules, leave decisions and audited corrections. Revoking/replacing a card retains earlier logs.
4. UID formats accept 4, 7 or 10 bytes as hexadecimal, with optional spaces/colons. Only a SHA-256 digest and suffix are stored in the web database. RFID UID alone is not strong identity verification; enable device PIN verification where needed.
5. Attendance stores UTC and displays Asia/Manila. Absence is calculated after the configured cutoff, leave and off-duty days are distinguished, and open sessions are excluded from completed hours. Overtime appears only after administrator approval. Corrections require a reason and preserve before/after values.

## Hardware wiring

There is currently no connected RFID reader. Physical scans, firmware compilation on a chosen board, LED and buzzer behavior still need hardware verification. The implementation supports Arduino Uno or ESP32 with an MFRC522 reader and passive buzzer. Install the official Arduino IDE board package and the MFRC522 library through Library Manager, then compile/upload `hardware/arduino_rfid/arduino_rfid.ino` for the selected board.

Uno connections: MFRC522 SDA/SS → D10, RST → D9, MOSI → D11, MISO → D12, SCK → D13, GND → GND, VCC → 3.3V. MFRC522 is a 3.3V device: use suitable level shifting on Uno 5V outputs; never connect its power to 5V. Green LED → D6 through 220–330 ohm resistor, red LED → D5 through a resistor, buzzer signal → D4, all returns → GND. Use an appropriate driver for a buzzer drawing more than the pin rating.

ESP32 connections: SS → GPIO5, RST → GPIO27, MOSI → GPIO23, MISO → GPIO19, SCK → GPIO18, VCC → 3.3V, GND → GND. Green LED → GPIO25 through resistor, red LED → GPIO26 through resistor, buzzer signal → GPIO14. Use a board exposing these pins.

Signal path: RFID card → MFRC522 SPI → Arduino/ESP32 → USB serial (115200 baud) → Python bridge → authenticated Flask API → PostgreSQL. Firmware sends UID JSON over USB; it never contains database credentials or an API secret. Green/buzzer success follows an accepted API response, not merely card detection.

## Device and serial bridge

The current single-reader Wi-Fi demo uses automatic pairing and has no reader setup panel. See **RFID_ATTENDANCE_FLOW.md** and `hardware/esp32_rfid_wifi/esp32_rfid_wifi.ino` for the current flow. The following USB bridge instructions describe the credential-based transport, which requires a reader record and credential provisioned separately by a system administrator.

```powershell
Set-Location C:\Users\SERIES\Desktop\DAD\barangay-system
$env:ATTENDANCE_DEVICE_CREDENTIAL='paste-the-enrolled-id:secret-here'
python hardware/serial_bridge.py --port COM3 --server http://127.0.0.1:5001 --queue C:\Users\SERIES\Desktop\DAD\instance\bridge\attendance-queue.sqlite
# For a PIN-enabled device add --pin-prompt.
```

Find the actual port in Windows Device Manager; COM3 above is an example. Do not run two bridges against the same reader/queue. Protect the queue with Windows file permissions: pending offline UIDs are necessary for retry and must remain private. Successful events are removed from the bridge queue, terminal rejected events retain only the rejection message and event ID. PINs are never persisted; PIN scans require reconnection/rescan instead of offline storage. Serial reconnect retries every three seconds. Events retain their unique ID and scan timestamp; replay cannot create a second attendance entry. The server rejects future/out-of-order/stale events. The default offline limit is seven days.

Remote devices require HTTPS with valid certificates. Local loopback HTTP is permitted for development. API scan and heartbeat use Bearer device credentials; only those device endpoints are CSRF-exempt. Web administration retains session, role and CSRF checks. Device enrollment, rotation, scans, corrections and leave decisions are audited.

## Test without hardware

Use a separate development database with synthetic personnel. Set `ATTENDANCE_DEV_MODE=true` before starting that development server. Enroll a **Development test only** device and its synthetic card/personnel. Then:

```powershell
$env:ATTENDANCE_DEVICE_CREDENTIAL='development-device-id:secret'
python hardware/serial_bridge.py --development --server http://127.0.0.1:5002 --queue instance/bridge/test-queue.sqlite
```

Keyboard mode authenticates the device and rejects credentials for real hardware devices. It is restricted to local servers. Enter the enrolled test UID, observe the actual server decision, wait at least 30 seconds before another scan and respect the schedule minimum session duration. Keep `ATTENDANCE_DEV_MODE=false` on the live database. No synthetic staff attendance is added to the live installation.

## Complaints, emergency contacts and referrals

Residents open **My Complaints / Report Incident**, enter category, incident time, description, location, urgency, optional coordinates and up to four evidence files (JPEG/PNG/PDF, each up to 5 MB; total request limit defaults to 16 MB). The page offers a 911 call link immediately, including before submission. Routing uses versioned category rules and English/Tagalog danger indicators; emergency indicators override ordinary categories. Unknown cases require classification review. Recommendations do not place calls or transmit reports.

The initial 19 categories and agency names are seeded; no invented local hotline numbers are seeded. National 911 fallback source: https://www.pna.gov.ph/articles/1281331 (checked October 9, 2026). Administrators add local numbers using **Hotline Directory**, official HTTPS verification source, verification date, hours and coverage. Unverified, inactive, future-dated or more than 180-day-old numbers are hidden from resident recommendations. Reverify local contacts regularly. Contact coverage must actually include the resident's location; office administrators are responsible for verifying that coverage before publishing the number.

Administrators edit routing agencies, category classification, keyword indicators, priority and active state in **Incident Routing**. New submissions save a rule/version snapshot; changes do not silently rewrite old recommendations. Officials review ordinary incidents; personnel marked Staff see assigned incidents. Sensitive child, medical, domestic violence and other restricted categories are available only to the reporting resident, administrators and explicitly assigned reviewers. Evidence is served through authenticated private endpoints; PDFs download instead of executing inline.

Officials can assign/review, record resident-visible updates, maintain separate private notes, approve printable referrals and record an actual documented handoff. A call link click is never logged as a completed telephone call. Approving/printing a referral never implies external delivery. Emergency response stages require an officer-entered confirmation reference and do not automatically resolve the complaint. The resident timeline and notification bell show actual saved updates and referral contacts. Residents can send follow-ups; closed cases need an authorized reopening. Attendance and incident reports export actual authorized data to CSV, Excel and PDF.

## Backup, retention and production

Before migrations take a Supabase database backup and a private copy of the full STORAGE_ROOT (including generated documents and evidence). Migration is additive and PostgreSQL DDL is transactional. Do not run db.create_all against production as a substitute for migrations. Automated downgrade deliberately refuses to drop operation/history tables; restoration requires the approved database and file backup. Keep database backup credentials outside source control.

`ATTENDANCE_RETENTION_DAYS` and `INCIDENT_RETENTION_DAYS` default to 2555 as administrative review windows, not a legal retention mandate. Configure according to the office's approved records policy and applicable holds. Run `python -m flask --app 'app:create_app' operations-retention-review` for counts eligible for review. It never deletes evidence, personal records or audit history. Authorized disposal/archive is a separate documented office decision. `ATTENDANCE_OFFLINE_WINDOW_DAYS` accepts 1–30 (default 7).

Production requires strong SECRET_KEY, HTTPS, secure session cookies, a production WSGI server, restricted private storage/backup permissions, verified hotline ownership/coverage, assigned sensitive-case reviewers, accurate device/bridge time synchronization and `ATTENDANCE_DEV_MODE=false`. Stop the development Flask server before switching production serving. Keep personnel contact data and evidence private; only authorized summaries are exported.

## Verification

Run `python -m pytest -q -p no:cacheprovider` from the root. New tests cover scans/replays/revocation, overnight shifts/late computation, leave/cutoffs, session totals, role boundaries, CSRF, exports, offline disconnect/reconnect, migration preservation, English/Tagalog routing, verified contact filtering, private evidence and human-confirmed referrals. Browser checks use an isolated synthetic database.

Hardware acceptance: compile for the exact board; enroll a real authorized employee/card; confirm IN and OUT display their actual name/time; check unknown-card red signal, server-accepted green signal, PIN behavior, unplug USB/network and reconnect, verify only one synchronized event, test restart with pending queue and confirm DTR exports. Do not use synthetic successful scans as evidence that the physical reader works.


## Official Pila contact import (October 9, 2026)
At the user's request, the live directory now includes two Pila Action Center numbers, two PNP numbers, two BFP numbers and the municipal general contact, as published on the official Pila LGU poster/contact page. These are source-verified, not telephone-connectivity-tested; service hours were not published. For another installation run `python tools/import_pila_hotlines.py --actor-id YOUR_ADMIN_ID` from the root. The import is explicit and idempotent, preserves unrelated contacts and stores verification history. Do not treat Pila Action Center as a separately verified RHU, MSWDO or VAWC hotline. Reverify after 180 days.


## Unified resident complaint workspace
The resident sidebar now has one Complaints & Blotter entry at /resident/blotter. This workspace combines owned incident reports and authorized existing blotter records with search, record-type filters and pagination. Submission, formal blotter filing, tracking and verified hotlines are available from that workspace. Existing detailed workflows and record permissions are preserved.
