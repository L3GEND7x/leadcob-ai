"""Private workspace tasks."""
from alembic import op
import sqlalchemy as sa

revision = '36a847dc920e'
down_revision = '7e30ac981d42'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('workspace_tasks',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('organization_id', sa.Integer(), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('title', sa.String(250), nullable=False),
        sa.Column('due_date', sa.String(10), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_workspace_tasks_organization_id', 'workspace_tasks', ['organization_id'])


def downgrade():
    if op.get_bind().execute(sa.text('SELECT COUNT(*) FROM workspace_tasks')).scalar_one():
        raise RuntimeError('Private tasks exist; refusing destructive downgrade.')
    op.drop_table('workspace_tasks')
