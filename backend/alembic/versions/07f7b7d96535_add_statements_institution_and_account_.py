"""add statements institution and account_type_tags overrides

Revision ID: 07f7b7d96535
Revises: cf872bc680da
Create Date: 2026-08-26 10:08:48.040297

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '07f7b7d96535'
down_revision: Union[str, Sequence[str], None] = 'cf872bc680da'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('statements', sa.Column('institution', sa.String(length=255), nullable=True))
    op.add_column(
        'statements',
        sa.Column('account_type_tags', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('statements', 'account_type_tags')
    op.drop_column('statements', 'institution')
