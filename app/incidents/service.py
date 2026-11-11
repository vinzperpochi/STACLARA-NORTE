"""Deterministic recommendations; no call, transmission or resolution is implied."""
from datetime import date, datetime, timedelta, timezone
import re
from sqlalchemy import select
from flask_login import current_user
from app.extensions import db
from app.models import GovernmentAgency, AgencyHotline, IncidentCategory, IncidentRoutingRule, ResidentComplaint, ComplaintStatusHistory, ComplaintAssignment, ComplaintNotification, ComplaintAuditLog, Notification, Role, User

AGENCIES={'BFP':'Bureau of Fire Protection','PNP':'Philippine National Police','911':'Emergency 911','RHU':'Rural Health Unit / Municipal Health Office','MDRRMO':'Municipal Disaster Risk Reduction and Management Office','VAWC':'Authorized VAWC Response Personnel','MSWDO':'Municipal Social Welfare and Development Office','BARANGAY':'Barangay Complaint and Mediation Office','ENVIRONMENT':'Municipal Environment Office','ENGINEERING':'Municipal Engineering Office','UTILITY':'Authorized Electricity Utility Provider','WATER':'Authorized Water Service Provider','VETERINARY':'Municipal Veterinary Office'}
# code, label, class, agencies, multilingual indicators, restricted
INITIAL_RULES=[
 ('FIRE','Fire / smoke emergency','EMERGENCY',['BFP','911'],['nasusunog','sunog','burning house','fire emergency','smoke emergency'],False),
 ('MEDICAL','Serious medical emergency','EMERGENCY',['911','RHU'],['hindi humihinga','not breathing','unconscious','nahimatay','severe bleeding'],True),
 ('VIOLENCE','Assault / active violence','EMERGENCY',['PNP','911'],['armado','armed suspect','active violence','may baril','gunshot','binabaril'],True),
 ('ACCIDENT','Road accident with injuries','EMERGENCY',['911','PNP','RHU'],['road accident','aksidente','injured accident'],False),
 ('DISASTER','Flooding / typhoon / disaster','EMERGENCY',['MDRRMO','911'],['baha','flood','typhoon','bagyo','landslide'],False),
 ('ROBBERY','Robbery / theft / serious crime','REFERRAL',['PNP'],['holdap','robbery','theft','nakawan','nangholdap'],True),
 ('VAWC','Domestic violence / VAWC','REFERRAL',['VAWC','PNP','MSWDO'],['domestic violence','vawc','violence against women'],True),
 ('CHILD','Child abuse / child protection','REFERRAL',['PNP','MSWDO'],['child abuse','child protection','abuso sa bata'],True),
 ('HEALTH','Health concern / illness','REFERRAL',['RHU'],['health concern','non emergency illness','sakit'],True),
 ('GARBAGE','Garbage / waste disposal','BARANGAY',['BARANGAY','ENVIRONMENT'],['garbage','basura','waste disposal'],False),
 ('NOISE','Noise complaint','BARANGAY',['BARANGAY'],['noise','ingay','videoke'],False),
 ('DISPUTE','Neighborhood dispute','BARANGAY',['BARANGAY'],['neighbor dispute','kapitbahay','alitan'],False),
 ('PROPERTY','Property dispute','REVIEW',['BARANGAY'],['property dispute','boundary','lupa'],True),
 ('INFRASTRUCTURE','Infrastructure damage','REFERRAL',['ENGINEERING','BARANGAY'],['infrastructure','sirang kalsada','damaged road'],False),
 ('ELECTRICITY','Electricity hazard','REFERRAL',['UTILITY','911'],['live wire','kuryente','electricity hazard'],False),
 ('WATER','Water supply concern','REFERRAL',['WATER'],['water supply','tubig'],False),
 ('ANIMAL','Stray animal complaint','BARANGAY',['BARANGAY','VETERINARY'],['stray animal','stray dog','ligaw na aso'],False),
 ('SANITATION','Public health / sanitation','BARANGAY',['BARANGAY','RHU'],['sanitation','public health','sanitasyon'],False),
 ('UNKNOWN','Other / needs classification','REVIEW',['BARANGAY'],[],False),
]
STATUSES=['SUBMITTED','UNDER_INITIAL_REVIEW','ASSIGNED','UNDER_INVESTIGATION','FOR_MEDIATION','ACTION_REQUIRED','FOR_EXTERNAL_REFERRAL','REFERRED_TO_EXTERNAL_AGENCY','AWAITING_AGENCY_RESPONSE','RESOLVED','CLOSED','REOPENED']
TRANSITIONS={
 'SUBMITTED':{'UNDER_INITIAL_REVIEW','ASSIGNED','FOR_EXTERNAL_REFERRAL'},
 'UNDER_INITIAL_REVIEW':{'ASSIGNED','UNDER_INVESTIGATION','FOR_MEDIATION','ACTION_REQUIRED','FOR_EXTERNAL_REFERRAL','RESOLVED'},
 'ASSIGNED':{'UNDER_INVESTIGATION','FOR_MEDIATION','ACTION_REQUIRED','FOR_EXTERNAL_REFERRAL','RESOLVED'},
 'UNDER_INVESTIGATION':{'FOR_MEDIATION','ACTION_REQUIRED','FOR_EXTERNAL_REFERRAL','RESOLVED'},
 'FOR_MEDIATION':{'ACTION_REQUIRED','FOR_EXTERNAL_REFERRAL','RESOLVED'},
 'ACTION_REQUIRED':{'UNDER_INVESTIGATION','FOR_MEDIATION','FOR_EXTERNAL_REFERRAL','RESOLVED'},
 'FOR_EXTERNAL_REFERRAL':{'UNDER_INVESTIGATION','REFERRED_TO_EXTERNAL_AGENCY'},
 'REFERRED_TO_EXTERNAL_AGENCY':{'AWAITING_AGENCY_RESPONSE','ACTION_REQUIRED','RESOLVED'},
 'AWAITING_AGENCY_RESPONSE':{'ACTION_REQUIRED','RESOLVED'},
 'RESOLVED':{'CLOSED','REOPENED'},'CLOSED':{'REOPENED'},
 'REOPENED':{'UNDER_INITIAL_REVIEW','ASSIGNED','UNDER_INVESTIGATION','FOR_EXTERNAL_REFERRAL'},
}
NATIONAL_SOURCE='https://www.pna.gov.ph/articles/1281331'


def ensure_directory():
    for code,name in AGENCIES.items():
        if not db.session.scalar(select(GovernmentAgency).where(GovernmentAgency.code==code)):
            db.session.add(GovernmentAgency(code=code,name=name,service_area='Philippines' if code=='911' else 'Pila, Laguna'))
    for priority,(code,name,classification,agencies,keywords,sensitive) in enumerate(INITIAL_RULES):
        category=db.session.scalar(select(IncidentCategory).where(IncidentCategory.code==code))
        if not category:
            category=IncidentCategory(code=code,name=name,sensitive=sensitive);db.session.add(category);db.session.flush()
            db.session.add(IncidentRoutingRule(category_id=category.id,agency_codes=agencies,keywords=keywords,classification=classification,priority=priority))
    db.session.flush()


def contacts(codes):
    today=date.today();result=[]
    for code in codes:
        agency=db.session.scalar(select(GovernmentAgency).where(GovernmentAgency.code==code,GovernmentAgency.active.is_(True)))
        if not agency: continue
        hotlines=db.session.scalars(select(AgencyHotline).where(AgencyHotline.agency_id==agency.id,AgencyHotline.active.is_(True),AgencyHotline.verified_on>=today-timedelta(days=180),AgencyHotline.verified_on<=today,AgencyHotline.verification_source.is_not(None))).all()
        for hotline in hotlines:
            number=re.sub(r'[ ()\-]','',hotline.number)
            if re.fullmatch(r'\+?[0-9]{3,15}',number):
                result.append({'agency':agency.name,'code':code,'number':hotline.number,'tel':number,'availability':hotline.availability,'coverage':hotline.coverage,'verified_on':hotline.verified_on.isoformat(),'source':hotline.verification_source})
    return result


def classify(category_code,description='',urgency='normal',danger=False,external=False):
    rules=db.session.scalars(select(IncidentRoutingRule).join(IncidentCategory).where(IncidentRoutingRule.active.is_(True),IncidentCategory.active.is_(True)).order_by(IncidentRoutingRule.priority)).all()
    selected=next((r for r in rules if r.category.code==category_code),None)
    text=str(description).casefold()[:10000]
    emergency_matches=[r for r in rules if r.classification=='EMERGENCY' and any(str(k).casefold() in text for k in r.keywords)]
    rule=emergency_matches[0] if emergency_matches else selected
    if not rule: rule=next((r for r in rules if r.category.code=='UNKNOWN'),None)
    classification=rule.classification if rule else 'REVIEW'
    if danger or urgency=='emergency': classification='EMERGENCY'
    elif external and classification!='EMERGENCY': classification='REFERRAL'
    codes=list(rule.agency_codes if rule else ['BARANGAY'])
    if classification=='EMERGENCY' and '911' not in codes: codes.append('911')
    found=contacts(codes)
    if classification=='EMERGENCY' and not any(c['code']=='911' for c in found):
        found.append({'agency':'Emergency 911','code':'911','number':'911','tel':'911','availability':'National emergency fallback','coverage':'Philippines','verified_on':'2026-10-09','source':NATIONAL_SOURCE})
    return {'classification':classification,'category_code':rule.category.code if rule else 'UNKNOWN','agency_codes':codes,'contacts':found,'restricted':bool((rule and rule.category.sensitive) or (selected and selected.category.sensitive)),'rule_id':rule.id if rule else None,'rule_version':rule.version if rule else None,'reason':'Immediate danger indicator' if danger else ('Emergency description indicator' if emergency_matches else ('External review requested' if external else 'Selected incident category')),'requires_human_review':True,'warning':'Possible emergency. Contact emergency services now if safe. Do not wait for an online reply.' if classification=='EMERGENCY' else 'Agency recommendations require human review; no report has been sent to an external agency.'}


def admin(user=None):
    user=user or current_user
    return any(r.name=='System Administrator' for r in user.roles)


def can_view(item,user=None):
    user=user or current_user
    if admin(user): return True
    if user.resident and item.resident_id==user.resident.id: return True
    return can_review(item,user)


def can_review(item,user=None):
    user=user or current_user
    if admin(user): return True
    official=any(r.name=='Barangay Official' for r in user.roles)
    from app.models import PersonnelProfile
    personnel=db.session.scalar(select(PersonnelProfile).where(PersonnelProfile.user_id==user.id))
    assigned=any(a.active and a.user_id==user.id for a in item.assignments)
    return official and (assigned or (not item.restricted and not (personnel and personnel.personnel_type=='Staff')))


def audit(item,action,actor,details):
    db.session.add(ComplaintAuditLog(complaint_id=item.id if item else None,actor_id=actor.id,action=action,details=details))


def notify(item,title,message,reviewers=False):
    if reviewers:
        roles=['System Administrator'] if item.restricted else ['System Administrator','Barangay Official']
        users=db.session.scalars(select(User).join(User.roles).where(Role.name.in_(roles),User.is_active.is_(True),User.status=='active').distinct()).all()
    else: users=[item.resident.user] if item.resident.user else []
    if reviewers:
        users.extend(a.user for a in item.assignments if a.active and a.user.is_active and a.user.status=='active')
        users=list({user.id:user for user in users}.values())
    for user in users:
        notification=Notification(user_id=user.id,title=title,message=message,status='active');db.session.add(notification);db.session.flush()
        db.session.add(ComplaintNotification(complaint_id=item.id,notification_id=notification.id))


def transition(item,status,actor,public,private=None):
    if status not in TRANSITIONS.get(item.status,set()): raise ValueError('This status transition is not permitted.')
    if not public or len(public)>3000: raise ValueError('Enter a resident-visible response of up to 3000 characters.')
    if status=='REFERRED_TO_EXTERNAL_AGENCY' and not any(r.transmitted_at for r in item.referrals): raise ValueError('Record a documented handoff before marking the complaint referred.')
    old=item.status;item.status=status
    if status=='RESOLVED': item.resolved_at=datetime.now(timezone.utc)
    if status=='REOPENED': item.resolved_at=None
    db.session.add(ComplaintStatusHistory(complaint_id=item.id,actor_id=actor.id,from_status=old,to_status=status,public_response=public,private_notes=private))
    audit(item,'STATUS_UPDATE',actor,f'{old} → {status}')
    notify(item,'Complaint status updated',f'{item.reference}: {status.replace("_"," ").title()}. Open My Complaints for the official response.')
