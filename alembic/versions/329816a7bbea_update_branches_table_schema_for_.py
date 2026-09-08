"""Update branches table schema for location and chat ids

Revision ID: 329816a7bbea
Revises: f97996a0609d
Create Date: 2026-09-08 07:53:30.899149

"""
from typing import Sequence, Union
import sqlmodel
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '329816a7bbea'
down_revision: Union[str, Sequence[str], None] = 'f97996a0609d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 1. Apply schema updates to the active branches table with safe server defaults for existing rows
    op.add_column('branches',
                  sa.Column('region', sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default='Tashkent'))
    op.add_column('branches',
                  sa.Column('location_url', sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=''))
    op.add_column('branches', sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')))

    op.alter_column('branches', 'manager_telegram_chat_id',
                    existing_type=sa.BIGINT(),
                    type_=sa.Integer(),
                    existing_nullable=True)
    op.drop_column('branches', 'address')

    # 2. Update candidate_applications stage enum
    op.alter_column('candidate_applications', 'stage',
                    existing_type=postgresql.ENUM('NEW', 'SCREENED_BY_BOT', 'INTERVIEW_SCHEDULED', 'OFFERED',
                                                  'REJECTED', 'HR_VERIFICATION', name='candidatestage'),
                    type_=sa.Enum('NEW', 'SCREENED_BY_BOT', 'INTERVIEW_SCHEDULED', 'OFFERED', 'REJECTED',
                                  'HR_VERIFICATION', 'BRANCH_INTERVIEW', 'DIRECTOR_INTERVIEW', name='candidatestage',
                                  native_enum=False),
                    existing_nullable=False)

    # 3. Clean up unused columns and index on users table
    op.drop_index(op.f('ix_users_role'), table_name='users')
    op.drop_column('users', 'is_active')
    op.drop_column('users', 'updated_at')


def downgrade() -> None:
    """Downgrade schema."""
    # 1. Revert users table columns and index
    op.add_column('users', sa.Column('updated_at', postgresql.TIMESTAMP(), server_default=sa.text('CURRENT_TIMESTAMP'), autoincrement=False, nullable=False))
    op.add_column('users', sa.Column('is_active', sa.BOOLEAN(), server_default=sa.text('true'), autoincrement=False, nullable=False))
    op.create_index(op.f('ix_users_role'), 'users', ['role'], unique=False)

    # 2. Revert candidate_applications stage enum
    op.alter_column('candidate_applications', 'stage',
               existing_type=sa.Enum('NEW', 'SCREENED_BY_BOT', 'INTERVIEW_SCHEDULED', 'OFFERED', 'REJECTED', 'HR_VERIFICATION', 'BRANCH_INTERVIEW', 'DIRECTOR_INTERVIEW', name='candidatestage', native_enum=False),
               type_=postgresql.ENUM('NEW', 'SCREENED_BY_BOT', 'INTERVIEW_SCHEDULED', 'OFFERED', 'REJECTED', 'HR_VERIFICATION', name='candidatestage'),
               existing_nullable=False)

    # 3. Revert branches table schema changes
    op.add_column('branches', sa.Column('address', sa.VARCHAR(), autoincrement=False, nullable=False))
    op.alter_column('branches', 'manager_telegram_chat_id',
               existing_type=sa.Integer(),
               type_=sa.BIGINT(),
               existing_nullable=True)
    op.drop_column('branches', 'is_active')
    op.drop_column('branches', 'location_url')
    op.drop_column('branches', 'region')