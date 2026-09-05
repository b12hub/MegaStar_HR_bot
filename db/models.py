import enum
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo
from enum import Enum
from typing import Any, Dict, Optional

from sqlalchemy import Column, Enum as SAEnum, String, BigInteger
from sqlalchemy.types import JSON
from sqlmodel import Field, SQLModel


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


class CandidateStage(str, Enum):
    NEW = "NEW"
    SCREENED_BY_BOT = "SCREENED_BY_BOT"
    INTERVIEW_SCHEDULED = "INTERVIEW_SCHEDULED"
    OFFERED = "OFFERED"
    REJECTED = "REJECTED"

    # Backward-compatible aliases used across legacy code and templates.
    HR_VERIFICATION = "HR_VERIFICATION"
    BRANCH_INTERVIEW = "BRANCH_INTERVIEW"
    DIRECTOR_INTERVIEW = "DIRECTOR_INTERVIEW"


# Backwards compatibility alias used by older code.
InterviewStage = CandidateStage


class PipelineStage(str, enum.Enum):
    YANGI = "YANGI"
    HR_ONLINE = "HR_ONLINE"
    HR_OFFLINE = "HR_OFFLINE"
    DIRECTOR_OFFLINE = "DIRECTOR_OFFLINE"
    OFFERED = "OFFERED"
    RAD_ETILDI = "RAD_ETILDI"
    QABUL_QILINDI = "QABUL_QILINDI"


class LLMActionType(str, Enum):
    VACANCY_GEN = "VACANCY_GEN"
    CV_EVALUATION = "CV_EVALUATION"


class Branch(SQLModel, table=True):
    __tablename__ = "branches"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    address: str
    manager_telegram_chat_id: Optional[int] = Field(default=None)


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: Optional[int] = Field(default=None, primary_key=True)
    telegram_id: Optional[int] = Field(default=None, sa_column=Column(BigInteger, unique=True, index=True))
    telegram_username: Optional[str] = Field(default=None)
    full_name: Optional[str] = Field(default=None)
    phone_number: Optional[str] = Field(default=None)
    role: str = Field(default="candidate")
    created_at: datetime = Field(default_factory=lambda: datetime.now(ZoneInfo("Asia/Tashkent")))


class LLMUsageLog(SQLModel, table=True):
    __tablename__ = "llm_usage_logs"

    id: Optional[int] = Field(default=None, primary_key=True)
    action_type: LLMActionType
    tokens_input: int
    tokens_output: int
    cost_usd: float
    created_at: datetime = Field(default_factory=lambda: datetime.now(ZoneInfo("Asia/Tashkent")))


class Vacancy(SQLModel, table=True):
    __tablename__ = "vacancies"

    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    department: str
    branch: Optional[str] = Field(default=None)
    region: Optional[str] = Field(default=None)
    category: Optional[str] = Field(default=None)
    description: str
    branch_id: int = Field(foreign_key="branches.id")

    # --- New structured job-posting fields (Task 1) ---
    reports_to: Optional[str] = Field(default=None)
    job_summary: Optional[str] = Field(default=None)
    work_hours: Optional[str] = Field(default="08:00 - 19:00")
    duties_responsibilities: Optional[str] = Field(default=None)
    required_qualifications: Optional[str] = Field(default=None)
    preferred_qualifications: Optional[str] = Field(default=None)
    salary_range: Optional[str] = Field(default=None)
    benefits: Optional[str] = Field(default=None)

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
    created_at: datetime = Field(default_factory=lambda: datetime.now(ZoneInfo("Asia/Tashkent")))


class CandidateApplication(SQLModel, table=True):
    __tablename__ = "candidate_applications"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id")
    vacancy_id: int = Field(foreign_key="vacancies.id")
    branch_id: int = Field(foreign_key="branches.id")

    birth_date: Optional[str] = Field(default=None)
    gender: Optional[str] = Field(default=None)
    email: Optional[str] = Field(default=None)
    address: Optional[str] = Field(default=None)
    extra_phone: Optional[str] = Field(default=None)
    marital_status: Optional[str] = Field(default=None)
    is_student: Optional[bool] = Field(default=None)
    education_field: Optional[str] = Field(default=None)
    uz_lang_level: Optional[str] = Field(default=None)
    rus_lang_level: Optional[str] = Field(default=None)
    eng_lang_level: Optional[str] = Field(default=None)
    computer_level: Optional[str] = Field(default=None)
    work_experience_years: Optional[str] = Field(default=None)
    crm_tools: Optional[str] = Field(default=None)
    expected_salary: Optional[str] = Field(default=None)
    has_car: Optional[bool] = Field(default=None)
    why_you: Optional[str] = Field(default=None)
    is_convicted: Optional[bool] = Field(default=None)
    where_heard: Optional[str] = Field(default=None)
    accept_offer: Optional[bool] = Field(default=None)
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
    stage: CandidateStage = Field(
        default=CandidateStage.NEW,
        sa_column=Column(
            SAEnum(
                CandidateStage,
                native_enum=False,
                values_callable=lambda enum_cls: [member.value for member in enum_cls],
            ),
            default=CandidateStage.NEW,
            nullable=False,
        ),
    )
    ai_score: Optional[int] = Field(default=None)
    objective_score: Optional[int] = Field(default=0)
    total_score: Optional[int] = Field(default=0)
    ai_reasoning: Optional[str] = Field(default=None)
    pipeline_stage: PipelineStage = Field(default=PipelineStage.YANGI, sa_column=Column(String))
    created_at: datetime = Field(default_factory=lambda: datetime.now(ZoneInfo("Asia/Tashkent")))


class WorkExperience(SQLModel, table=True):
    __tablename__ = "work_experiences"

    id: Optional[int] = Field(default=None, primary_key=True)
    application_id: int = Field(foreign_key="candidate_applications.id")
    company_name: str
    position: str
    start_date: Optional[str] = Field(default=None)
    end_date: Optional[str] = Field(default=None)
    description: Optional[str] = Field(default=None)


class Education(SQLModel, table=True):
    __tablename__ = "educations"

    id: Optional[int] = Field(default=None, primary_key=True)
    application_id: int = Field(foreign_key="candidate_applications.id")
    institution: str
    degree: Optional[str] = Field(default=None)
    field_of_study: Optional[str] = Field(default=None)
    graduation_year: Optional[int] = Field(default=None)


class Meeting(SQLModel, table=True):
    __tablename__ = "meetings"

    id: Optional[int] = Field(default=None, primary_key=True)
    candidate_id: int = Field(foreign_key="candidate_applications.id")
    vacancy_id: Optional[int] = Field(default=None, foreign_key="vacancies.id")
    scheduled_time: Optional[datetime] = Field(default=None)
    hr_chat_id: Optional[str] = Field(default=None)
    boss_chat_id: Optional[str] = Field(default=None)
    candidate_chat_id: Optional[str] = Field(default=None)
    status: str = Field(default="scheduled")
    stage: PipelineStage = Field(default=PipelineStage.YANGI, sa_column=Column(String))
    meeting_time: Optional[datetime] = Field(default=None)
    meeting_link: Optional[str] = Field(default=None)
    is_completed: bool = Field(default=False)
    reminders_sent: bool = Field(default=False)
    created_at: datetime = Field(default_factory=lambda: datetime.now(ZoneInfo("Asia/Tashkent")))


class JobOffer(SQLModel, table=True):
    __tablename__ = "job_offers"

    id: Optional[int] = Field(default=None, primary_key=True)
    candidate_id: int = Field(foreign_key="candidate_applications.id")

    starting_salary: str
    work_days: str
    work_hours: str
    start_datetime: datetime
    location: str

    created_at: datetime = Field(default_factory=lambda: datetime.now(ZoneInfo("Asia/Tashkent")))