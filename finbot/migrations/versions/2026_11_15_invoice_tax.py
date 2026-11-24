"""Bind the simulated tax calculation to invoice data."""
from alembic import op
import sqlalchemy as sa

revision = "32f07c8a645b"
down_revision = "a3f7c2d91e04"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("invoices", sa.Column("tax_category", sa.String(32), nullable=False, server_default="goods"))
    op.add_column("invoices", sa.Column("tax_jurisdiction", sa.String(32), nullable=False, server_default=""))


def downgrade():
    with op.batch_alter_table("invoices") as batch:
        batch.drop_column("tax_jurisdiction")
        batch.drop_column("tax_category")
