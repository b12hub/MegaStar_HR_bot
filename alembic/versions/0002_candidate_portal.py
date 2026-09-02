"""candidate portal models: user, candidate_application, work_experience, education

Revision ID: 0002_candidate_portal
Revises: 0001_initial
Create Date: 2026-08-25 17:45:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import sqlmodel

# revision identifiers, used by Alembic.
revision = '0002_candidate_portal'
down_revision = '0001_initial'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Ensure types exist or handle cleanly
    conn = op.get_bind()
    if conn.dialect.name == 'postgresql':
        userrole_enum = postgresql.ENUM('CANDIDATE', 'HR', 'DIRECTOR', 'EMPLOYEE', name='userrole', create_type=False)
        status_enum = postgresql.ENUM('PENDING', 'ACCEPTED', 'REJECTED', 'TALENT_POOL', 'HIRED', name='applicationstatus', create_type=False)
        stage_enum = postgresql.ENUM('HR_VERIFICATION', 'BRANCH_INTERVIEW', 'DIRECTOR_INTERVIEW', name='interviewstage', create_type=False)
    else:
        userrole_enum = sa.Enum('CANDIDATE', 'HR', 'DIRECTOR', 'EMPLOYEE', name='userrole')
        status_enum = sa.Enum('PENDING', 'ACCEPTED', 'REJECTED', 'TALENT_POOL', 'HIRED', name='applicationstatus')
        stage_enum = sa.Enum('HR_VERIFICATION', 'BRANCH_INTERVIEW', 'DIRECTOR_INTERVIEW', name='interviewstage')

    op.create_table(
        'user',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('telegram_id', sa.Integer(), nullable=True),
        sa.Column('full_name', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('phone_number', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('role', userrole_enum, nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        if_not_exists=True
    )
    if conn.dialect.name == 'postgresql':
        op.execute('CREATE INDEX IF NOT EXISTS ix_user_telegram_id ON "user" (telegram_id);')
    else:
        try:
            op.create_index(op.f('ix_user_telegram_id'), 'user', ['telegram_id'], unique=False)
        except Exception:
            pass

    op.create_table(
        'candidate_application',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('vacancy_id', sa.Integer(), nullable=False),
        sa.Column('branch_id', sa.Integer(), nullable=False),
        sa.Column('birth_date', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('gender', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('languages', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('pc_skills', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('hard_skill_a1', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('hard_skill_a2', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('soft_skill_a1', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('soft_skill_a2', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('status', status_enum, nullable=False),
        sa.Column('stage', stage_enum, nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['branch_id'], ['branch.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ),
        sa.ForeignKeyConstraint(['vacancy_id'], ['vacancy.id'], ),
        sa.PrimaryKeyConstraint('id'),
        if_not_exists=True
    )

    op.create_table(
        'work_experience',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('application_id', sa.Integer(), nullable=False),
        sa.Column('company_name', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('position', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('start_date', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('end_date', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('description', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.ForeignKeyConstraint(['application_id'], ['candidate_application.id'], ),
        sa.PrimaryKeyConstraint('id'),
        if_not_exists=True
    )

    op.create_table(
        'education',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('application_id', sa.Integer(), nullable=False),
        sa.Column('institution', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('degree', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('field_of_study', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('graduation_year', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['application_id'], ['candidate_application.id'], ),
        sa.PrimaryKeyConstraint('id'),
        if_not_exists=True
    )


def downgrade() -> None:
    op.drop_table('education')
    op.drop_table('work_experience')
    op.drop_table('candidate_application')
    op.drop_index(op.f('ix_user_telegram_id'), table_name='user')
    op.drop_table('user')
