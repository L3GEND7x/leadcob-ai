"""Private institutional contacts and suppression."""
from alembic import op
import sqlalchemy as sa

revision = 'ab83e14f095c'
down_revision = '36a847dc920e'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('workspace_contacts',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('organization_id', sa.Integer(), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('cnpj', sa.String(14), nullable=False),
        sa.Column('kind', sa.String(20), nullable=False),
        sa.Column('value', sa.String(500), nullable=False),
        sa.Column('source_url', sa.String(1000), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('organization_id', 'cnpj', 'kind', 'value', name='uq_workspace_contact'),
        sa.CheckConstraint("kind IN ('email', 'website', 'phone', 'whatsapp', 'linkedin', 'instagram', 'facebook')", name='ck_workspace_contact_kind'))
    op.create_index('ix_workspace_contacts_organization_id', 'workspace_contacts', ['organization_id'])
    op.create_table('workspace_suppressions',
        sa.Column('organization_id', sa.Integer(), sa.ForeignKey('organizations.id'), primary_key=True),
        sa.Column('cnpj', sa.String(14), primary_key=True),
        sa.Column('reason', sa.String(250), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))


def downgrade():
    for table in ('workspace_suppressions', 'workspace_contacts'):
        if op.get_bind().execute(sa.text(f'SELECT COUNT(*) FROM {table}')).scalar_one():
            raise RuntimeError('Private contacts or suppressions exist; refusing destructive downgrade.')
    op.drop_table('workspace_suppressions')
    op.drop_table('workspace_contacts')
