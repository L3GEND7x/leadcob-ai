"""Registry abuse controls and private CNPJ import ledger."""
from alembic import op
import sqlalchemy as sa

revision="d161a20261123"
down_revision="c159a2026118"
branch_labels=None
depends_on=None

def upgrade():
    op.create_table("workspace_registry_query_quotas",
        sa.Column("organization_id",sa.Integer(),sa.ForeignKey("organizations.id"),primary_key=True),
        sa.Column("hour_bucket",sa.String(13),primary_key=True),
        sa.Column("requests",sa.Integer(),nullable=False),
        sa.CheckConstraint("requests >= 0",name="ck_registry_query_requests"))
    op.create_table("workspace_prospect_imports",
        sa.Column("organization_id",sa.Integer(),sa.ForeignKey("organizations.id"),primary_key=True),
        sa.Column("cnpj",sa.String(14),primary_key=True),
        sa.Column("lead_id",sa.Integer(),sa.ForeignKey("workspace_leads.id"),nullable=False,unique=True),
        sa.Column("created_at",sa.DateTime(timezone=True),nullable=False))

def downgrade():
    if op.get_bind().execute(sa.text("SELECT COUNT(*) FROM workspace_prospect_imports")).scalar_one():
        raise RuntimeError("Prospect import history exists; refusing destructive downgrade.")
    op.drop_table("workspace_prospect_imports")
    op.drop_table("workspace_registry_query_quotas")
