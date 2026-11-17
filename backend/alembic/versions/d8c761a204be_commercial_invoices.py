"""Internal commercial receivables."""
from alembic import op
import sqlalchemy as sa

revision = 'd8c761a204be'
down_revision = 'b9c42d701ea6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('commercial_invoices',
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('organization_id',sa.Integer(),sa.ForeignKey('organizations.id'),nullable=False),
        sa.Column('plan_id',sa.Integer(),sa.ForeignKey('commercial_plans.id'),nullable=False),
        sa.Column('period_start',sa.String(10),nullable=False),
        sa.Column('period_end',sa.String(10),nullable=False),
        sa.Column('due_date',sa.String(10),nullable=False),
        sa.Column('amount_cents',sa.Integer(),nullable=False),
        sa.Column('status',sa.String(20),nullable=False),
        sa.Column('payment_reference',sa.String(160),nullable=True,unique=True),
        sa.Column('paid_at',sa.DateTime(timezone=True),nullable=True),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.UniqueConstraint('organization_id','period_start','period_end',name='uq_commercial_invoice_period'),
        sa.CheckConstraint('amount_cents > 0',name='ck_commercial_invoice_amount'),
        sa.CheckConstraint('period_end > period_start',name='ck_commercial_invoice_dates'),
        sa.CheckConstraint("status IN ('open','paid','void')",name='ck_commercial_invoice_status'))
    op.create_index('ix_commercial_invoices_organization_id','commercial_invoices',['organization_id'])


def downgrade():
    if op.get_bind().execute(sa.text('SELECT COUNT(*) FROM commercial_invoices')).scalar_one():
        raise RuntimeError('Receivables exist; refusing destructive downgrade.')
    op.drop_table('commercial_invoices')
