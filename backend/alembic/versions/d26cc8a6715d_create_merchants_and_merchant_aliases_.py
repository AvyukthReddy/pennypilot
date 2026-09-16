"""create merchants and merchant_aliases tables

Revision ID: d26cc8a6715d
Revises: 25d591fb73a0
Create Date: 2026-09-16 18:18:58.304057

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd26cc8a6715d'
down_revision: Union[str, Sequence[str], None] = '25d591fb73a0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'merchants',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('default_category_id', sa.UUID(), nullable=True),
        sa.Column('default_subcategory_id', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['default_category_id'], ['categories.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['default_subcategory_id'], ['categories.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_merchants_name'), 'merchants', ['name'], unique=True)

    op.create_table(
        'merchant_aliases',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('merchant_id', sa.UUID(), nullable=False),
        sa.Column('alias', sa.String(length=255), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['merchant_id'], ['merchants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_merchant_aliases_merchant_id'), 'merchant_aliases', ['merchant_id'], unique=False)
    op.create_index(op.f('ix_merchant_aliases_alias'), 'merchant_aliases', ['alias'], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_merchant_aliases_alias'), table_name='merchant_aliases')
    op.drop_index(op.f('ix_merchant_aliases_merchant_id'), table_name='merchant_aliases')
    op.drop_table('merchant_aliases')
    op.drop_index(op.f('ix_merchants_name'), table_name='merchants')
    op.drop_table('merchants')
