"""rename profiles to users, add timestamps and profile image

Revision ID: f63aac5142d7
Revises: 5e849b7810f6
Create Date: 2026-08-15 20:15:18.123485

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f63aac5142d7'
down_revision: Union[str, Sequence[str], None] = '5e849b7810f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.rename_table('profiles', 'users')
    op.add_column('users', sa.Column('profile_image', sa.String(length=500), nullable=True))
    op.add_column(
        'users',
        sa.Column(
            'created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.add_column(
        'users',
        sa.Column(
            'updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('users', 'updated_at')
    op.drop_column('users', 'created_at')
    op.drop_column('users', 'profile_image')
    op.rename_table('users', 'profiles')
