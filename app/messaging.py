"""In-app resident/official messaging with a deterministic customer-service fallback."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
import json
from urllib.error import HTTPError, URLError
from urllib.request import Request as UrlRequest, urlopen
from flask import Blueprint, current_app, jsonify, render_template, request
from flask_login import current_user
from sqlalchemy import func
from app.auth.decorators import official_account_required, resident_owner_required
from app.extensions import db
from app.models import Message, MessageThread, User

messaging_bp = Blueprint("messaging", __name__, url_prefix="/messaging")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _serialize(message: Message) -> dict:
    return {
        "id": message.id,
        "sender_type": message.sender_type,
        "sender_name": (current_app.config.get("CHATBOT_NAME") or current_app.config["BARANGAY_NAME"] + " Assistant") if message.sender_type == "BOT" else (
            "You" if message.sender_user_id == current_user.id else (
                message.sender.username if message.sender else "Barangay Official"
            )
        ),
        "body": message.body,
        "created_at": message.created_at.isoformat() if message.created_at else None,
    }


def _faq_reply(body: str) -> str:
    text = body.casefold()
    if any(word in text for word in ("document", "certificate", "clearance", "sertipiko")):
        return "Chatbot: Para sa certificate, dokumento, o clearance, pumunta sa Documents sa iyong portal at i-check ang status ng request. Kung may request number ka, isama ito sa susunod na mensahe."
    if any(word in text for word in ("queue", "pila", "appointment", "schedule")):
        return "Chatbot: Makikita ang iyong pila at schedule sa Queue status. Hintayin ang opisyal na reply para sa pagbabago ng schedule o priority."
    if any(word in text for word in ("blotter", "complaint", "reklamo", "incident")):
        return "Chatbot: Maaari kang mag-file ng reklamo sa Complaints. Para sa agarang panganib, tumawag sa barangay emergency contact; huwag hintayin ang chat reply."
    if any(word in text for word in ("profile", "correction", "address", "name")):
        return "Chatbot: Para sa correction ng record, gamitin ang Corrections page at ilahad ang field na kailangang baguhin at dahilan."
    return "Chatbot: Salamat sa iyong mensahe. Makakatulong ako sa basic questions tungkol sa documents, pila, reklamo, at profile corrections. May notification din ang barangay team at sasagot sila sa lalong madaling panahon."


def _gemini_reply(thread: MessageThread, body: str) -> str | None:
    """Ask Gemini for a concise barangay-service reply; return None on any API failure."""
    api_key = current_app.config.get("GEMINI_API_KEY", "")
    if not api_key:
        return None
    history = db.session.scalars(
        db.select(Message).where(Message.thread_id == thread.id).order_by(Message.created_at.desc(), Message.id.desc()).limit(10)
    ).all()
    contents = []
    for item in reversed(history):
        role = "model" if item.sender_type == "BOT" else "user"
        contents.append({"role": role, "parts": [{"text": item.body[:2000]}]})
    contents.append({"role": "user", "parts": [{"text": body}]})
    payload = {
        "systemInstruction": {"parts": [{"text": (
            f"Ikaw ang assistant ng {current_app.config["BARANGAY_NAME"]} sa Pilipinas. Huwag banggitin ang AI provider. "
            "Sumagot sa Filipino o simpleng Taglish, maikli at magalang. "
            "Magbigay lamang ng general guidance tungkol sa barangay services. "
            "Huwag mangako ng approval, huwag humingi ng password/OTP/API key, "
            "at sabihin na official ang kailangan para sa case-specific decision. "
            "Para sa emergency o agarang panganib, sabihin na tumawag sa emergency contact at huwag umasa sa chat."
        )}]},
        "contents": contents,
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 220, "responseMimeType": "text/plain"},
    }
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{current_app.config.get('GEMINI_MODEL', 'gemini-3.8-flash')}:generateContent"
    try:
        req = UrlRequest(url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json", "x-goog-api-key": api_key}, method="POST")
        with urlopen(req, timeout=int(current_app.config.get("GEMINI_API_TIMEOUT_SECONDS", 12))) as response:
            data = json.loads(response.read().decode("utf-8"))
        text = "".join(part.get("text", "") for part in data.get("candidates", [])[0].get("content", {}).get("parts", []))
        return text.strip()[:4000] or None
    except (HTTPError, URLError, TimeoutError, ValueError, KeyError, IndexError) as exc:
        current_app.logger.warning("Gemini chatbot unavailable; using FAQ fallback: %s", type(exc).__name__)
        return None


def _chatbot_reply(thread: MessageThread, body: str) -> str:
    return _gemini_reply(thread, body) or _faq_reply(body)


def _get_or_create_thread(resident_id: int) -> MessageThread:
    thread = db.session.scalar(db.select(MessageThread).where(MessageThread.resident_id == resident_id))
    if thread is None:
        thread = MessageThread(resident_id=resident_id, subject="General assistance", status="OPEN", last_message_at=_now())
        db.session.add(thread)
        db.session.flush()
    return thread


def _maybe_auto_reply(thread: MessageThread) -> None:
    latest = db.session.scalar(
        db.select(Message).where(Message.thread_id == thread.id).order_by(Message.created_at.desc(), Message.id.desc())
    )
    if not latest or latest.sender_type != "RESIDENT":
        return
    delay = int(current_app.config.get("MESSAGING_AUTO_REPLY_DELAY_SECONDS", 120))
    created = latest.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    if _now() - created < timedelta(seconds=delay):
        return
    bot_already_replied = db.session.scalar(
        db.select(func.count(Message.id)).where(
            Message.thread_id == thread.id,
            Message.sender_type == "BOT",
            Message.created_at >= latest.created_at,
        )
    )
    if bot_already_replied:
        return
    db.session.add(Message(thread_id=thread.id, sender_type="BOT", body=_chatbot_reply(thread, latest.body), is_read=False))
    thread.last_message_at = _now()
    db.session.commit()


@messaging_bp.get("/api/thread")
@resident_owner_required
def resident_thread():
    thread = _get_or_create_thread(current_user.resident.id)
    _maybe_auto_reply(thread)
    messages = db.session.scalars(db.select(Message).where(Message.thread_id == thread.id).order_by(Message.created_at, Message.id)).all()
    for item in messages:
        if item.sender_type in ("OFFICIAL", "BOT"):
            item.is_read = True
    db.session.commit()
    return jsonify(thread={"id": thread.id, "status": thread.status}, messages=[_serialize(item) for item in messages])


@messaging_bp.post("/api/thread/messages")
@resident_owner_required
def resident_send():
    body = (request.form.get("body") or "").strip()
    if not body or len(body) > 2000:
        return jsonify(error="Mensahe ay kailangang 1–2000 characters."), 400
    thread = _get_or_create_thread(current_user.resident.id)
    if thread.status == "CLOSED":
        thread.status = "OPEN"
        thread.closed_at = None
    db.session.add(Message(thread_id=thread.id, sender_user_id=current_user.id, sender_type="RESIDENT", body=body, is_read=False))
    chatbot_mode = request.form.get("mode") == "chatbot"
    if chatbot_mode:
        db.session.add(Message(thread_id=thread.id, sender_type="BOT", body=_chatbot_reply(thread, body), is_read=False))
    thread.last_message_at = _now()
    db.session.commit()
    return jsonify(ok=True, chatbot=chatbot_mode)


@messaging_bp.get("/official")
@official_account_required
def official_inbox():
    return render_template("official/messages.html")


@messaging_bp.get("/api/inbox")
@official_account_required
def official_inbox_api():
    threads = db.session.scalars(db.select(MessageThread).order_by(MessageThread.last_message_at.desc())).all()
    result = []
    for thread in threads:
        latest = db.session.scalar(db.select(Message).where(Message.thread_id == thread.id).order_by(Message.created_at.desc(), Message.id.desc()))
        unread = db.session.scalar(db.select(func.count(Message.id)).where(Message.thread_id == thread.id, Message.sender_type == "RESIDENT", Message.is_read.is_(False))) or 0
        result.append({"id": thread.id, "resident_name": " ".join(filter(None, [thread.resident.first_name, thread.resident.last_name])), "status": thread.status, "unread": unread, "latest": latest.body if latest else "", "last_message_at": thread.last_message_at.isoformat()})
    return jsonify(threads=result)


@messaging_bp.get("/api/inbox/<int:thread_id>")
@official_account_required
def official_thread(thread_id: int):
    thread = db.get_or_404(MessageThread, thread_id)
    messages = db.session.scalars(db.select(Message).where(Message.thread_id == thread.id).order_by(Message.created_at, Message.id)).all()
    for item in messages:
        if item.sender_type == "RESIDENT":
            item.is_read = True
    db.session.commit()
    return jsonify(thread={"id": thread.id, "resident_name": " ".join(filter(None, [thread.resident.first_name, thread.resident.last_name])), "status": thread.status}, messages=[_serialize(item) for item in messages])


@messaging_bp.post("/api/inbox/<int:thread_id>/messages")
@official_account_required
def official_send(thread_id: int):
    body = (request.form.get("body") or "").strip()
    if not body or len(body) > 2000:
        return jsonify(error="Mensahe ay kailangang 1–2000 characters."), 400
    thread = db.get_or_404(MessageThread, thread_id)
    db.session.add(Message(thread_id=thread.id, sender_user_id=current_user.id, sender_type="OFFICIAL", body=body, is_read=False))
    thread.status = "OPEN"
    thread.last_message_at = _now()
    db.session.commit()
    return jsonify(ok=True)
