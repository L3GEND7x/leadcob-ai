"""Append one independent sandbox observation per inbox event."""
from alembic import op
import sqlalchemy as sa

revision = "c93b71d50e24"
down_revision = "a62f08c913bd"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("asaas_sandbox_observations",
        sa.Column("event_id", sa.String(160), sa.ForeignKey("asaas_sandbox_events.event_id"), primary_key=True),
        sa.Column("invoice_id", sa.Integer(), sa.ForeignKey("commercial_invoices.id"), nullable=False),
        sa.Column("outcome", sa.String(32), nullable=False),
        sa.Column("provider_status", sa.String(80), nullable=False),
        sa.Column("gross_cents", sa.Integer(), nullable=True),
        sa.Column("net_cents", sa.Integer(), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False))


def downgrade():
    if op.get_bind().execute(sa.text("SELECT COUNT(*) FROM asaas_sandbox_observations")).scalar_one():
        raise RuntimeError("Observations exist; refusing destructive downgrade.")
    op.drop_table("asaas_sandbox_observations")
