from typing import Any, Dict
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel import Session, select

from db.database import get_session
from db.models import Branch, LLMActionType, LLMUsageLog, Vacancy
from services.llm_evaluator import generate_vacancy_questions

router = APIRouter(prefix="/hr", tags=["HR Portal"])


class VacancyCreateRequest(BaseModel):
    title: str
    department: str
    description: str
    branch_id: int


class VacancyCreateResponse(BaseModel):
    vacancy: Vacancy
    generated_questions: Dict[str, Any]
    llm_cost_usd: float


@router.post(
    "/vacancies/create",
    response_model=VacancyCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_vacancy(
    request: VacancyCreateRequest,
    db: Session = Depends(get_session),
):
    # 1. Verify that branch_id exists in DB (if not, raise 404)
    branch = db.get(Branch, request.branch_id)
    if not branch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Branch with id {request.branch_id} not found",
        )

    # 2. Call generate_vacancy_questions
    llm_result = await generate_vacancy_questions(
        title=request.title, description=request.description
    )

    questions = llm_result["questions"]
    tokens_input = llm_result["tokens_input"]
    tokens_output = llm_result["tokens_output"]
    cost_usd = llm_result["cost_usd"]

    # 3. Create and persist LLMUsageLog record
    usage_log = LLMUsageLog(
        action_type=LLMActionType.VACANCY_GEN,
        tokens_input=tokens_input,
        tokens_output=tokens_output,
        cost_usd=cost_usd,
    )
    db.add(usage_log)

    # 4. Create and persist Vacancy record
    vacancy = Vacancy(
        title=request.title,
        department=request.department,
        description=request.description,
        branch_id=request.branch_id,
        generated_hard_skill_q1=questions.get("hard_skill_q1", ""),
        generated_hard_skill_q2=questions.get("hard_skill_q2", ""),
        generated_soft_skill_q1=questions.get("soft_skill_q1", ""),
        generated_soft_skill_q2=questions.get("soft_skill_q2", ""),
        llm_cost_usd=cost_usd,
    )
    db.add(vacancy)
    db.commit()
    db.refresh(vacancy)

    # 5. Return HTTP 201 response
    return VacancyCreateResponse(
        vacancy=vacancy,
        generated_questions=questions,
        llm_cost_usd=cost_usd,
    )
