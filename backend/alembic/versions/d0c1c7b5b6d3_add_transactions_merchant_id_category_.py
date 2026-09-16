"""add transactions merchant_id category_id and merchant_category_preferences table

Revision ID: d0c1c7b5b6d3
Revises: d26cc8a6715d
Create Date: 2026-09-16 18:40:15.937616

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd0c1c7b5b6d3'
down_revision: Union[str, Sequence[str], None] = 'd26cc8a6715d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('transactions', sa.Column('merchant_id', sa.UUID(), nullable=True))
    op.create_foreign_key(
        'fk_transactions_merchant_id_merchants', 'transactions', 'merchants',
        ['merchant_id'], ['id'], ondelete='SET NULL',
    )
    op.create_index(op.f('ix_transactions_merchant_id'), 'transactions', ['merchant_id'], unique=False)

    op.add_column('transactions', sa.Column('category_id', sa.UUID(), nullable=True))
    op.create_foreign_key(
        'fk_transactions_category_id_categories', 'transactions', 'categories',
        ['category_id'], ['id'], ondelete='SET NULL',
    )
    op.create_index(op.f('ix_transactions_category_id'), 'transactions', ['category_id'], unique=False)

    op.create_table(
        'merchant_category_preferences',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('merchant_id', sa.UUID(), nullable=False),
        sa.Column('category_id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['auth.users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['merchant_id'], ['merchants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['category_id'], ['categories.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_merchant_category_preferences_user_id'), 'merchant_category_preferences', ['user_id'], unique=False
    )
    op.create_index(
        op.f('ix_merchant_category_preferences_merchant_id'), 'merchant_category_preferences', ['merchant_id'],
        unique=False,
    )
    op.create_index(
        'uq_merchant_category_preferences_user_merchant',
        'merchant_category_preferences', ['user_id', 'merchant_id'], unique=True,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('uq_merchant_category_preferences_user_merchant', table_name='merchant_category_preferences')
    op.drop_index(op.f('ix_merchant_category_preferences_merchant_id'), table_name='merchant_category_preferences')
    op.drop_index(op.f('ix_merchant_category_preferences_user_id'), table_name='merchant_category_preferences')
    op.drop_table('merchant_category_preferences')

    op.drop_index(op.f('ix_transactions_category_id'), table_name='transactions')
    op.drop_constraint('fk_transactions_category_id_categories', 'transactions', type_='foreignkey')
    op.drop_column('transactions', 'category_id')

    op.drop_index(op.f('ix_transactions_merchant_id'), table_name='transactions')
    op.drop_constraint('fk_transactions_merchant_id_merchants', 'transactions', type_='foreignkey')
    op.drop_column('transactions', 'merchant_id')
