"""Commercial plan catalog."""
from alembic import op
import sqlalchemy as sa

revision = 'ea73d619b205'
down_revision = 'c18f4b750e29'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('commercial_plans',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('code', sa.String(80), nullable=False, unique=True),
        sa.Column('name', sa.String(160), nullable=False),
        sa.Column('monthly_price_cents', sa.Integer(), nullable=False),
        sa.Column('max_members', sa.Integer(), nullable=False),
        sa.Column('max_leads', sa.Integer(), nullable=False),
        sa.Column('max_contacts', sa.Integer(), nullable=False),
        sa.Column('max_tasks', sa.Integer(), nullable=False),
        sa.Column('max_portfolios', sa.Integer(), nullable=False),
        sa.Column('max_titles', sa.Integer(), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint('monthly_price_cents >= 0', name='ck_commercial_plan_price'),
        sa.CheckConstraint('max_members >= 1 AND max_leads >= 0 AND max_contacts >= 0 AND max_tasks >= 0 AND max_portfolios >= 0 AND max_titles >= 0', name='ck_commercial_plan_limits'))


def downgrade():
    if op.get_bind().execute(sa.text('SELECT COUNT(*) FROM commercial_plans')).scalar_one():
        raise RuntimeError('Commercial plans exist; refusing destructive downgrade.')
    op.drop_table('commercial_plans')
