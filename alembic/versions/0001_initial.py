"""initial migration for branch, llm_usage_log, and vacancy models

Revision ID: 0001_initial
Revises: 
Create Date: 2026-08-25 17:31:00.000000

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel

# revision identifiers, used by Alembic.
revision = '0001_initial'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'branch',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('address', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('manager_telegram_chat_id', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_table(
        'llm_usage_log',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('action_type', sa.Enum('VACANCY_GEN', 'CV_EVALUATION', name='llmactiontype'), nullable=False),
        sa.Column('tokens_input', sa.Integer(), nullable=False),
        sa.Column('tokens_output', sa.Integer(), nullable=False),
        sa.Column('cost_usd', sa.Float(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_table(
        'vacancy',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('title', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('department', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('description', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('branch_id', sa.Integer(), nullable=False),
        sa.Column('generated_hard_skill_q1', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('generated_hard_skill_q2', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('generated_soft_skill_q1', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('generated_soft_skill_q2', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['branch_id'], ['branch.id'], ),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    op.drop_table('vacancy')
    op.drop_table('llm_usage_log')
    op.drop_table('branch')
