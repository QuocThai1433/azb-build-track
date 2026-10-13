"""Readable project URLs: add project.slug (unique) and fill it from the project name.

Revision ID: 0004
Revises: 0003
"""
import re
import unicodedata

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def _slugify(name: str) -> str:
    text = unicodedata.normalize("NFKD", (name or "").replace("đ", "d").replace("Đ", "D"))
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).lower()
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")[:60].strip("-") or "du-an"


def upgrade() -> None:
    with op.batch_alter_table("project") as batch:
        batch.add_column(sa.Column("slug", sa.Text()))
    conn = op.get_bind()
    taken = {"new", "p", "projects", "static"}
    for pid, name in conn.execute(sa.text("SELECT id, name FROM project ORDER BY id")).fetchall():
        base = _slugify(name)
        slug, n = base, 2
        while slug in taken:
            slug, n = f"{base}-{n}", n + 1
        taken.add(slug)
        conn.execute(sa.text("UPDATE project SET slug = :s WHERE id = :i"), {"s": slug, "i": pid})
    op.create_index("uq_project_slug", "project", ["slug"], unique=True)


def downgrade() -> None:
    op.drop_index("uq_project_slug", table_name="project")
    with op.batch_alter_table("project") as batch:
        batch.drop_column("slug")
