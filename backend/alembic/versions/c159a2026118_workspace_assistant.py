"""Private workspace assistant ledger."""
from alembic import op
import sqlalchemy as sa

revision = "c159a2026118"
down_revision = "b157c0b20261"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("workspace_assistant_exchanges",
        sa.Column("id",sa.String(36),primary_key=True),
        sa.Column("organization_id",sa.Integer(),sa.ForeignKey("organizations.id"),nullable=False),
        sa.Column("user_id",sa.Integer(),sa.ForeignKey("account_users.id"),nullable=False),
        sa.Column("month",sa.String(7),nullable=False),
        sa.Column("prompt",sa.Text(),nullable=False),
        sa.Column("answer",sa.Text(),nullable=True),
        sa.Column("status",sa.String(20),nullable=False),
        sa.Column("reserved_micro_usd",sa.Integer(),nullable=False),
        sa.Column("charged_micro_usd",sa.Integer(),nullable=False),
        sa.Column("created_at",sa.DateTime(timezone=True),nullable=False))
    op.create_index("ix_workspace_assistant_exchanges_organization_id","workspace_assistant_exchanges",["organization_id"])
    op.create_index("ix_workspace_assistant_exchanges_month","workspace_assistant_exchanges",["month"])
    op.create_table("workspace_assistant_budget_locks",sa.Column("id",sa.Integer(),primary_key=True))
    op.execute("INSERT INTO workspace_assistant_budget_locks (id) VALUES (1)")

def downgrade():
    if op.get_bind().execute(sa.text("SELECT COUNT(*) FROM workspace_assistant_exchanges")).scalar_one():
        raise RuntimeError("Assistant history exists; refusing destructive downgrade.")
    op.drop_table("workspace_assistant_budget_locks")
    op.drop_index("ix_workspace_assistant_exchanges_month",table_name="workspace_assistant_exchanges")
    op.drop_index("ix_workspace_assistant_exchanges_organization_id",table_name="workspace_assistant_exchanges")
    op.drop_table("workspace_assistant_exchanges")
