"""add api_key_hash and prefix columns, make api_key nullable

Revision ID: a1b2c3d4e5f6
Revises: f4f601938b39
Create Date: 2026-02-18 12:00:00.000000

"""

import hashlib
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "f4f601938b39"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Step 1: Add new columns as nullable first (data migration needs to populate them)
    op.add_column(
        "projects",
        sa.Column("api_key_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "projects",
        sa.Column("api_key_prefix", sa.String(length=10), nullable=True),
    )

    # Step 2: Data migration — hash existing plaintext API keys
    conn = op.get_bind()
    projects = conn.execute(sa.text("SELECT id, api_key FROM projects WHERE api_key IS NOT NULL"))
    for row in projects:
        key_hash = hashlib.sha256(row.api_key.encode()).hexdigest()
        key_prefix = row.api_key[:10]
        conn.execute(
            sa.text(
                "UPDATE projects SET api_key_hash = :hash, api_key_prefix = :prefix WHERE id = :id"
            ),
            {"hash": key_hash, "prefix": key_prefix, "id": row.id},
        )

    # Step 3: Make new columns NOT NULL after populating data
    with op.batch_alter_table("projects") as batch_op:
        batch_op.alter_column("api_key_hash", nullable=False)
        batch_op.alter_column("api_key_prefix", nullable=False)
        # Make api_key nullable (legacy — will be removed in future migration)
        batch_op.alter_column("api_key", nullable=True)

    # Step 4: Add indexes and unique constraint on api_key_hash
    op.create_index(op.f("ix_projects_api_key_hash"), "projects", ["api_key_hash"], unique=True)


def downgrade() -> None:
    # Remove index
    op.drop_index(op.f("ix_projects_api_key_hash"), table_name="projects")

    # Restore api_key to NOT NULL, drop new columns
    with op.batch_alter_table("projects") as batch_op:
        batch_op.alter_column("api_key", nullable=False)
        batch_op.drop_column("api_key_prefix")
        batch_op.drop_column("api_key_hash")
