"""Validated administration edits and safe record retirement."""
from datetime import date
from decimal import Decimal, InvalidOperation
import re
from flask import abort, request, render_template, redirect, url_for, flash
from sqlalchemy.exc import IntegrityError
from app.admin import admin_bp, admin_required, log_action
from app.extensions import db
from app.models import Role, Permission, DocumentType, FeeConfiguration, SystemSetting
from app.operations_common import text_field
from app.permissions import PERMISSIONS
CONFIG={
 'roles':(Role,'admin.roles',[('name','Role name'),('description','Description')]),
 'permissions':(Permission,'admin.permissions',[('resource','Resource'),('action','Action'),('description','Description')]),
 'document-types':(DocumentType,'admin.document_types',[('code','Code'),('name','Document name'),('base_fee','Base fee'),('description','Description'),('status','Status')]),
 'fees':(FeeConfiguration,'admin.fees',[('document_type_id','Document type'),('amount','Amount'),('effective_from','Effective from'),('notes','Notes'),('status','Status')])}
def permission_key(permission):
    return permission.resource if permission.action=='access' else f'{permission.resource}.{permission.action}'

def ensure_permission_catalog():
    existing={(p.resource,p.action) for p in db.session.scalars(db.select(Permission)).all()}
    for key in set().union(*PERMISSIONS.values()):
        resource,action=key.rsplit('.',1) if '.' in key else (key,'access')
        if (resource,action) not in existing:db.session.add(Permission(resource=resource,action=action,description='Application access: '+key))
    db.session.commit()

BUILTIN_PERMISSIONS=set().union(*PERMISSIONS.values())

CORE={'System Administrator','Barangay Official','Resident'}

def populate(item,entity,data):
    if entity not in CONFIG:abort(404)
    values={}
    for key,label in CONFIG[entity][2]:
        if key=='status':
            values[key]=data.get('status',getattr(item,'status',None) or 'active')
            if values[key] not in {'active','inactive'}:raise ValueError('Choose an active or inactive status.')
        elif key in {'base_fee','amount'}:
            try:value=Decimal(str(data.get(key,'')))
            except InvalidOperation:raise ValueError('Enter a valid amount.')
            if not value.is_finite() or value<0 or value>9999999999:raise ValueError('Amount must be non-negative and within the allowed range.')
            values[key]=value.quantize(Decimal('.01'))
        elif key=='effective_from':
            try:values[key]=date.fromisoformat(data.get(key,''))
            except ValueError:raise ValueError('Enter a valid effective date.')
        elif key=='document_type_id':
            try:identifier=int(data.get(key,''))
            except ValueError:raise ValueError('Select a document type.')
            document=db.session.get(DocumentType,identifier)
            if not document or document.status!='active':raise ValueError('Select an active document type.')
            values[key]=identifier
        else:values[key]=text_field(data,key,150 if key=='name' and entity=='document-types' else 80 if key=='name' else 255,key not in {'description','notes'}) or None
    if entity=='permissions':
        if item.id and permission_key(item) in BUILTIN_PERMISSIONS and (values['resource']!=item.resource or values['action']!=item.action):raise ValueError('Built-in permission keys cannot be changed. Edit the description or change role access.')
        for key,limit in [('resource',100),('action',50)]:
            if not re.fullmatch(r'[a-z][a-z0-9_.-]*',values[key]) or len(values[key])>limit:raise ValueError('Use lowercase permission keys, such as documents and review.')
    if entity=='document-types':
        values['code']=values['code'].upper()
        if not re.fullmatch(r'[A-Z0-9_-]{1,30}',values['code']):raise ValueError('Use a document code of up to 30 letters, digits, underscores or hyphens.')
        if item.id and item.code!=values['code']:raise ValueError('Document codes cannot be changed after creation.')
    if entity=='roles' and item.id and item.name in CORE and values['name']!=item.name:raise ValueError('Built-in role names cannot be changed.')
    for key,value in values.items():setattr(item,key,value)

@admin_bp.route('/<entity>/<int:item_id>/edit',methods=['GET','POST'])
@admin_required
def manage_edit(entity,item_id):
    if entity not in CONFIG:abort(404)
    model,back,fields=CONFIG[entity];item=db.get_or_404(model,item_id)
    if request.method=='POST':
        try:
            populate(item,entity,request.form);log_action('update',model.__name__,item.id,'Administration record updated');db.session.commit();flash('Changes saved.','success');return redirect(url_for(back))
        except (ValueError,IntegrityError) as error:
            db.session.rollback();flash(str(error) if isinstance(error,ValueError) else 'This record conflicts with an existing entry.','danger')
    return render_template('admin/manage_edit.html',entity=entity,item=item,fields=fields,back=back,document_types=db.session.scalars(db.select(DocumentType).where(DocumentType.status=='active').order_by(DocumentType.name)).all())

@admin_bp.post('/<entity>/<int:item_id>/delete')
@admin_required
def manage_delete(entity,item_id):
    if entity not in CONFIG:abort(404)
    model,back,_=CONFIG[entity];item=db.get_or_404(model,item_id)
    try:
        if entity=='roles' and (item.name in CORE or item.users):raise ValueError('Built-in roles and roles assigned to users cannot be deleted.')
        if entity=='permissions' and permission_key(item) in BUILTIN_PERMISSIONS:raise ValueError('Built-in permissions are protected. Change the role access instead.')
        if entity=='permissions' and item.roles:raise ValueError('Remove this permission from its roles before deleting it.')
        if entity in {'document-types','fees'}:item.status='inactive'
        else:db.session.delete(item)
        log_action('retire' if entity in {'document-types','fees'} else 'delete',model.__name__,item_id,'Administration record retired or removed');db.session.commit();flash('Record archived.' if entity in {'document-types','fees'} else 'Record deleted.','success')
    except (ValueError,IntegrityError) as error:
        db.session.rollback();flash(str(error) if isinstance(error,ValueError) else 'This record is still referenced and cannot be deleted.','danger')
    return redirect(url_for(back))

@admin_bp.route('/roles/<int:role_id>/access',methods=['GET','POST'])
@admin_required
def role_access(role_id):
    role=db.get_or_404(Role,role_id)
    baseline=PERMISSIONS.get(role.name,set())
    if request.method=='POST':
        try:
            if role.name=='System Administrator':raise ValueError('Administrator access is protected to prevent lockout.')
            raw=request.form.getlist('permission_id')
            if any(not value.isdigit() for value in raw):raise ValueError('Select valid permissions.')
            selected=db.session.scalars(db.select(Permission).where(Permission.id.in_([int(v) for v in raw]))).all()
            if len(selected)!=len(set(raw)):raise ValueError('One or more permissions no longer exist.')
            keys={permission_key(p) for p in selected}
            if role.name=='Resident' and not keys<=baseline:raise ValueError('Resident roles can only use permissions for their own records.')
            role.permissions=selected
            key=f'role_permissions_override_{role.id}';setting=db.session.scalar(db.select(SystemSetting).where(SystemSetting.setting_key==key))
            if not setting:setting=SystemSetting(setting_key=key,setting_value='yes');db.session.add(setting)
            setting.setting_value='yes';log_action('access_update','Role',role.id,', '.join(sorted(keys)));db.session.commit();flash('Role access updated.','success');return redirect(url_for('admin.roles'))
        except ValueError as error:db.session.rollback();flash(str(error),'danger')
    permissions=db.session.scalars(db.select(Permission).order_by(Permission.resource,Permission.action)).all()
    override=db.session.scalar(db.select(SystemSetting).where(SystemSetting.setting_key==f'role_permissions_override_{role.id}'))
    selected={p.id for p in role.permissions} if override else {p.id for p in permissions if permission_key(p) in baseline} | {p.id for p in role.permissions}
    return render_template('admin/role_access.html',role=role,permissions=permissions,selected=selected)
