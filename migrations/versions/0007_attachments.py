"""Attachments: photos and documents on diary entries, HSSE records and risks.

Revision ID: 0007
Revises: 0006
"""
import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "attachments",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("project.id", ondelete="CASCADE",
                                                            name="fk_attachments_project_id"), nullable=False),
        sa.Column("entity_type", sa.Text(), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("stored_name", sa.Text(), nullable=False),
        sa.Column("content_type", sa.Text()),
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("uploaded_by", sa.Text()),
        sa.Column("uploaded_at", sa.Text()),
        sqlite_autoincrement=True,
    )
    op.create_index("ix_attachments_project_id", "attachments", ["project_id"])
    op.create_index("idx_attachments_entity", "attachments", ["entity_type", "entity_id"])


def downgrade() -> None:
    op.drop_table("attachments")
