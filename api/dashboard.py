from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select
from typing import Optional

from db.database import get_session
from db.models import (
    ApplicationStatus,
    Branch,
    CandidateApplication,
    InterviewStage,
    LLMActionType,
    LLMUsageLog,
    User,
    Vacancy,
)
from services.llm_evaluator import generate_vacancy_questions

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

templates = Jinja2Templates(directory="templates")


@router.get("/hr", response_class=HTMLResponse)
async def get_hr_dashboard(
    request: Request,
    db: Session = Depends(get_session),
):
    statement = select(Vacancy).order_by(Vacancy.id)
    vacancies = db.exec(statement).all()

    total_ai_cost = sum(v.llm_cost_usd or 0.0 for v in vacancies)
    active_vacancies_count = sum(
        1 for v in vacancies if getattr(v, "is_active", False)
    )

    candidate_counts = {}
    applications = db.exec(select(CandidateApplication)).all()
    for application in applications:
        candidate_counts[application.vacancy_id] = (
            candidate_counts.get(application.vacancy_id, 0) + 1
        )

    vacancy_rows = []
    for vacancy in vacancies:
        vacancy_row = vacancy.model_dump() if hasattr(vacancy, "model_dump") else {
            key: getattr(vacancy, key) for key in [
                "id", "title", "department", "branch", "region", "category",
                "description", "branch_id", "is_active", "llm_cost_usd", "created_at",
            ] if hasattr(vacancy, key)
        }
        vacancy_row["candidate_count"] = candidate_counts.get(vacancy.id, 0)
        vacancy_rows.append(vacancy_row)

    recent_applications = []
    for application in applications[-5:]:
        user = db.get(User, application.user_id)
        recent_applications.append({
            "id": application.id,
            "full_name": user.full_name if user and user.full_name else "Noma'lum nomzod",
            "vacancy_title": db.get(Vacancy, application.vacancy_id).title if db.get(Vacancy, application.vacancy_id) else "-",
            "status": application.status.value if hasattr(application.status, "value") else str(application.status),
            "created_at": application.created_at,
        })

    return templates.TemplateResponse(
        request=request,
        name="hr_dashboard.html",
        context={
            "request": request,
            "vacancies": vacancy_rows,
            "recent_applications": recent_applications,
            "total_ai_cost": total_ai_cost,
            "active_vacancies_count": active_vacancies_count,
        },
    )


@router.get("/vacancies/new", response_class=HTMLResponse)
async def new_vacancy_page(
    request: Request,
    db: Session = Depends(get_session),
):
    branches = db.exec(select(Branch).order_by(Branch.id)).all()
    return templates.TemplateResponse(
        request=request,
        name="vacancy_create.html",
        context={
            "request": request,
            "branches": branches,
        },
    )


@router.post("/vacancies/new")
async def create_vacancy_form(
    request: Request,
    title: str = Form(...),
    department: str = Form(...),
    description: str = Form(...),
    branch_id: int = Form(...),
    db: Session = Depends(get_session),
):
    branch = db.get(Branch, branch_id)
    if not branch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Branch with id {branch_id} not found",
        )

    # Invoke LLM evaluator
    llm_result = await generate_vacancy_questions(
        title=title, description=description
    )

    questions = llm_result.get("questions", {})
    tokens_input = llm_result.get("tokens_input", 0)
    tokens_output = llm_result.get("tokens_output", 0)
    cost_usd = llm_result.get("cost_usd", 0.0)

    # Persist LLM usage log
    usage_log = LLMUsageLog(
        action_type=LLMActionType.VACANCY_GEN,
        tokens_input=tokens_input,
        tokens_output=tokens_output,
        cost_usd=cost_usd,
    )
    db.add(usage_log)

    # Create and persist Vacancy record
    vacancy = Vacancy(
        title=title,
        department=department,
        description=description,
        branch_id=branch_id,
        generated_hard_skill_q1=questions.get("hard_skill_q1", ""),
        generated_hard_skill_q2=questions.get("hard_skill_q2", ""),
        generated_soft_skill_q1=questions.get("soft_skill_q1", ""),
        generated_soft_skill_q2=questions.get("soft_skill_q2", ""),
        llm_cost_usd=cost_usd,
    )
    db.add(vacancy)
    db.commit()
    db.refresh(vacancy)

    return RedirectResponse(url="/dashboard/hr", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/vacancies/{vacancy_id}", response_class=HTMLResponse)
async def get_vacancy_detail(
    vacancy_id: int,
    request: Request,
    db: Session = Depends(get_session),
):
    vacancy = db.get(Vacancy, vacancy_id)
    if not vacancy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Vacancy with id {vacancy_id} not found",
        )

    branch = db.get(Branch, vacancy.branch_id)

    return templates.TemplateResponse(
        request=request,
        name="vacancy_detail.html",
        context={
            "request": request,
            "vacancy": vacancy,
            "branch": branch,
        },
    )


@router.get("/vacancies/{vacancy_id}/candidates", response_class=HTMLResponse)
async def get_vacancy_candidates(
    vacancy_id: int,
    request: Request,
    db: Session = Depends(get_session),
):
    vacancy = db.get(Vacancy, vacancy_id)
    if not vacancy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Vacancy with id {vacancy_id} not found",
        )

    applications = db.exec(
        select(CandidateApplication)
        .where(CandidateApplication.vacancy_id == vacancy_id)
        .order_by(CandidateApplication.created_at.desc())
    ).all()

    candidates = []
    for application in applications:
        user = db.get(User, application.user_id)
        candidates.append(
            {
                "id": application.id,
                "full_name": user.full_name if user and user.full_name else "Noma'lum nomzod",
                "phone_number": user.phone_number if user and user.phone_number else "-",
                "telegram_username": user.telegram_username if user and user.telegram_username else "Mavjud emas",
                "created_at": application.created_at,
                "status": application.status.value if hasattr(application.status, "value") else str(application.status),
                "ai_score": application.ai_score if application.ai_score is not None else "-",
                "user": user,
            }
        )

    return templates.TemplateResponse(
        request=request,
        name="candidate_list.html",
        context={
            "request": request,
            "vacancy": vacancy,
            "candidates": candidates,
        },
    )


@router.get("/candidates/{candidate_id}", response_class=HTMLResponse)
async def get_candidate_detail(
    candidate_id: int,
    request: Request,
    db: Session = Depends(get_session),
):
    application = db.get(CandidateApplication, candidate_id)
    if not application:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"CandidateApplication with id {candidate_id} not found")

    vacancy = db.get(Vacancy, application.vacancy_id)
    user = db.get(User, application.user_id)
    extended_data = application.extended_data or {}

    return templates.TemplateResponse(
        request=request,
        name="candidate_detail.html",
        context={
            "request": request,
            "candidate": application,
            "user": user,
            "vacancy": vacancy,
            "extended_data": extended_data,
        },
    )


@router.post("/candidates/{candidate_id}/evaluate")
async def evaluate_candidate(
    candidate_id: int,
    db: Session = Depends(get_session),
):
    application = db.get(CandidateApplication, candidate_id)
    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"CandidateApplication with id {candidate_id} not found",
        )

    score = 0
    if application.hard_skill_a1:
        score += 20
    if application.hard_skill_a2:
        score += 20
    if application.soft_skill_a1:
        score += 20
    if application.soft_skill_a2:
        score += 20
    if application.resume_file_path:
        score += 20

    application.ai_score = score
    application.status = ApplicationStatus.PENDING
    application.stage = InterviewStage.HR_VERIFICATION
    db.add(application)
    db.commit()
    db.refresh(application)

    return JSONResponse(
        content={
            "status": "success",
            "message": "AI baholash yakunlandi.",
            "candidate_id": candidate_id,
            "score": score,
        }
    )


@router.post("/vacancies/{vacancy_id}/toggle")
async def toggle_vacancy_status(
    vacancy_id: int,
    db: Session = Depends(get_session),
):
    vacancy = db.get(Vacancy, vacancy_id)
    if not vacancy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Vacancy with id {vacancy_id} not found",
        )

    vacancy.is_active = not vacancy.is_active
    db.add(vacancy)
    db.commit()
    db.refresh(vacancy)

    return RedirectResponse(url="/dashboard/hr", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/vacancies/{vacancy_id}/edit", response_class=HTMLResponse)
async def edit_vacancy_page(
    vacancy_id: int,
    request: Request,
    db: Session = Depends(get_session),
):
    vacancy = db.get(Vacancy, vacancy_id)
    if not vacancy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Vacancy with id {vacancy_id} not found",
        )

    branches = db.exec(select(Branch).order_by(Branch.id)).all()
    return templates.TemplateResponse(
        request=request,
        name="vacancy_edit.html",
        context={
            "request": request,
            "vacancy": vacancy,
            "branches": branches,
        },
    )


@router.post("/vacancies/{vacancy_id}/edit")
async def update_vacancy(
    vacancy_id: int,
    request: Request,
    title: str = Form(...),
    department: str = Form(...),
    description: str = Form(...),
    branch_id: int = Form(...),
    is_active: bool = Form(False),
    generated_hard_skill_q1: str = Form(""),
    generated_hard_skill_q2: str = Form(""),
    generated_soft_skill_q1: str = Form(""),
    generated_soft_skill_q2: str = Form(""),
    custom_ai_prompt: Optional[str] = Form(None),
    regenerate_ai: bool = Form(False),
    db: Session = Depends(get_session),
):
    vacancy = db.get(Vacancy, vacancy_id)
    if not vacancy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Vacancy with id {vacancy_id} not found",
        )

    branch = db.get(Branch, branch_id)
    if not branch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Branch with id {branch_id} not found",
        )

    # If AI regeneration is requested, re-run the LLM evaluator.
    if regenerate_ai:
        llm_kwargs = {
            "title": title,
            "description": description,
        }
        if custom_ai_prompt and custom_ai_prompt.strip():
            llm_kwargs["custom_prompt"] = custom_ai_prompt.strip()

        llm_result = await generate_vacancy_questions(**llm_kwargs)
        questions = llm_result.get("questions", {})
        tokens_input = llm_result.get("tokens_input", 0)
        tokens_output = llm_result.get("tokens_output", 0)
        cost_usd = llm_result.get("cost_usd", 0.0)

        usage_log = LLMUsageLog(
            action_type=LLMActionType.VACANCY_GEN,
            tokens_input=tokens_input,
            tokens_output=tokens_output,
            cost_usd=cost_usd,
        )
        db.add(usage_log)

        vacancy.generated_hard_skill_q1 = questions.get("hard_skill_q1", vacancy.generated_hard_skill_q1 or "")
        vacancy.generated_hard_skill_q2 = questions.get("hard_skill_q2", vacancy.generated_hard_skill_q2 or "")
        vacancy.generated_soft_skill_q1 = questions.get("soft_skill_q1", vacancy.generated_soft_skill_q1 or "")
        vacancy.generated_soft_skill_q2 = questions.get("soft_skill_q2", vacancy.generated_soft_skill_q2 or "")
        vacancy.llm_cost_usd = (vacancy.llm_cost_usd or 0.0) + cost_usd
    else:
        # Save manual text overwrites directly while preserving existing values when form fields are blank.
        vacancy.generated_hard_skill_q1 = generated_hard_skill_q1 or vacancy.generated_hard_skill_q1
        vacancy.generated_hard_skill_q2 = generated_hard_skill_q2 or vacancy.generated_hard_skill_q2
        vacancy.generated_soft_skill_q1 = generated_soft_skill_q1 or vacancy.generated_soft_skill_q1
        vacancy.generated_soft_skill_q2 = generated_soft_skill_q2 or vacancy.generated_soft_skill_q2

    # Update base vacancy parameters
    vacancy.title = title
    vacancy.department = department
    vacancy.description = description
    vacancy.branch_id = branch_id
    vacancy.is_active = is_active

    db.add(vacancy)
    db.commit()
    db.refresh(vacancy)

    return RedirectResponse(url="/dashboard/hr", status_code=status.HTTP_303_SEE_OTHER)

@router.post("/vacancies/{vacancy_id}/delete")
async def delete_vacancy(
    vacancy_id: int,
    db: Session = Depends(get_session),
):
    vacancy = db.get(Vacancy, vacancy_id)
    if not vacancy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Vacancy with id {vacancy_id} not found",
        )

    db.delete(vacancy)
    db.commit()

    return RedirectResponse(url="/dashboard/hr", status_code=status.HTTP_303_SEE_OTHER)
