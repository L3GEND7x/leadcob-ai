"""Private workspace leads, additive migration."""
from alembic import op
import sqlalchemy as sa

revision = '4ca719e03b62'
down_revision = '9af31c620e41'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('workspace_leads',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('organization_id', sa.Integer(), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('name', sa.String(220), nullable=False),
        sa.Column('notes', sa.Text(), nullable=False),
        sa.Column('stage', sa.String(30), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("stage IN ('identified', 'contacted', 'negotiation', 'won', 'lost')", name='ck_workspace_lead_stage'))
    op.create_index('ix_workspace_leads_organization_id', 'workspace_leads', ['organization_id'])


def downgrade():
    if op.get_bind().execute(sa.text('SELECT COUNT(*) FROM workspace_leads')).scalar_one():
        raise RuntimeError('Private leads exist; refusing destructive downgrade.')
    op.drop_table('workspace_leads')
