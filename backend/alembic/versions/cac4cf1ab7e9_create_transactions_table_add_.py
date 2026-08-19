"""create transactions table, add statements parse_error and file_hash

Revision ID: cac4cf1ab7e9
Revises: 684dfcb36717
Create Date: 2026-08-18 14:58:22.952402

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cac4cf1ab7e9'
down_revision: Union[str, Sequence[str], None] = '684dfcb36717'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('statements', sa.Column('parse_error', sa.String(length=500), nullable=True))
    op.add_column('statements', sa.Column('file_hash', sa.String(length=64), nullable=True))
    op.create_index(op.f('ix_statements_file_hash'), 'statements', ['file_hash'], unique=False)

    op.create_table(
        'transactions',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('statement_id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('transaction_date', sa.Date(), nullable=False),
        sa.Column('post_date', sa.Date(), nullable=True),
        sa.Column('description', sa.String(length=500), nullable=False),
        sa.Column('amount', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('currency', sa.String(length=3), nullable=True),
        sa.Column('raw_row', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['statement_id'], ['statements.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['auth.users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_transactions_statement_id'), 'transactions', ['statement_id'], unique=False)
    op.create_index(op.f('ix_transactions_user_id'), 'transactions', ['user_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_transactions_user_id'), table_name='transactions')
    op.drop_index(op.f('ix_transactions_statement_id'), table_name='transactions')
    op.drop_table('transactions')

    op.drop_index(op.f('ix_statements_file_hash'), table_name='statements')
    op.drop_column('statements', 'file_hash')
    op.drop_column('statements', 'parse_error')
