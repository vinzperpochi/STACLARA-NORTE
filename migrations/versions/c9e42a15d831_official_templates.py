"""Original certificate templates, verified approvals and atomic numbering."""
from alembic import op
import sqlalchemy as sa
revision = 'c9e42a15d831'
down_revision = 'b8d31f04c720'
branch_labels = depends_on = None

def upgrade():
    timestamps=[sa.Column('id',sa.Integer(),primary_key=True),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now())]
    op.create_table('document_signatories',*timestamps,sa.Column('status',sa.String(30),nullable=False),sa.Column('full_name',sa.String(200),nullable=False),sa.Column('designation',sa.String(100),nullable=False),sa.Column('authorized_by_id',sa.Integer(),sa.ForeignKey('users.id',ondelete='RESTRICT'),nullable=False),sa.Column('effective_from',sa.Date(),nullable=False),sa.Column('effective_until',sa.Date()))
    op.create_table('document_sequences',sa.Column('id',sa.Integer(),primary_key=True),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),sa.Column('template_code',sa.String(10),nullable=False),sa.Column('year',sa.Integer(),nullable=False),sa.Column('last_number',sa.Integer(),nullable=False),sa.UniqueConstraint('template_code','year',name='uq_document_sequence_year'))
    with op.batch_alter_table('document_types') as b: b.add_column(sa.Column('template_code',sa.String(10)))
    with op.batch_alter_table('requests') as b:
        b.add_column(sa.Column('additional_data',sa.JSON()))
        b.add_column(sa.Column('verification_notes',sa.Text()))
        b.add_column(sa.Column('verification_digest',sa.String(64)))
        for name in ['verified_at','approved_at']: b.add_column(sa.Column(name,sa.DateTime(timezone=True)))
        for name in ['verified_by_id','approved_by_id']:
            b.add_column(sa.Column(name,sa.Integer()))
            b.create_foreign_key('fk_requests_'+name,'users',[name],['id'],ondelete='SET NULL')
        b.add_column(sa.Column('signatory_id',sa.Integer()))
        b.create_foreign_key('fk_requests_signatory_id','document_signatories',['signatory_id'],['id'],ondelete='RESTRICT')
    with op.batch_alter_table('issued_documents') as b:
        b.add_column(sa.Column('verification_token',sa.String(64)))
        b.create_unique_constraint('uq_issued_documents_verification_token',['verification_token'])
        b.add_column(sa.Column('snapshot',sa.JSON()))
        b.add_column(sa.Column('pdf_filename',sa.String(255)))
        b.add_column(sa.Column('revoked_at',sa.DateTime(timezone=True)))
        b.add_column(sa.Column('revocation_reason',sa.Text()))
    codes={'CERTIFICATE_INDIGENCY':'SCN-IND','CERTIFICATE_RESIDENCY':'SCN-RSD','BUSINESS_CLEARANCE':'SCN-BIZ','BARANGAY_CLEARANCE':'SCN-CLR','CERTIFICATE_GOOD_MORAL':'SCN-GMC','SOLO_PARENT_ENDORSEMENT':'SCN-SPE','FIRST_TIME_JOBSEEKER':'SCN-FTJ'}
    for old,new in codes.items():
        op.execute(sa.text('UPDATE document_types SET template_code=:new WHERE code=:old').bindparams(old=old,new=new))

def downgrade():
    with op.batch_alter_table('issued_documents') as b:
        b.drop_constraint('uq_issued_documents_verification_token',type_='unique')
        for n in ['revocation_reason','revoked_at','pdf_filename','snapshot','verification_token']: b.drop_column(n)
    with op.batch_alter_table('requests') as b:
        for n in ['signatory_id','approved_by_id','verified_by_id']: b.drop_constraint('fk_requests_'+n,type_='foreignkey'); b.drop_column(n)
        for n in ['approved_at','verified_at','verification_digest','verification_notes','additional_data']: b.drop_column(n)
    with op.batch_alter_table('document_types') as b: b.drop_column('template_code')
    op.drop_table('document_sequences'); op.drop_table('document_signatories')
