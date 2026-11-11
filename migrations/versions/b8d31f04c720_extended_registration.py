"""Extended resident registration profile and private verification images."""
from alembic import op
import sqlalchemy as sa
revision = 'b8d31f04c720'
down_revision = 'a7c20d9e6410'
branch_labels = None
depends_on = None
FIELDS = {'place_of_birth': 200, 'religion': 100, 'educational_attainment': 80, 'household_relationship': 80, 'house_no': 100, 'street_landmark': 155, 'residency_duration': 40, 'proof_of_residency_filename': 255, 'philsys_card_filename': 255, 'emergency_contact_name': 200, 'emergency_contact_relationship': 80, 'emergency_contact_number': 30}

def upgrade():
    with op.batch_alter_table('residents') as batch:
        for name, length in FIELDS.items():
            batch.add_column(sa.Column(name, sa.String(length), nullable=True))
        batch.add_column(sa.Column('special_categories', sa.JSON(), nullable=True))

def downgrade():
    with op.batch_alter_table('residents') as batch:
        batch.drop_column('special_categories')
        for name in reversed(FIELDS):
            batch.drop_column(name)
