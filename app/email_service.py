"""SMTP email helpers for account lifecycle notifications."""
from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr

from flask import current_app


def send_verification_email(*, recipient: str, full_name: str, verification_url: str, valid_hours: int) -> None:
    """Send the email-ownership verification link for a new resident registration."""
    message = _new_message(
        recipient=recipient,
        subject="I-verify ang iyong email - Barangay Sta. Clara Norte",
        body=f"""Magandang araw, {full_name}!

Natanggap namin ang iyong registration sa Barangay Sta. Clara Norte e-Governance.

I-click ang link na ito para i-verify ang iyong email address:
{verification_url}

Ang link ay may bisa sa loob ng {valid_hours} oras. Pagkatapos ma-verify, hihintayin pa rin ang pag-apruba ng barangay staff bago ma-activate ang iyong account. Ipapadala sa email na ito ang iyong Resident ID at pansamantalang password kapag naaprubahan.

Kung hindi ikaw ang nagparehistro, huwag pansinin ang email na ito.

Barangay Sta. Clara Norte e-Governance
""",
    )
    _deliver(message)


def send_official_created_resident_verification(*, recipient: str, full_name: str, verification_url: str, valid_hours: int) -> None:
    """Ask a staff-approved resident to verify email before account activation."""
    message = _new_message(
        recipient=recipient,
        subject="Kumpirmahin ang iyong aprubadong barangay account",
        body=f"""Magandang araw, {full_name}!

Inaprubahan na ng barangay ang iyong resident registration. Para ma-activate ang account, i-verify muna ang pagmamay-ari mo sa email address na ito:

{verification_url}

May bisa ang link sa loob ng {valid_hours} oras. Pagkatapos ma-verify, ipapadala sa email na ito ang iyong Resident ID at pansamantalang password. Kailangan mong palitan ang pansamantalang password sa unang pag-login.

Kung hindi ikaw ang nagparehistro, huwag buksan ang link at makipag-ugnayan sa Barangay Sta. Clara Norte.

Barangay Sta. Clara Norte e-Governance
""",
    )
    _deliver(message)


def send_resident_credentials(*, recipient: str, full_name: str, resident_id: str, temporary_password: str) -> None:
    """Send approved resident credentials; raise if SMTP is not configured or delivery fails."""
    message = _new_message(
        recipient=recipient,
        subject="Naaprubahan ang iyong Barangay resident account",
        body=f"""Magandang araw, {full_name}!

Naaprubahan at na-activate na ang iyong resident account.

Resident ID: {resident_id}
Pansamantalang password: {temporary_password}

Gamitin ang Resident ID at pansamantalang password para mag-sign in. Para sa seguridad, kailangan mong palitan ang password sa unang pag-login. Huwag ibahagi ang password na ito.

Kung hindi ikaw ang nagparehistro, makipag-ugnayan agad sa Barangay Sta. Clara Norte.

Barangay Sta. Clara Norte e-Governance
""",
    )
    _deliver(message)


def send_activation_code(*, recipient: str, full_name: str, activation_code: str, resident_id: str, temporary_password: str) -> None:
    """Send login credentials after official activates resident account."""
    message = _new_message(
        recipient=recipient,
        subject="Account Activated - Barangay Resident Login",
        body=f"""Magandang araw, {full_name}!

Na-activate na ang inyong resident account!

Ito ang inyong login credentials:

━━━━━━━━━━━━━━━━━━━━━━━━━━
Resident ID: {resident_id}
Password: {temporary_password}
━━━━━━━━━━━━━━━━━━━━━━━━━━

MAKAPAG-LOGIN NA KAYO NGAYON!

Pumunta sa login page at gamitin ang credentials sa itaas.

IMPORTANTE: Para sa seguridad, kailangan mong palitan ang password sa unang pag-login.

Kung hindi ikaw ang nagparehistro, makipag-ugnayan agad sa Barangay Sta. Clara Norte.

Barangay Sta. Clara Norte e-Governance
""",
    )
    _deliver(message)


def send_official_credentials(*, recipient: str, full_name: str, official_id: str, temporary_password: str) -> None:
    """Send the generated official login credentials through the configured SMTP server."""
    message = _new_message(
        recipient=recipient,
        subject="Nagawa ang iyong Barangay Official account",
        body=f"""Magandang araw, {full_name}!

Nagawa na ang iyong Barangay Sta. Clara Norte official account.

Official ID / Login ID: {official_id}
Email: {recipient}
Pansamantalang password: {temporary_password}

Gamitin ang Official ID o email at pansamantalang password para mag-sign in. Para sa seguridad, kailangan mong palitan ang password sa unang pag-login. Huwag ibahagi ang password na ito.

Kung hindi ikaw ang inaasahang recipient, makipag-ugnayan agad sa Barangay Sta. Clara Norte.

Barangay Sta. Clara Norte e-Governance
""",
    )
    _deliver(message)


def send_smtp_test(*, recipient: str) -> None:
    """Send a diagnostic message without activating an account or including credentials."""
    message = _new_message(
        recipient=recipient,
        subject="Barangay SMTP configuration test",
        body=(
            "SMTP test successful. This message only confirms that the configured mail server "
            "can send email. No resident account was activated and no credentials were included.\n"
        ),
    )
    _deliver(message)


def _new_message(*, recipient: str, subject: str, body: str) -> EmailMessage:
    config = current_app.config
    sender = config.get("SMTP_FROM_EMAIL") or config.get("SMTP_USERNAME")
    if not sender:
        raise RuntimeError("Set SMTP_FROM_EMAIL (or SMTP_USERNAME for Gmail) before sending email.")
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = formataddr((config.get("SMTP_FROM_NAME", "Barangay e-Governance"), sender))
    message["To"] = recipient
    message.set_content(body)
    return message


def _deliver(message: EmailMessage) -> None:
    config = current_app.config
    host = (config.get("SMTP_HOST") or "").strip()
    if not host:
        raise RuntimeError("SMTP_HOST must be configured before sending email.")
    is_gmail = host.lower() == "smtp.gmail.com"
    if is_gmail and (not config.get("SMTP_USERNAME") or not config.get("SMTP_PASSWORD")):
        raise RuntimeError("Gmail SMTP requires SMTP_USERNAME and a Google App Password in SMTP_PASSWORD.")
    timeout = int(config.get("SMTP_TIMEOUT", 15))
    tls_context = ssl.create_default_context()
    try:
        if config.get("SMTP_USE_SSL"):
            with smtplib.SMTP_SSL(host, config.get("SMTP_PORT", 465), timeout=timeout, context=tls_context) as server:
                _smtp_authenticate(server, config)
                server.send_message(message)
            return

        with smtplib.SMTP(host, config.get("SMTP_PORT", 587), timeout=timeout) as server:
            server.ehlo()
            if config.get("SMTP_STARTTLS", True):
                server.starttls(context=tls_context)
                server.ehlo()
            _smtp_authenticate(server, config)
            server.send_message(message)
    except smtplib.SMTPAuthenticationError as exc:
        raise RuntimeError(
            "SMTP login was rejected. For Gmail, use the full Gmail address as SMTP_USERNAME and a "
            "16-character Google App Password (2-Step Verification must be on), not your normal password."
        ) from exc
    except (smtplib.SMTPConnectError, TimeoutError, OSError) as exc:
        raise RuntimeError(
            f"Could not connect to {host}:{config.get('SMTP_PORT')}. Check SMTP_HOST/SMTP_PORT, "
            "your internet connection, and that your firewall allows outgoing SMTP."
        ) from exc


def _smtp_authenticate(server: smtplib.SMTP, config: dict) -> None:
    username = config.get("SMTP_USERNAME")
    # Google shows App Passwords in groups of four with spaces; the spaces are not part of the password.
    password = config.get("SMTP_PASSWORD") or ""
    if (config.get("SMTP_HOST") or "").strip().lower() == "smtp.gmail.com":
        password = password.replace(" ", "")
    if username:
        server.login(username, password)
