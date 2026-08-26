import json
from typing import List, Optional, Any, Dict
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from db.database import get_session
from db.models import (
    ApplicationStatus,
    Branch,
    CandidateApplication,
    Education,
    InterviewStage,
    User,
    UserRole,
    Vacancy,
    WorkExperience,
)

router = APIRouter(prefix="/apply", tags=["Candidate Portal"])


class VacancyCascadeItem(BaseModel):
    id: int
    title: str
    branch_ids: List[int]


class BranchItem(BaseModel):
    id: int
    name: str


class CascadeDataResponse(BaseModel):
    vacancies: List[VacancyCascadeItem]
    branches: List[BranchItem]


class WorkExperienceItem(BaseModel):
    company_name: str
    position: str
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    description: Optional[str] = None


class EducationItem(BaseModel):
    institution: str
    degree: Optional[str] = None
    field_of_study: Optional[str] = None
    graduation_year: Optional[int] = None


class CandidateFormSubmit(BaseModel):
    # Personal details
    full_name: str
    phone_number: str
    telegram_id: Optional[int] = None
    birth_date: Optional[str] = None
    gender: Optional[str] = None
    languages: Optional[List[str] | str] = None
    pc_skills: Optional[List[str] | str] = None

    # Cascade Selection (Manual selection, no GPS)
    vacancy_id: int
    branch_id: int

    # Experience and Education arrays
    experience: List[WorkExperienceItem] = Field(default_factory=list)
    education: List[EducationItem] = Field(default_factory=list)

    # Dynamic Questions Answers
    hard_skill_a1: Optional[str] = None
    hard_skill_a2: Optional[str] = None
    soft_skill_a1: Optional[str] = None
    soft_skill_a2: Optional[str] = None


class SubmitResponse(BaseModel):
    success: bool
    message: str
    application_id: int


@router.get("/data", response_model=CascadeDataResponse)
def get_cascade_data(db: Session = Depends(get_session)):
    """
    Returns the necessary JSON payload to populate the frontend cascade dropdowns:
    Active vacancies with their available branch_ids, and all branches.
    """
    # 1. Query all active Vacancy records
    active_vacancies = db.exec(select(Vacancy).where(Vacancy.is_active == True)).all()

    # Aggregate branch_ids per vacancy title (or per vacancy id)
    # Front-end cascade dropdown format:
    # {"vacancies": [{"id": 1, "title": "Cashier", "branch_ids": [1, 2]}], "branches": [{"id": 1, "name": "Chilonzor"}, ...]}
    # We group by vacancy title/id or preserve unique vacancy representations
    vacancy_map: Dict[str, Dict[str, Any]] = {}
    for vac in active_vacancies:
        if vac.title not in vacancy_map:
            vacancy_map[vac.title] = {
                "id": vac.id,
                "title": vac.title,
                "branch_ids": [vac.branch_id],
            }
        else:
            if vac.branch_id not in vacancy_map[vac.title]["branch_ids"]:
                vacancy_map[vac.title]["branch_ids"].append(vac.branch_id)

    vacancies_list = list(vacancy_map.values())

    # 2. Query all Branch records
    branches = db.exec(select(Branch)).all()
    branches_list = [{"id": b.id, "name": b.name} for b in branches if b.id is not None]

    return CascadeDataResponse(vacancies=vacancies_list, branches=branches_list)


@router.post("/submit", response_model=SubmitResponse, status_code=status.HTTP_201_CREATED)
async def submit_candidate_application(
    form_data: CandidateFormSubmit,
    db: Session = Depends(get_session),
):
    """
    Accepts candidate application payload and saves it to PostgreSQL database:
    - Creates or updates User record
    - Validates vacancy and branch
    - Creates CandidateApplication record (PENDING, HR_VERIFICATION)
    - Creates WorkExperience and Education records
    - Triggers async LLM evaluation
    """
    # 1. Validate Vacancy and Branch exist
    vacancy = db.get(Vacancy, form_data.vacancy_id)
    if not vacancy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Vacancy with id {form_data.vacancy_id} not found",
        )

    branch = db.get(Branch, form_data.branch_id)
    if not branch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Branch with id {form_data.branch_id} not found",
        )

    # 2. Find or create User
    user = None
    if form_data.telegram_id:
        user = db.exec(select(User).where(User.telegram_id == form_data.telegram_id)).first()

    if not user:
        user = db.exec(select(User).where(User.phone_number == form_data.phone_number)).first()

    if not user:
        user = User(
            telegram_id=form_data.telegram_id,
            full_name=form_data.full_name,
            phone_number=form_data.phone_number,
            role=UserRole.CANDIDATE,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        # Update user full_name or telegram_id if newly provided
        updated = False
        if form_data.full_name and user.full_name != form_data.full_name:
            user.full_name = form_data.full_name
            updated = True
        if form_data.telegram_id and user.telegram_id != form_data.telegram_id:
            user.telegram_id = form_data.telegram_id
            updated = True
        if updated:
            db.add(user)
            db.commit()
            db.refresh(user)

    # Convert languages & pc_skills to string if passed as list
    languages_str = (
        json.dumps(form_data.languages, ensure_ascii=False)
        if isinstance(form_data.languages, list)
        else form_data.languages
    )
    pc_skills_str = (
        json.dumps(form_data.pc_skills, ensure_ascii=False)
        if isinstance(form_data.pc_skills, list)
        else form_data.pc_skills
    )

    # 3. Create CandidateApplication record with status PENDING and stage HR_VERIFICATION
    application = CandidateApplication(
        user_id=user.id,
        vacancy_id=form_data.vacancy_id,
        branch_id=form_data.branch_id,
        birth_date=form_data.birth_date,
        gender=form_data.gender,
        languages=languages_str,
        pc_skills=pc_skills_str,
        hard_skill_a1=form_data.hard_skill_a1,
        hard_skill_a2=form_data.hard_skill_a2,
        soft_skill_a1=form_data.soft_skill_a1,
        soft_skill_a2=form_data.soft_skill_a2,
        status=ApplicationStatus.PENDING,
        stage=InterviewStage.HR_VERIFICATION,
    )
    db.add(application)
    db.commit()
    db.refresh(application)

    # 4. Create WorkExperience records
    for exp in form_data.experience:
        work_exp = WorkExperience(
            application_id=application.id,
            company_name=exp.company_name,
            position=exp.position,
            start_date=exp.start_date,
            end_date=exp.end_date,
            description=exp.description,
        )
        db.add(work_exp)

    # 5. Create Education records
    for edu in form_data.education:
        education_rec = Education(
            application_id=application.id,
            institution=edu.institution,
            degree=edu.degree,
            field_of_study=edu.field_of_study,
            graduation_year=edu.graduation_year,
        )
        db.add(education_rec)

    db.commit()

    # 6. Trigger LLM evaluation asynchronously
    # TODO: Trigger async CV/Application LLM evaluation via services/llm_evaluator.py
    # asyncio.create_task(evaluate_candidate_application(application.id))

    return SubmitResponse(
        success=True,
        message="Application submitted successfully",
        application_id=application.id,
    )
