"""Persist sandbox-only provider identities without settling receivables."""
from alembic import op
import sqlalchemy as sa

revision = "e7a109c42b56"
down_revision = "d8c761a204be"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "asaas_sandbox_customers",
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), primary_key=True),
        sa.Column("customer_id", sa.String(120), nullable=False, unique=True),
    )
    op.create_table(
        "asaas_sandbox_payments",
        sa.Column("invoice_id", sa.Integer(), sa.ForeignKey("commercial_invoices.id"), primary_key=True),
        sa.Column("payment_id", sa.String(120), nullable=False, unique=True),
        sa.Column("external_reference", sa.String(160), nullable=False, unique=True),
    )


def downgrade():
    for table in ("asaas_sandbox_payments", "asaas_sandbox_customers"):
        if op.get_bind().execute(sa.text(f"SELECT COUNT(*) FROM {table}")).scalar_one():
            raise RuntimeError("Sandbox bindings exist; refusing destructive downgrade.")
    op.drop_table("asaas_sandbox_payments")
    op.drop_table("asaas_sandbox_customers")
