"""Private operational preferences."""
from alembic import op
import sqlalchemy as sa

revision = 'fcb28716a045'
down_revision = 'ab83e14f095c'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('workspace_settings',
        sa.Column('organization_id', sa.Integer(), sa.ForeignKey('organizations.id'), primary_key=True),
        sa.Column('timezone', sa.String(80), nullable=False),
        sa.Column('followup_days', sa.JSON(), nullable=False),
        sa.Column('default_page_size', sa.Integer(), nullable=False),
        sa.Column('updated_by', sa.Integer(), sa.ForeignKey('account_users.id'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint('default_page_size BETWEEN 10 AND 250', name='ck_workspace_page_size'))


def downgrade():
    if op.get_bind().execute(sa.text('SELECT COUNT(*) FROM workspace_settings')).scalar_one():
        raise RuntimeError('Private settings exist; refusing destructive downgrade.')
    op.drop_table('workspace_settings')
