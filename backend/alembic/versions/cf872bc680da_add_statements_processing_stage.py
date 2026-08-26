"""add statements processing stage

Revision ID: cf872bc680da
Revises: c9d0e1f2a3b4
Create Date: 2026-08-25 19:25:18.671666

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cf872bc680da'
down_revision: Union[str, Sequence[str], None] = 'c9d0e1f2a3b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'statements',
        sa.Column('processing_stage', sa.String(length=30), nullable=True),
    )
    op.add_column(
        'statements',
        sa.Column('processing_detail', sa.String(length=100), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('statements', 'processing_detail')
    op.drop_column('statements', 'processing_stage')
