"""Private financial portfolios; never migrate legacy records automatically."""
from alembic import op
import sqlalchemy as sa

revision = '7e30ac981d42'
down_revision = '4ca719e03b62'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('workspace_portfolios',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('organization_id', sa.Integer(), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('name', sa.String(160), nullable=False),
        sa.Column('reference_date', sa.String(10), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_workspace_portfolios_organization_id', 'workspace_portfolios', ['organization_id'])
    op.create_table('workspace_portfolio_titles',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('portfolio_id', sa.Integer(), sa.ForeignKey('workspace_portfolios.id'), nullable=False),
        sa.Column('reference', sa.String(80), nullable=False),
        sa.Column('amount', sa.Numeric(16, 2), nullable=False),
        sa.Column('due_date', sa.String(10), nullable=False),
        sa.Column('paid_date', sa.String(10), nullable=True),
        sa.UniqueConstraint('portfolio_id', 'reference', name='uq_workspace_title_reference'),
        sa.CheckConstraint('amount > 0', name='ck_workspace_title_positive'))
    op.create_index('ix_workspace_portfolio_titles_portfolio_id', 'workspace_portfolio_titles', ['portfolio_id'])


def downgrade():
    bind = op.get_bind()
    for table in ('workspace_portfolio_titles', 'workspace_portfolios'):
        if bind.execute(sa.text(f'SELECT COUNT(*) FROM {table}')).scalar_one():
            raise RuntimeError('Private financial records exist; refusing destructive downgrade.')
    op.drop_table('workspace_portfolio_titles')
    op.drop_table('workspace_portfolios')
