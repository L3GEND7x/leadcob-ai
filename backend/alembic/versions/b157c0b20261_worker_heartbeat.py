"""Persist contact discovery worker activity."""
from alembic import op
import sqlalchemy as sa

revision = "b157c0b20261"
down_revision = "d15e90c73b42"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("contact_worker_heartbeats",
        sa.Column("worker_id",sa.String(36),primary_key=True),
        sa.Column("observed_at",sa.DateTime(timezone=True),nullable=False),
        sa.Column("state",sa.String(20),nullable=False),
        sa.Column("attempts_processed",sa.Integer(),nullable=False))
    op.create_index("ix_contact_worker_heartbeats_observed_at","contact_worker_heartbeats",["observed_at"])


def downgrade():
    op.drop_index("ix_contact_worker_heartbeats_observed_at",table_name="contact_worker_heartbeats")
    op.drop_table("contact_worker_heartbeats")
