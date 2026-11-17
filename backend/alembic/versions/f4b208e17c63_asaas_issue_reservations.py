"""Durable one-attempt sandbox issuance reservation."""
from alembic import op
import sqlalchemy as sa
revision = "f4b208e17c63"
down_revision = "e7a109c42b56"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("asaas_sandbox_issue_reservations",
        sa.Column("invoice_id", sa.Integer(), sa.ForeignKey("commercial_invoices.id"), primary_key=True),
        sa.Column("customer_id", sa.String(120), nullable=False),
        sa.Column("external_reference", sa.String(160), nullable=False, unique=True),
        sa.Column("billing_type", sa.String(10), nullable=False),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("due_date", sa.String(10), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("billing_type IN ('PIX','BOLETO')"),
        sa.CheckConstraint("amount_cents > 0"))


def downgrade():
    if op.get_bind().execute(sa.text("SELECT COUNT(*) FROM asaas_sandbox_issue_reservations")).scalar_one():
        raise RuntimeError("Issuance history exists; refusing destructive downgrade.")
    op.drop_table("asaas_sandbox_issue_reservations")
