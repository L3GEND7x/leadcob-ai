"""Commercial identity foundation; legacy data remains unchanged."""
from alembic import op
import sqlalchemy as sa

revision: str = '9af31c620e41'
down_revision = '2b3f641847d9'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('organizations',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(160), nullable=False),
        sa.Column('slug', sa.String(80), nullable=False, unique=True),
        sa.Column('active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.create_table('account_users',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('email', sa.String(254), nullable=False, unique=True),
        sa.Column('password_hash', sa.String(200), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.create_table('memberships',
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('account_users.id'), primary_key=True),
        sa.Column('organization_id', sa.Integer(), sa.ForeignKey('organizations.id'), primary_key=True),
        sa.Column('role', sa.String(20), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False),
        sa.CheckConstraint("role IN ('admin', 'member', 'viewer')", name='ck_membership_role'))
    op.create_table('account_sessions',
        sa.Column('token_hash', sa.String(64), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('account_users.id'), nullable=False),
        sa.Column('organization_id', sa.Integer(), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('csrf_token', sa.String(80), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_account_sessions_user_id', 'account_sessions', ['user_id'])
    op.create_index('ix_account_sessions_expires_at', 'account_sessions', ['expires_at'])


def downgrade():
    # Refuse destructive rollback after commercial identity records exist.
    bind = op.get_bind()
    for table in ('account_sessions', 'memberships', 'account_users', 'organizations'):
        if bind.execute(sa.text(f'SELECT COUNT(*) FROM {table}')).scalar_one():
            raise RuntimeError('Commercial records exist; use a reviewed forward migration.')
    for table in ('account_sessions', 'memberships', 'account_users', 'organizations'):
        op.drop_table(table)
