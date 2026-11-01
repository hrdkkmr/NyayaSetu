"""google sign-in and one-time reset codes

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-01 12:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0002'
down_revision: str | None = '0001'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('users', sa.Column('google_sub', sa.String(length=255), nullable=True))
    op.create_index(op.f('ix_users_google_sub'), 'users', ['google_sub'], unique=True)
    op.add_column('password_reset_tokens',
                  sa.Column('attempts', sa.Integer(), server_default='0', nullable=False))


def downgrade() -> None:
    with op.batch_alter_table('password_reset_tokens') as batch:
        batch.drop_column('attempts')
    op.drop_index(op.f('ix_users_google_sub'), table_name='users')
    with op.batch_alter_table('users') as batch:
        batch.drop_column('google_sub')
