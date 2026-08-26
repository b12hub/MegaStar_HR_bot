from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select
from typing import Optional

from db.database import get_session
from db.models import Branch, LLMActionType, LLMUsageLog, Vacancy
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

    return templates.TemplateResponse(
        request=request,
        name="hr_dashboard.html",
        context={
            "request": request,
            "vacancies": vacancies,
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

    # If AI regeneration requested with a custom prompt, re-run LLM Evaluator
    if regenerate_ai and custom_ai_prompt and custom_ai_prompt.strip():
        llm_result = await generate_vacancy_questions(
            title=title,
            description=description,
            custom_prompt=custom_ai_prompt.strip(),
        )
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

        vacancy.generated_hard_skill_q1 = questions.get("hard_skill_q1", "")
        vacancy.generated_hard_skill_q2 = questions.get("hard_skill_q2", "")
        vacancy.generated_soft_skill_q1 = questions.get("soft_skill_q1", "")
        vacancy.generated_soft_skill_q2 = questions.get("soft_skill_q2", "")
        vacancy.llm_cost_usd = (vacancy.llm_cost_usd or 0.0) + cost_usd
    else:
        # Save manual text overwrites directly
        vacancy.generated_hard_skill_q1 = generated_hard_skill_q1
        vacancy.generated_hard_skill_q2 = generated_hard_skill_q2
        vacancy.generated_soft_skill_q1 = generated_soft_skill_q1
        vacancy.generated_soft_skill_q2 = generated_soft_skill_q2

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
