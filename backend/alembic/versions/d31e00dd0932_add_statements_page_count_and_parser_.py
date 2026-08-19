"""add statements page_count and parser_version

Revision ID: d31e00dd0932
Revises: cac4cf1ab7e9
Create Date: 2026-08-18 22:22:45.135638

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd31e00dd0932'
down_revision: Union[str, Sequence[str], None] = 'cac4cf1ab7e9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('statements', sa.Column('page_count', sa.Integer(), nullable=True))
    op.add_column('statements', sa.Column('parser_version', sa.String(length=20), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('statements', 'parser_version')
    op.drop_column('statements', 'page_count')
