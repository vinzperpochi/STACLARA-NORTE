# Single-reader RFID registration and local Wi-Fi testing

## Start the system

The current local configuration uses:

```dotenv
FLASK_CONFIG=development
HOST=0.0.0.0
PORT=5000
ATTENDANCE_LOCAL_TEST_MODE=true
```

Restart the server with `python run.py` after changing these settings. Keep the computer and ESP32 on the same private Wi-Fi network. The computer's current address is `192.168.1.14`, so the sketch uses `http://192.168.1.14:5000`. Update `SERVER_URL` if the computer's address changes. The computer must keep the system running and retain access to Supabase. The ESP32 cannot reach the PC using `127.0.0.1`.

## Upload the Wi-Fi firmware

Use `hardware/esp32_rfid_wifi/esp32_rfid_wifi.ino`. Fill in the Wi-Fi name and password. There is no manual device credential, root CA certificate, Supabase anon key, or reader enrollment form. The sketch preserves the GPIO wiring from the supplied OLED/button demo. Libraries: MFRC522, Adafruit GFX, Adafruit SSD1306, ArduinoJson 7. Stop the USB Python bridge when using this Wi-Fi sketch.

## Pair and register

1. Super Admin opens the single **Personnel & RFID** page and chooses **Has a system account** or **No system account**. The first option reveals an active-account picker that links the personnel record to that account; known name, role and email values can be filled from the selection and reviewed before saving. No account option registers a barangay worker without creating a login. Enter first/last name and barangay role, then set the first work schedule. Others reveals a custom role field. Employee ID, contact details, department, employment status and photo are optional; an employee ID is generated if omitted.
2. Click **Scan RFID Card/Tag**. The backend creates its one internal local reader record automatically and opens a 60-second capture reservation.
3. The ESP32 connects directly over Wi-Fi. Its automatically generated chip identifier is paired only while an administrator's capture modal is waiting. No identifier is typed or selected on the page.
4. Wait until the modal says **Waiting for card**, then tap the card/tag. An existing or revoked UID is rejected and the modal waits for a different card. A detected card shows a confirmation with its suffix and the entered personnel name. Click **Use this card** to attach it and enable Save, **Scan again** to use a different card, or Cancel to discard it. Detection alone does not record attendance, attach a token to the form, or save a card assignment.
5. After confirming **Use this card**, click **Save personnel, schedule & RFID** within five minutes of capture. Capture/confirmation is temporary and is not a saved assignment. The backend saves the profile, account link (if selected), initial schedule and scanned card together in one transaction; validation failure does not leave a partial registration. After commit, the page reloads the saved record from the database and displays the assigned personnel, account and card suffix. The card's UID digest and suffix go to `public.rfid_cards`.
6. A person/account can only use this registration flow once. Existing personnel without any card may receive their first card, keeping their account link and schedule. A person with any recorded card cannot be registered again, including after revocation. Selecting an already registered account displays its saved card and disables another scan/save. A UID can never be reused or reassigned, even if revoked. A partial unique database index allows at most one active card per personnel; the existing unique account link allows only one personnel profile per user.
7. Use **Manage record** for changes. An unlinked personnel record can be connected to an unused active account here without creating another profile or changing its saved RFID/history. Existing account links cannot be silently replaced. An explicit card replacement revokes the old card and assigns one new, never-before-used UID; old card ownership/history remain intact. Old `/attendance/personnel` links redirect to the combined page; the separate personnel creation form is retired.

Cancel releases the reservation. Pairing persists across server restarts and DHCP address changes for the same ESP32 chip. A different chip identifier is rejected after pairing. Historical/manual reader records are retained. No reader setup or device health panel is shown in the registration UI.

Attendance account pickers list only active users with an active Barangay Official or System Administrator role. Resident-only accounts are excluded and are also rejected by the registration and account-linking POST handlers. Barangay staff without a login can still use No system account. These checks are scoped to attendance and do not change resident roles, accounts, app pages or the resident dashboard.

Account status and personnel status are separate. For an inactive profile without a prior RFID assignment, selecting its account shows **Reactivate this personnel record** and a Review record link. Super Admin must explicitly check it for that exact profile before first enrollment; reactivation, account linking and card registration commit together and are audited. For an already registered inactive profile, use Manage record to activate it instead of registering another card. Validation failure rolls back reactivation and preserves a still-valid captured card. Disabled login accounts and revoked cards are not automatically enabled.

## Attendance

### Account creation and attendance history

New official accounts created under **Official Accounts**, and new System
Administrator accounts created under **Users** or the account-creation scripts,
receive a linked personnel record in the same transaction. Creating a login does
not create a scan, work schedule, or Present record. For a new worker, enroll the
card and schedule under **Personnel & RFID**, choosing **Has a system account**;
this reuses the account's personnel record.

When the worker already has RFID or attendance history, select their unused
record in **Attendance personnel record** while creating the account. The card,
schedule and historical sessions keep the same IDs and become visible in that
official's **My Attendance** and reports. Matching names alone never link records.
An existing unlinked record with the same name must be explicitly selected.
The CLI creation functions also accept an explicit `personnel_id` keyword.

Existing account links cannot be overwritten or assigned to a second account.
Resident-only accounts cannot claim personnel records. Super Admin retains the
all-personnel view; officials see only their own linked record. Old unlinked
accounts show a setup notice rather than silently displaying an empty dashboard.
Attendance pages are not cached, and the existing 30-second refresh shows new
accepted scans when the page is idle. Deleting a login retains its personnel,
RFID and attendance history and clears only that account link.

The server supplies the name and next IN/OUT action through the read-only preview endpoint. Time In requires a fresh button press within ten seconds; Time Out requires only a tap. The final scan rechecks schedule, active card/account status, leave, repeat timing, and session rules. Green success follows server acceptance. Server time is synchronized through the mode response, so this sketch does not require a certificate or NTP connection.

Time In opens exactly five minutes before the assigned shift starts, including flexible schedules. For an 08:00 shift, 07:55:00 is accepted and 07:54:59 is rejected with the opening time shown on the reader. Preview and final scan use the same server rule. A shift just after midnight can accept its five-minute early arrival on the preceding calendar date while retaining the shift's actual work date. The existing late-arrival/grace and Time Out rules continue to apply.

Daily records include Time In and Time Out in Philippine Standard Time (UTC+8), with one aligned pair per session. Dates are displayed to identify overnight time-outs. An open session shows Not yet for Time Out; personnel with no sessions show dashes. Session counts and hours retain their existing calculations.

Time Out is accepted before the scheduled end and marked **Early out**, with the early minutes recorded in session metrics and scan messages. The stored minimum-session value is a short-session review threshold, not a block on departure. The 30-second rapid-repeat check, chronological ordering and 24-hour open-session limit remain enforced. The account choices are full clickable cards with visible radio controls, keyboard focus, and a selected check mark.

If an attendance response is lost, the sketch retains one event and its original ID/timestamp in flash. It retries that event and blocks new scans until acceptance or terminal rejection. Pending events are never shown as successful. Registration taps are not put in that queue.

## Local mode limits

This credential-free transport is for a trusted private LAN demo, not public deployment. The chip ID identifies the one reader but is not a secret. Local mode must be explicitly enabled, accepts only direct RFC1918/loopback peers and LAN/localhost Host addresses, rejects forwarded/proxied traffic, and is refused by production configuration. Existing credential-based HTTPS authentication remains available without the local-test header.

Pairing/reservations are stored privately under `STORAGE_ROOT/bridge/registration.sqlite`, shared by workers on the same application host. The main database keeps personnel, cards, attendance, and audit records. Local mode needs no additional main-database migration. Migration `e8b2f901d6aa` from the preceding update allows personnel without account links or supplemental contact/photo details.

Migration `f2a914c8b031` enforces one active RFID per personnel. It does not alter assignments and refuses to run if multiple active cards already exist for a person, requiring an explicit choice before enforcing the index. Registration also takes account/personnel row locks and a transaction-scoped name lock on PostgreSQL to prevent simultaneous duplicate enrollment.
