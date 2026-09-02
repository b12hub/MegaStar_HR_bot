"""add llm_cost_usd to vacancy table

Revision ID: 0003_vacancy_cost
Revises: 0002_candidate_portal
Create Date: 2026-08-26 13:15:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0003_vacancy_cost'
down_revision = '0002_candidate_portal'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name == 'postgresql':
        op.execute("ALTER TABLE vacancy ADD COLUMN IF NOT EXISTS llm_cost_usd DOUBLE PRECISION DEFAULT 0.0;")
    else:
        try:
            op.add_column('vacancy', sa.Column('llm_cost_usd', sa.Float(), nullable=False, server_default='0.0'))
        except Exception:
            pass


def downgrade() -> None:
    op.drop_column('vacancy', 'llm_cost_usd')
