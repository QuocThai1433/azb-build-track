"""Remember column / sheet choices made in the Excel import preview.

Revision ID: 0003
Revises: 0002
"""
import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "import_aliases",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("entity", sa.Text(), nullable=False),
        sa.Column("text_norm", sa.Text(), nullable=False),
        sa.Column("text_shown", sa.Text()),
        sa.Column("field", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.Text()),
        sa.UniqueConstraint("kind", "entity", "text_norm", name="uq_import_alias"),
        sqlite_autoincrement=True,
    )


def downgrade() -> None:
    op.drop_table("import_aliases")
