"""widen comment ordering index to include id

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-06

"""

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Include id so comment ordering has a stable, index-backed tiebreaker
    # when two comments share a created_at (matches ix_tasks_project_created).
    op.drop_index("ix_comments_task_created", table_name="comments")
    op.create_index("ix_comments_task_created", "comments", ["task_id", "created_at", "id"])


def downgrade() -> None:
    op.drop_index("ix_comments_task_created", table_name="comments")
    op.create_index("ix_comments_task_created", "comments", ["task_id", "created_at"])
