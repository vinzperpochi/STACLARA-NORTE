"""Public document verification and QR-code helpers."""

from __future__ import annotations

import base64
from io import BytesIO
from urllib.parse import quote

import qrcode
from flask import current_app, has_request_context, url_for


def verification_url(document_number: str) -> str:
    base = current_app.config.get("DOCUMENT_VERIFICATION_BASE_URL", "").rstrip("/")
    path = f"/verify/{quote(document_number, safe='')}"
    if base:
        return f"{base}{path}"
    if has_request_context():
        return url_for("main.verify_document", document_number=document_number, _external=True)
    return path


def qr_data_uri(value: str) -> str:
    image = qrcode.make(value)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")
