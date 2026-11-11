"""Routes for the public foundation pages."""

from flask import Blueprint, abort, jsonify, redirect, render_template, request
from flask_login import current_user, login_required
from sqlalchemy import or_

from app.auth.session import post_login_url
from app.extensions import db
from app.models import BlotterCase, IssuedDocument, Request, Resident

from . import main_bp


# Public endpoints that don't require auth are listed in auth/session.py's
# PUBLIC_ENDPOINTS set.  Add "main.help_page" and "main.verify" there too.


@main_bp.get("/")
def index():
    """Render the public homepage, or send signed-in users to their workspace."""
    if current_user.is_authenticated:
        return redirect(post_login_url())
    return render_template("index.html")


@main_bp.get("/health")
def health_check():
    """Return a lightweight service and database health response."""
    database_status = "ok"
    try:
        db.session.execute(db.text("SELECT 1"))
    except Exception:
        database_status = "error"

    status_code = 200 if database_status == "ok" else 503
    return jsonify({"status": "ok" if status_code == 200 else "degraded", "database": database_status}), status_code


@main_bp.get("/privacy")
def privacy_notice():
    return render_template("privacy.html")


@main_bp.get("/search")
@login_required
def search():
    role_names = {role.name for role in current_user.roles}
    if "System Administrator" not in role_names and "Barangay Official" not in role_names:
        abort(403)
    query = (request.args.get("q") or "").strip()
    from app.pagination import paginate_named
    pagers={}
    residents,cases,requests=[],[],[]
    if len(query)>=2:
        pattern=f"%{query}%"
        queries={
            'residents': db.select(Resident).where(or_(Resident.first_name.ilike(pattern),Resident.middle_name.ilike(pattern),Resident.last_name.ilike(pattern),Resident.email.ilike(pattern))).order_by(Resident.last_name,Resident.first_name),
            'cases': db.select(BlotterCase).where(or_(BlotterCase.case_number.ilike(pattern),BlotterCase.category.ilike(pattern),BlotterCase.respondent_name.ilike(pattern))).order_by(BlotterCase.created_at.desc()),
            'requests': db.select(Request).where(or_(Request.request_number.ilike(pattern),Request.service_type.ilike(pattern),Request.description.ilike(pattern))).order_by(Request.created_at.desc()),
        }
        pagers={key:paginate_named(value,key+'_page') for key,value in queries.items()}
        residents,cases,requests=[pagers[key].items for key in ['residents','cases','requests']]
    return render_template("search.html",query=query,residents=residents,cases=cases,requests=requests,pagers=pagers)



@main_bp.get("/help")
def help_page():
    """Public help / contact page."""
    return render_template("help.html")


@main_bp.get("/verify")
def verify():
    """Document verification search — accepts an optional ?doc= query param."""
    doc_number = request.args.get("doc", "").strip()
    if doc_number:
        return redirect(request.url_root.rstrip("/") + f"/verify/{doc_number}")
    return render_template("verify_search.html")


@main_bp.get("/verify/<document_number>")
def verify_document(document_number: str):
    """Display only non-sensitive facts needed to validate an issued document."""
    if len(document_number) > 80 or not all(character.isalnum() or character in "-_" for character in document_number):
        return render_template("verify.html", document_number="unrecognized document", document=None), 404
    document = db.session.scalar(db.select(IssuedDocument).where(db.or_(IssuedDocument.verification_token == document_number, db.and_(IssuedDocument.verification_token.is_(None), IssuedDocument.document_number == document_number))))
    if document is None:
        return render_template("verify.html", document_number=document_number, document=None), 404
    datetime_module = __import__("datetime")
    now = datetime_module.datetime.now(datetime_module.timezone.utc)
    expires_at = document.expires_at
    if expires_at is not None and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=datetime_module.timezone.utc)
    state="Revoked" if document.status=="revoked" else "Expired" if expires_at and expires_at<now else "Valid" if document.status=="released" else "Not issued"
    is_valid=state=="Valid"
    return render_template("verify.html", document_number=document_number, document=document, is_valid=is_valid,verification_state=state), 200
