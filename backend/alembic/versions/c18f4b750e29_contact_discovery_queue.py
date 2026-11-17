"""Persistent owner contact discovery queue."""
from alembic import op
import sqlalchemy as sa

revision = 'c18f4b750e29'
down_revision = 'fcb28716a045'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('contact_discovery_jobs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.create_table('contact_discovery_items',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('job_id', sa.Integer(), sa.ForeignKey('contact_discovery_jobs.id'), nullable=False),
        sa.Column('company_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('claim_token', sa.String(36), nullable=True),
        sa.Column('lease_until', sa.DateTime(timezone=True), nullable=True),
        sa.Column('result', sa.JSON(), nullable=False),
        sa.UniqueConstraint('job_id', 'company_id', name='uq_contact_discovery_job_company'),
        sa.CheckConstraint("status IN ('queued','running','completed','failed','skipped')", name='ck_contact_discovery_status'))
    op.create_index('ix_contact_discovery_items_job_id', 'contact_discovery_items', ['job_id'])


def downgrade():
    if op.get_bind().execute(sa.text('SELECT COUNT(*) FROM contact_discovery_jobs')).scalar_one():
        raise RuntimeError('Discovery history exists; refusing destructive downgrade.')
    op.drop_table('contact_discovery_items')
    op.drop_table('contact_discovery_jobs')
