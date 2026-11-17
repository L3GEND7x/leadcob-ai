"""Commercial subscriptions and approved initial catalog."""
from datetime import datetime, timezone
from alembic import op
import sqlalchemy as sa

revision = 'b9c42d701ea6'
down_revision = 'ea73d619b205'
branch_labels = None
depends_on = None

PLANS = [
    ('essential-v1','Essential',2700,1,500,1000,100,2,1000),
    ('professional-v1','Professional',11700,5,5000,10000,1000,10,20000),
    ('enterprise-v1','Enterprise',39700,20,25000,50000,10000,50,100000),
]
KEYS = ('code','name','monthly_price_cents','max_members','max_leads','max_contacts',
        'max_tasks','max_portfolios','max_titles')


def upgrade():
    op.create_table('commercial_subscriptions',
        sa.Column('organization_id',sa.Integer(),sa.ForeignKey('organizations.id'),primary_key=True),
        sa.Column('plan_id',sa.Integer(),sa.ForeignKey('commercial_plans.id'),nullable=False),
        sa.Column('starts_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('ends_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('status',sa.String(20),nullable=False),
        sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False),
        sa.CheckConstraint('ends_at > starts_at',name='ck_subscription_period'),
        sa.CheckConstraint("status IN ('active','cancelled')",name='ck_subscription_status'))
    op.create_index('ix_commercial_subscriptions_plan_id','commercial_subscriptions',['plan_id'])
    plans=sa.table('commercial_plans',
                   *[sa.column(k,sa.String() if k in ('code','name') else sa.Integer()) for k in KEYS],
                   sa.column('active',sa.Boolean()),sa.column('created_at',sa.DateTime(timezone=True)))
    conn=op.get_bind()
    for values in PLANS:
        existing=conn.execute(sa.select(plans.c.code).where(plans.c.code==values[0])).scalar_one_or_none()
        if existing is None:
            conn.execute(plans.insert().values(**dict(zip(KEYS,values)),active=False,
                                               created_at=datetime.now(timezone.utc)))


def downgrade():
    if op.get_bind().execute(sa.text('SELECT COUNT(*) FROM commercial_subscriptions')).scalar_one():
        raise RuntimeError('Subscriptions exist; refusing destructive downgrade.')
    op.drop_table('commercial_subscriptions')
    # Preserve catalog and any administrative changes to plans.
