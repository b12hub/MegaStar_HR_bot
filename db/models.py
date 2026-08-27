from enum import Enum
from datetime import datetime, date, timezone
from typing import Optional, List, Dict, Any
from sqlmodel import SQLModel, Field
from sqlalchemy import Column
from sqlalchemy.types import JSON


class UserRole(str, Enum):
    CANDIDATE = "CANDIDATE"
    HR = "HR"
    DIRECTOR = "DIRECTOR"
    EMPLOYEE = "EMPLOYEE"


class ApplicationStatus(str, Enum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    TALENT_POOL = "TALENT_POOL"
    HIRED = "HIRED"


class InterviewStage(str, Enum):
    HR_VERIFICATION = "HR_VERIFICATION"
    BRANCH_INTERVIEW = "BRANCH_INTERVIEW"
    DIRECTOR_INTERVIEW = "DIRECTOR_INTERVIEW"


class LLMActionType(str, Enum):
    VACANCY_GEN = "VACANCY_GEN"
    CV_EVALUATION = "CV_EVALUATION"


class Branch(SQLModel, table=True):
    __tablename__ = "branch"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    address: str
    manager_telegram_chat_id: Optional[int] = Field(default=None)


class User(SQLModel, table=True):
    __tablename__ = "user"

    id: Optional[int] = Field(default=None, primary_key=True)
    telegram_id: Optional[int] = Field(default=None, unique=True, index=True)
    telegram_username: Optional[str] = Field(default=None)
    full_name: Optional[str] = Field(default=None)
    phone_number: Optional[str] = Field(default=None)
    role: str = Field(default="candidate")
    created_at: datetime = Field(default_factory=datetime.utcnow)


class LLMUsageLog(SQLModel, table=True):
    __tablename__ = "llm_usage_log"

    id: Optional[int] = Field(default=None, primary_key=True)
    action_type: LLMActionType
    tokens_input: int
    tokens_output: int
    cost_usd: float
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Vacancy(SQLModel, table=True):
    __tablename__ = "vacancy"

    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    department: str
    branch: Optional[str] = Field(default=None)
    region: Optional[str] = Field(default=None)
    category: Optional[str] = Field(default=None)
    description: str
    branch_id: int = Field(foreign_key="branch.id")
    generated_hard_skill_q1: Optional[str] = Field(default=None)
    generated_hard_skill_q2: Optional[str] = Field(default=None)
    generated_soft_skill_q1: Optional[str] = Field(default=None)
    generated_soft_skill_q2: Optional[str] = Field(default=None)
    hard_skill_q1: Optional[str] = Field(default=None)
    hard_skill_q2: Optional[str] = Field(default=None)
    soft_skill_q1: Optional[str] = Field(default=None)
    soft_skill_q2: Optional[str] = Field(default=None)
    llm_cost_usd: float = Field(default=0.0)
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CandidateApplication(SQLModel, table=True):
    __tablename__ = "candidate_application"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id")
    vacancy_id: int = Field(foreign_key="vacancy.id")
    branch_id: int = Field(foreign_key="branch.id")

    birth_date: Optional[str] = Field(default=None)
    gender: Optional[str] = Field(default=None)
    languages: Optional[str] = Field(default=None)
    pc_skills: Optional[str] = Field(default=None)

    hard_skill_a1: Optional[str] = Field(default=None)
    hard_skill_a2: Optional[str] = Field(default=None)
    soft_skill_a1: Optional[str] = Field(default=None)
    soft_skill_a2: Optional[str] = Field(default=None)

    resume_file_path: Optional[str] = Field(default=None)
    photo_file_path: Optional[str] = Field(default=None)
    extended_data: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))

    status: ApplicationStatus = Field(default=ApplicationStatus.PENDING)
    stage: InterviewStage = Field(default=InterviewStage.HR_VERIFICATION)
    ai_score: Optional[int] = Field(default=None)

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class WorkExperience(SQLModel, table=True):
    __tablename__ = "work_experience"

    id: Optional[int] = Field(default=None, primary_key=True)
    application_id: int = Field(foreign_key="candidate_application.id")
    company_name: str
    position: str
    start_date: Optional[str] = Field(default=None)
    end_date: Optional[str] = Field(default=None)
    description: Optional[str] = Field(default=None)


class Education(SQLModel, table=True):
    __tablename__ = "education"

    id: Optional[int] = Field(default=None, primary_key=True)
    application_id: int = Field(foreign_key="candidate_application.id")
    institution: str
    degree: Optional[str] = Field(default=None)
    field_of_study: Optional[str] = Field(default=None)
    graduation_year: Optional[int] = Field(default=None)
