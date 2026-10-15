"""Sign-in and roles, project membership, an append-only audit log, construction status of a project and
approval of costs.

* users / project_members: who may sign in and which projects a staff member (nhan_vien) works on.
* audit_logs: one row per change. Rows are never updated or deleted (two triggers refuse it), and they
  keep no foreign key so the history of a deleted project or user stays.
* project.construction_status: dang_thi_cong / tam_dung / hoan_thanh. Archiving (status) is unchanged.
* costs.approval_status: costs that exist before this version count as approved.
* Project slugs that now clash with a new top-level URL (login, api, ...) get a "-2" suffix.

Revision ID: 0005
Revises: 0004
"""
import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

NEW_RESERVED = ("login", "logout", "account", "users", "audit-logs", "api")


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("username", sa.Text(), nullable=False, unique=True),
        sa.Column("full_name", sa.Text(), nullable=False, server_default=""),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False, server_default="nhan_vien"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("must_change_password", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.Text()),
        sa.Column("last_login_at", sa.Text()),
        sqlite_autoincrement=True,
    )
    op.create_table(
        "project_members",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE",
                                                         name="fk_project_members_user_id"), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("project.id", ondelete="CASCADE",
                                                            name="fk_project_members_project_id"), primary_key=True),
        sa.Column("role_in_project", sa.Text(), nullable=False, server_default="Thành viên"),
    )
    op.create_index("ix_project_members_project_id", "project_members", ["project_id"])
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer()),
        sa.Column("username", sa.Text()),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("entity_type", sa.Text()),
        sa.Column("entity_id", sa.Integer()),
        sa.Column("project_id", sa.Integer()),
        sa.Column("old_value", sa.Text()),
        sa.Column("new_value", sa.Text()),
        sa.Column("ip_address", sa.Text()),
        sa.Column("user_agent", sa.Text()),
        sa.Column("created_at", sa.Text(), nullable=False),
        sqlite_autoincrement=True,
    )
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])
    op.create_index("ix_audit_logs_project_id", "audit_logs", ["project_id"])
    op.execute("CREATE TRIGGER audit_logs_no_update BEFORE UPDATE ON audit_logs "
               "BEGIN SELECT RAISE(ABORT, 'audit_logs is append-only'); END")
    op.execute("CREATE TRIGGER audit_logs_no_delete BEFORE DELETE ON audit_logs "
               "BEGIN SELECT RAISE(ABORT, 'audit_logs is append-only'); END")

    with op.batch_alter_table("project") as batch:
        batch.add_column(sa.Column("construction_status", sa.Text(), nullable=False, server_default="dang_thi_cong"))
    with op.batch_alter_table("costs") as batch:
        batch.add_column(sa.Column("approval_status", sa.Text(), nullable=False, server_default="da_duyet"))
        batch.add_column(sa.Column("approved_by", sa.Text()))
        batch.add_column(sa.Column("approved_at", sa.Text()))
        batch.add_column(sa.Column("approval_note", sa.Text()))

    conn = op.get_bind()
    taken = set(conn.execute(sa.text("SELECT slug FROM project WHERE slug IS NOT NULL")).scalars())
    for slug in NEW_RESERVED:
        if slug in taken:
            new, n = f"{slug}-2", 3
            while new in taken:
                new, n = f"{slug}-{n}", n + 1
            taken.add(new)
            conn.execute(sa.text("UPDATE project SET slug = :new WHERE slug = :old"), {"new": new, "old": slug})


def downgrade() -> None:
    with op.batch_alter_table("costs") as batch:
        for column in ("approval_note", "approved_at", "approved_by", "approval_status"):
            batch.drop_column(column)
    with op.batch_alter_table("project") as batch:
        batch.drop_column("construction_status")
    op.execute("DROP TRIGGER IF EXISTS audit_logs_no_delete")
    op.execute("DROP TRIGGER IF EXISTS audit_logs_no_update")
    op.drop_table("audit_logs")
    op.drop_table("project_members")
    op.drop_table("users")
