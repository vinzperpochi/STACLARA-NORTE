"""One paginated resident workspace for both preserved blotter and incident records."""
from math import ceil
from sqlalchemy import select, literal, union_all, func, or_
from app.extensions import db
from app.models import BlotterCase, BlotterCaseAccess, ResidentComplaint, IncidentCategory
from app.pagination import Pagination


def resident_reports(resident_id,page=1,kind='',search=''):
    access=select(BlotterCaseAccess.id).where(BlotterCaseAccess.case_id==BlotterCase.id,BlotterCaseAccess.resident_id==resident_id).exists()
    blotter=select(BlotterCase.id.label('id'),literal('blotter').label('kind'),BlotterCase.case_number.label('reference'),BlotterCase.category.label('title'),BlotterCase.category.label('category'),BlotterCase.status.label('status'),BlotterCase.created_at.label('created_at'),literal(False).label('emergency')).where(or_(BlotterCase.complainant_id==resident_id,access))
    incident=select(ResidentComplaint.id.label('id'),literal('incident').label('kind'),ResidentComplaint.reference.label('reference'),ResidentComplaint.title.label('title'),IncidentCategory.name.label('category'),ResidentComplaint.status.label('status'),ResidentComplaint.created_at.label('created_at'),(ResidentComplaint.classification=='EMERGENCY').label('emergency')).join(IncidentCategory).where(ResidentComplaint.resident_id==resident_id)
    combined=union_all(blotter,incident).subquery()
    query=select(combined)
    if kind in {'blotter','incident'}: query=query.where(combined.c.kind==kind)
    if search: query=query.where(or_(combined.c.reference.ilike('%'+search[:100]+'%'),combined.c.title.ilike('%'+search[:100]+'%')))
    total=db.session.scalar(select(func.count()).select_from(query.subquery())) or 0
    pages=max(1,ceil(total/5));page=max(1,min(page or 1,pages))
    items=db.session.execute(query.order_by(combined.c.emergency.desc(),combined.c.created_at.desc(),combined.c.kind,combined.c.id.desc()).offset((page-1)*5).limit(5)).mappings().all()
    return Pagination(items,page,5,total,pages)


def management_reports(visible_incidents, page=1, kind='', search=''):
    """Combine management records while retaining the incident visibility policy."""
    blotter=select(BlotterCase.id.label('id'),literal('blotter').label('kind'),BlotterCase.case_number.label('reference'),BlotterCase.category.label('title'),BlotterCase.category.label('category'),BlotterCase.status.label('status'),BlotterCase.created_at.label('created_at'),literal(False).label('emergency'))
    allowed=visible_incidents.with_only_columns(ResidentComplaint.id).order_by(None)
    incident=select(ResidentComplaint.id.label('id'),literal('incident').label('kind'),ResidentComplaint.reference.label('reference'),ResidentComplaint.title.label('title'),IncidentCategory.name.label('category'),ResidentComplaint.status.label('status'),ResidentComplaint.created_at.label('created_at'),(ResidentComplaint.classification=='EMERGENCY').label('emergency')).join(IncidentCategory).where(ResidentComplaint.id.in_(allowed))
    combined=union_all(blotter,incident).subquery()
    query=select(combined)
    if kind in {'blotter','incident'}: query=query.where(combined.c.kind==kind)
    if search: query=query.where(or_(combined.c.reference.ilike('%'+search[:100]+'%'),combined.c.title.ilike('%'+search[:100]+'%')))
    total=db.session.scalar(select(func.count()).select_from(query.subquery())) or 0
    pages=max(1,ceil(total/5));page=max(1,min(page or 1,pages))
    items=db.session.execute(query.order_by(combined.c.emergency.desc(),combined.c.created_at.desc(),combined.c.kind,combined.c.id.desc()).offset((page-1)*5).limit(5)).mappings().all()
    return Pagination(items,page,5,total,pages)
