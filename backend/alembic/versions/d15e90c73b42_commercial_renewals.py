"""Record consumption of a paid invoice for subscription renewal."""
from alembic import op
import sqlalchemy as sa

revision = "d15e90c73b42"
down_revision = "c93b71d50e24"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("commercial_renewals",
        sa.Column("invoice_id", sa.Integer(), sa.ForeignKey("commercial_invoices.id"), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("previous_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("new_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("new_end > previous_end"))


def downgrade():
    if op.get_bind().execute(sa.text("SELECT COUNT(*) FROM commercial_renewals")).scalar_one():
        raise RuntimeError("Renewal history exists; refusing destructive downgrade.")
    op.drop_table("commercial_renewals")
