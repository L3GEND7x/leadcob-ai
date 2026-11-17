"""Durable sandbox webhook inbox, isolated from financial settlement."""
from alembic import op
import sqlalchemy as sa

revision = "a62f08c913bd"
down_revision = "f4b208e17c63"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("asaas_sandbox_events",
        sa.Column("event_id", sa.String(160), primary_key=True),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("payment_id", sa.String(120), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_asaas_sandbox_events_payment", "asaas_sandbox_events", ["payment_id"])


def downgrade():
    if op.get_bind().execute(sa.text("SELECT COUNT(*) FROM asaas_sandbox_events")).scalar_one():
        raise RuntimeError("Webhook history exists; refusing destructive downgrade.")
    op.drop_table("asaas_sandbox_events")
