import json
import os
import shutil
from typing import Any, Dict, List, Optional, Union
from uuid import uuid4

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
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

router = APIRouter(tags=["Candidate Portal"])
templates = Jinja2Templates(directory="templates")

# Make sure the uploads directory exists.
os.makedirs("uploads", exist_ok=True)


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
    telegram_username: Optional[str] = None
    birth_date: Optional[str] = None
    gender: Optional[str] = None
    languages: Optional[Union[List[str], str]] = None
    pc_skills: Optional[Union[List[str], str]] = None

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


@router.get("/apply/data", response_model=CascadeDataResponse)
def get_cascade_data(db: Session = Depends(get_session)):
    """
    Returns the necessary JSON payload to populate the frontend cascade dropdowns:
    Active vacancies with their available branch_ids, and all branches.
    """
    active_vacancies = db.exec(select(Vacancy).where(Vacancy.is_active == True)).all()

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
    branches = db.exec(select(Branch)).all()
    branches_list = [{"id": b.id, "name": b.name} for b in branches if b.id is not None]

    return CascadeDataResponse(vacancies=vacancies_list, branches=branches_list)


@router.get("/apply/portal", response_class=HTMLResponse)
def show_portal(request: Request, db: Session = Depends(get_session)):
    """
    Landing portal that lists active vacancies and provides filter data.
    """
    vacancies = db.exec(
        select(Vacancy)
        .where(Vacancy.is_active == True)
        .order_by(Vacancy.id)
    ).all()

    regions = sorted({v.region for v in vacancies if getattr(v, "region", None)})
    departments = sorted({v.department for v in vacancies if getattr(v, "department", None)})
    branch_list = [
        {"id": b.id, "name": b.name}
        for b in db.exec(select(Branch).order_by(Branch.id)).all()
    ]
    categories = sorted({v.category for v in vacancies if getattr(v, "category", None)})

    return templates.TemplateResponse(
        request=request,
        name="portal.html",
        context={
            "request": request,
            "vacancies": vacancies,
            "regions": regions,
            "departments": departments,
            "branches": branch_list,
            "categories": categories,
        },
    )


@router.get("/apply/{vacancy_id}", response_class=HTMLResponse)
async def serve_intake_form(
    vacancy_id: int,
    request: Request,
    db: Session = Depends(get_session),
):
    """Serves the HTML intake form for a specific vacancy."""
    vacancy = db.get(Vacancy, vacancy_id)

    if not vacancy or not getattr(vacancy, "is_active", True):
        return templates.TemplateResponse(
            request=request,
            name="error.html",
            context={
                "request": request,
                "message": "Kechirasiz, ushbu vakansiya yopilgan yoki mavjud emas.",
            },
            status_code=404
        )

    return templates.TemplateResponse(
        request=request,
        name="apply.html",
        context={"request": request, "vacancy": vacancy},
    )


@router.post("/apply/submit", response_model=SubmitResponse, status_code=status.HTTP_201_CREATED)
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

    user = None
    if form_data.telegram_id:
        user = db.exec(select(User).where(User.telegram_id == form_data.telegram_id)).first()

    if not user:
        user = db.exec(select(User).where(User.phone_number == form_data.phone_number)).first()

    if not user:
        user = User(
            telegram_id=form_data.telegram_id,
            telegram_username=form_data.telegram_username,
            full_name=form_data.full_name,
            phone_number=form_data.phone_number,
            role=UserRole.CANDIDATE,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        updated = False
        if form_data.full_name and user.full_name != form_data.full_name:
            user.full_name = form_data.full_name
            updated = True
        if form_data.telegram_id and user.telegram_id != form_data.telegram_id:
            user.telegram_id = form_data.telegram_id
            updated = True
        if form_data.telegram_username and user.telegram_username != form_data.telegram_username:
            user.telegram_username = form_data.telegram_username
            updated = True
        if updated:
            db.add(user)
            db.commit()
            db.refresh(user)

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

    return SubmitResponse(
        success=True,
        message="Application submitted successfully",
        application_id=application.id,
    )


@router.post("/apply/{vacancy_id}")
async def submit_intake_form(
    vacancy_id: int,
    # Step 1: personal info
    full_name: str = Form(...),
    birth_date: Optional[str] = Form(None),
    email: Optional[str] = Form(None),
    address: Optional[str] = Form(None),
    phone_number: str = Form(...),
    telegram_id: Optional[int] = Form(None),
    telegram_username: Optional[str] = Form(None),
    extra_phone: Optional[str] = Form(None),
    marital_status: Optional[str] = Form(None),
    is_student: Optional[str] = Form(None),
    education_field: Optional[str] = Form(None),
    uz_lang_level: Optional[str] = Form(None),
    rus_lang_level: Optional[str] = Form(None),
    eng_lang_level: Optional[str] = Form(None),
    computer_level: Optional[str] = Form(None),
    work_experience_years: Optional[str] = Form(None),
    crm_tools: Optional[str] = Form(None),
    expected_salary: Optional[str] = Form(None),
    has_car: Optional[str] = Form(None),
    why_you: Optional[str] = Form(None),
    is_convicted: Optional[str] = Form(None),
    where_heard: Optional[str] = Form(None),
    accept_offer: Optional[str] = Form(None),

    # Step 2 & 3: dynamic experience & education (JSON strings from frontend)
    experience_json: Optional[str] = Form(None),
    education_json: Optional[str] = Form(None),

    # Step 4: AI questions (may be empty)
    hard_skill_a1: Optional[str] = Form(None),
    hard_skill_a2: Optional[str] = Form(None),
    soft_skill_a1: Optional[str] = Form(None),
    soft_skill_a2: Optional[str] = Form(None),

    # Step 5: files
    photo_file: Optional[UploadFile] = File(None),
    resume_file: Optional[UploadFile] = File(None),

    db: Session = Depends(get_session),
):
    """
    Handles a large multipart application submission; stores files and extended_data JSON.
    """
    vacancy = db.get(Vacancy, vacancy_id)
    if not vacancy:
        raise HTTPException(status_code=404, detail="Vacancy not found")

    # 1) Save files (if present)
    resume_path = None
    photo_path = None
    if resume_file:
        resume_safe = f"{uuid4().hex}_{resume_file.filename}"
        resume_path = os.path.join("uploads", resume_safe)
        with open(resume_path, "wb") as buffer:
            shutil.copyfileobj(resume_file.file, buffer)

    if photo_file:
        photo_safe = f"{uuid4().hex}_{photo_file.filename}"
        photo_path = os.path.join("uploads", photo_safe)
        with open(photo_path, "wb") as buffer:
            shutil.copyfileobj(photo_file.file, buffer)

    # 2) Find or create user (lookup by phone / telegram id)
    user = None
    if telegram_id:
        user = db.exec(select(User).where(User.telegram_id == telegram_id)).first()

    if not user:
        user = db.exec(select(User).where(User.phone_number == phone_number)).first()

    if not user:
        user = User(
            full_name=full_name,
            phone_number=phone_number,
            telegram_id=telegram_id,
            telegram_username=telegram_username,
            role=UserRole.CANDIDATE,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        updated = False
        if full_name and user.full_name != full_name:
            user.full_name = full_name
            updated = True
        if telegram_id and user.telegram_id != telegram_id:
            user.telegram_id = telegram_id
            updated = True
        if telegram_username and user.telegram_username != telegram_username:
            user.telegram_username = telegram_username
            updated = True
        if updated:
            db.add(user)
            db.commit()
            db.refresh(user)

    # 3) Parse dynamic experience and education JSON arrays
    experience_list = []
    education_list = []
    try:
        if experience_json:
            experience_list = json.loads(experience_json)
    except (json.JSONDecodeError, TypeError):
        experience_list = []
    try:
        if education_json:
            education_list = json.loads(education_json)
    except (json.JSONDecodeError, TypeError):
        education_list = []

    # 4) Build extended_data dict (dynamic arrays only — no ai_answers duplication)
    extended_data: Dict[str, Any] = {
        "experience": experience_list,
        "education": education_list,
    }

    # 5) Helper to convert "Ha"/"Yo'q" strings to boolean
    def to_bool(val: Optional[str]) -> Optional[bool]:
        if val is None:
            return None
        return val.lower() in ("ha", "true", "1", "yes", "on")

    # 6) Create CandidateApplication record with all flat columns
    application = CandidateApplication(
        user_id=user.id,
        vacancy_id=vacancy_id,
        branch_id=vacancy.branch_id,
        birth_date=birth_date,
        email=email,
        address=address,
        extra_phone=extra_phone,
        marital_status=marital_status,
        is_student=to_bool(is_student),
        education_field=education_field,
        uz_lang_level=uz_lang_level,
        rus_lang_level=rus_lang_level,
        eng_lang_level=eng_lang_level,
        computer_level=computer_level,
        work_experience_years=work_experience_years,
        crm_tools=crm_tools,
        expected_salary=expected_salary,
        has_car=to_bool(has_car),
        why_you=why_you,
        is_convicted=to_bool(is_convicted),
        where_heard=where_heard,
        accept_offer=to_bool(accept_offer),
        hard_skill_a1=hard_skill_a1 or None,
        hard_skill_a2=hard_skill_a2 or None,
        soft_skill_a1=soft_skill_a1 or None,
        soft_skill_a2=soft_skill_a2 or None,
        resume_file_path=resume_path,
        photo_file_path=photo_path,
        extended_data=extended_data,
        status=ApplicationStatus.PENDING,
        stage=InterviewStage.HR_VERIFICATION,
    )

    db.add(application)
    db.commit()
    db.refresh(application)

    # 7) Persist WorkExperience records from parsed JSON
    for exp in experience_list:
        if isinstance(exp, dict) and exp.get("company_name"):
            work_exp = WorkExperience(
                application_id=application.id,
                company_name=exp.get("company_name", ""),
                position=exp.get("position", ""),
                start_date=exp.get("start_date"),
                end_date=exp.get("end_date"),
                description=exp.get("manager_name", ""),
            )
            db.add(work_exp)

    # 8) Persist Education records from parsed JSON
    for edu in education_list:
        if isinstance(edu, dict) and edu.get("institution"):
            education_rec = Education(
                application_id=application.id,
                institution=edu.get("institution", ""),
                degree=edu.get("degree"),
                field_of_study=edu.get("field_of_study"),
                graduation_year=edu.get("graduation_year"),
            )
            db.add(education_rec)

    db.commit()

    # Return success: Frontend should close WebApp
    return JSONResponse(content={"success": True, "message": "Arizangiz muvaffaqiyatli yuborildi!", "application_id": application.id})

