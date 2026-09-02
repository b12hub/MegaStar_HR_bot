from fastapi import APIRouter, HTTPException , Depends, Form, Request, status, BackgroundTasks, Query
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select
from pydantic import BaseModel
from datetime import datetime, timezone
from typing import Optional, Union


# Services
from services.zoom_service import create_zoom_meeting
from services.notifications import notify_candidate_status
from services.llm_evaluator import evaluate_candidate_answers, generate_vacancy_questions
from services.google_sheets import sync_candidates_to_sheet

class ScheduleRequest(BaseModel):
    stage: str
    meeting_time: Union[datetime, str]
    meeting_link: Optional[str] = None
    branch_name: Optional[str] = None


from db.database import get_session
from db.models import (
    ApplicationStatus,
    Branch,
    CandidateApplication,
    CandidateStage,
    InterviewStage,
    LLMActionType,
    LLMUsageLog,
    User,
    Vacancy,
    Meeting,
    PipelineStage,
)


import logging
logger = logging.getLogger(__name__)



router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

templates = Jinja2Templates(directory="templates")


@router.get("/candidates", response_class=HTMLResponse)
async def redirect_candidates_list(
    request: Request,
    db: Session = Depends(get_session),
):
    """Legacy alias: redirect the old /dashboard/candidates route to the kanban board."""
    return RedirectResponse(url="/dashboard/candidates/board", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/candidates/board", response_class=HTMLResponse)
async def get_candidate_board(
    request: Request,
    vacancy_id: Optional[int] = Query(None),
    db: Session = Depends(get_session),
):
    """Render the candidate kanban board while keeping the route compatible with omitted query params."""
    statement = select(CandidateApplication)
    if vacancy_id is not None:
        statement = statement.where(CandidateApplication.vacancy_id == vacancy_id)

    applications = db.exec(statement.order_by(CandidateApplication.created_at.desc())).all()

    ordered_stages = [
        CandidateStage.NEW,
        CandidateStage.SCREENED_BY_BOT,
        CandidateStage.INTERVIEW_SCHEDULED,
        CandidateStage.OFFERED,
        CandidateStage.REJECTED,
    ]
    stage_labels = {
        CandidateStage.NEW: "Yangi",
        CandidateStage.SCREENED_BY_BOT: "Bot tomonidan saralangan",
        CandidateStage.INTERVIEW_SCHEDULED: "Suhbat belgilangan",
        CandidateStage.OFFERED: "Taklif qilingan",
        CandidateStage.REJECTED: "Rad etilgan",
    }

    board = {stage.value: [] for stage in ordered_stages}
    unknown = []
    for app in applications:
        raw_stage = app.stage
        if raw_stage is None:
            stage = CandidateStage.NEW
        elif isinstance(raw_stage, CandidateStage):
            stage = raw_stage
        else:
            try:
                stage = CandidateStage(raw_stage)
            except ValueError:
                stage = None

        if stage is None:
            unknown.append({
                "id": app.id,
                "full_name": (db.get(User, app.user_id).full_name if db.get(User, app.user_id) else "Noma'lum nomzod"),
                "phone_number": (db.get(User, app.user_id).phone_number if db.get(User, app.user_id) else "-"),
                "vacancy_title": (db.get(Vacancy, app.vacancy_id).title if db.get(Vacancy, app.vacancy_id) else "-"),
                "created_at": app.created_at,
                "status": str(app.status),
            })
            continue

        app_data = {
            "id": app.id,
            "full_name": (db.get(User, app.user_id).full_name if db.get(User, app.user_id) else "Noma'lum nomzod"),
            "phone_number": (db.get(User, app.user_id).phone_number if db.get(User, app.user_id) else "-"),
            "vacancy_title": (db.get(Vacancy, app.vacancy_id).title if db.get(Vacancy, app.vacancy_id) else "-"),
            "created_at": app.created_at,
            "status": (app.status.value if hasattr(app.status, "value") else str(app.status)),
        }
        if stage.value not in board:
            board[stage.value] = []
        board[stage.value].append(app_data)

    board_payload = []
    for stage in ordered_stages:
        board_payload.append({
            "key": stage.value,
            "label": stage_labels.get(stage, stage.value.replace("_", " ").title()),
            "items": board.get(stage.value, []),
        })
    if unknown:
        board_payload.append({
            "key": "unknown",
            "label": "Noma'lum / yangi",
            "items": unknown,
        })

    return templates.TemplateResponse(
        request=request,
        name="candidate_board.html",
        context={
            "request": request,
            "board": board_payload,
            "vacancy_id": vacancy_id,
        },
    )


@router.get("/meetings", response_class=HTMLResponse)
async def get_meetings_page(
    request: Request,
    db: Session = Depends(get_session),
):
    """Render the meetings dashboard page without filtering out records by accidental user constraints."""
    meetings = db.exec(
        select(Meeting)
        .order_by(Meeting.scheduled_time.is_(None), Meeting.scheduled_time.asc())
    ).all()

    serialized = []
    for meeting in meetings:
        user = db.get(User, db.get(CandidateApplication, meeting.candidate_id).user_id) if db.get(CandidateApplication, meeting.candidate_id) else None
        candidate_name = user.full_name if user and user.full_name else "Noma'lum nomzod"
        vacancy = db.get(Vacancy, meeting.vacancy_id) if meeting.vacancy_id else None
        serialized.append({
            "id": meeting.id,
            "candidate_name": candidate_name,
            "vacancy_title": vacancy.title if vacancy else "-",
            "scheduled_time": meeting.scheduled_time or meeting.meeting_time,
            "status": str(meeting.status or "scheduled"),
        })

    return templates.TemplateResponse(
        request=request,
        name="meetings.html",
        context={
            "request": request,
            "meetings": serialized,
        },
    )


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
    sort_by: Optional[str] = None,
    stage: Optional[str] = None,
    db: Session = Depends(get_session),
):
    vacancy = db.get(Vacancy, vacancy_id)
    if not vacancy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Vacancy with id {vacancy_id} not found",
        )

    statement = select(CandidateApplication).where(CandidateApplication.vacancy_id == vacancy_id)
    if stage:
        statement = statement.where(CandidateApplication.pipeline_stage == stage)
        
    applications = db.exec(statement).all()

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
                "ai_score": application.ai_score if application.ai_score is not None else 0,
                "objective_score": application.objective_score if application.objective_score is not None else 0,
                "total_score": application.total_score if application.total_score is not None else 0,
                "pipeline_stage": application.pipeline_stage.value if hasattr(application.pipeline_stage, "value") else str(application.pipeline_stage),
                "user": user,
            }
        )

    # Sort candidates
    if sort_by == "score":
        candidates.sort(key=lambda x: x["total_score"], reverse=True)
    else:
        candidates.sort(key=lambda x: x["created_at"], reverse=True)

    return templates.TemplateResponse(
        request=request,
        name="candidate_list.html",
        context={
            "request": request,
            "vacancy": vacancy,
            "candidates": candidates,
            "sort_by": sort_by or "",
            "selected_stage": stage or "",
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

    vacancy = db.get(Vacancy, application.vacancy_id)
    if not vacancy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Vacancy for this application not found",
        )

    # Bundle questions and answers together so evaluate_candidate_answers can process them precisely
    answers_dict = {
        f"Q1 (Hard): {vacancy.generated_hard_skill_q1}": application.hard_skill_a1 or "Bo'sh",
        f"Q2 (Hard): {vacancy.generated_hard_skill_q2}": application.hard_skill_a2 or "Bo'sh",
        f"Q3 (Soft): {vacancy.generated_soft_skill_q1}": application.soft_skill_a1 or "Bo'sh",
        f"Q4 (Soft): {vacancy.generated_soft_skill_q2}": application.soft_skill_a2 or "Bo'sh",
    }

    try:
        # Call the existing function from llm_evaluator.py
        ai_result = await evaluate_candidate_answers(answers_dict)

        ai_score_val = int(ai_result.get("ai_score", 0))
        ai_feedback = ai_result.get("feedback", "Tahlil tugallanmadi.")

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"AI baholashda xatolik yuz berdi: {str(e)}"
        )

    # Update application records with AI scores and feedback
    application.ai_score = ai_score_val
    application.ai_reasoning = ai_feedback  # Saves the savage feedback so HR can view it
    application.total_score = (application.objective_score or 0) + ai_score_val
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
            "score": ai_score_val,
            "feedback": ai_feedback,
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


@router.post("/candidates/{candidate_id}/schedule")
async def schedule_candidate(
    candidate_id: int,
    payload: ScheduleRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_session)
):
    candidate = db.get(CandidateApplication, candidate_id)
    if not candidate:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nomzod topilmadi")

    user = db.get(User, candidate.user_id)
    telegram_id = getattr(candidate, "telegram_id", None) or (user.telegram_id if user else None)

    if not telegram_id:
        logger.error(f"Telegram ID is missing for Candidate ID {candidate_id}. Notification will not be sent.")

    # Robust Datetime Parsing
    try:
        if isinstance(payload.meeting_time, str):
            parsed_dt = datetime.fromisoformat(payload.meeting_time.replace("Z", "+00:00"))
        elif isinstance(payload.meeting_time, datetime):
            parsed_dt = payload.meeting_time
        else:
            parsed_dt = datetime.now(timezone.utc)
        if parsed_dt.tzinfo is None:
            parsed_dt = parsed_dt.replace(tzinfo=timezone.utc)
        meeting_time_str = parsed_dt.strftime("%Y-%m-%d %H:%M")
    except (ValueError, TypeError, AttributeError):
        parsed_dt = datetime.now(timezone.utc)
        meeting_time_str = str(payload.meeting_time)

    final_meeting_link = payload.meeting_link

    if payload.stage == "hr_online":
        candidate.pipeline_stage = PipelineStage.HR_ONLINE
        try:
            candidate_name = user.full_name if (user and user.full_name) else f"Nomzod #{candidate_id}"

            # Pass parsed_dt directly as datetime object
            zoom_data = await create_zoom_meeting(
                topic=f"HR Suhbat: {candidate_name}",
                start_time=parsed_dt
            )

            # Handle both dictionary and string return types
            if isinstance(zoom_data, dict):
                final_meeting_link = zoom_data.get("join_url") or zoom_data.get("start_url")
            elif isinstance(zoom_data, str):
                final_meeting_link = zoom_data
            else:
                final_meeting_link = str(zoom_data)

        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Zoom uchrashuvi yaratishda xatolik yuz berdi: {str(e)}"
            )

        if telegram_id:
            background_tasks.add_task(
                notify_candidate_status,
                telegram_id=telegram_id,
                msg_type="accept_1st_meeting",
                meeting_link_or_loc=final_meeting_link,
                meeting_time=meeting_time_str
            )

    elif payload.stage == "hr_offline":
        candidate.pipeline_stage = PipelineStage.HR_OFFLINE
        if telegram_id:
            background_tasks.add_task(
                notify_candidate_status,
                telegram_id=telegram_id,
                msg_type="accept_2nd_meeting",
                meeting_link_or_loc=final_meeting_link,
                meeting_time=meeting_time_str,
                branch_name=getattr(payload, "branch_name", None)
            )

    elif payload.stage == "director_offline":
        candidate.pipeline_stage = PipelineStage.DIRECTOR_OFFLINE
        if telegram_id:
            background_tasks.add_task(
                notify_candidate_status,
                telegram_id=telegram_id,
                msg_type="accept_boss_meeting",
                meeting_link_or_loc=final_meeting_link,
                meeting_time=meeting_time_str,
                branch_name=getattr(payload, "branch_name", None)
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Noto'g'ri bosqich tanlandi."
        )

    candidate.status = ApplicationStatus.PENDING
    db.add(candidate)

    new_meeting = Meeting(
        candidate_id=candidate.id,
        stage=candidate.pipeline_stage,
        meeting_time=parsed_dt,
        meeting_link=final_meeting_link,
        is_completed=False,
        reminders_sent=0,
    )
    db.add(new_meeting)
    db.commit()

    return {
        "status": "success",
        "message": f"Uchrashuv muvaffaqiyatli belgilandi ({payload.stage}).",
        "zoom_url": final_meeting_link if payload.stage == "hr_online" else None
    }


@router.post("/candidates/{candidate_id}/reject")
async def reject_candidate(
    candidate_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_session)
):
    candidate = db.get(CandidateApplication, candidate_id)
    if not candidate:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nomzod topilmadi")

    current_stage = str(candidate.pipeline_stage).upper() if candidate.pipeline_stage else ""
    msg_type = "cancel_initial" if current_stage in ["NEW", "TEST_SUBMITTED", "INITIAL", "YANGI", ""] else "cancel_after_meeting"

    candidate.status = ApplicationStatus.REJECTED
    candidate.pipeline_stage = PipelineStage.RAD_ETILDI
    db.add(candidate)
    db.commit()

    user = db.get(User, candidate.user_id)
    telegram_id = getattr(candidate, "telegram_id", None) or (user.telegram_id if user else None)

    if telegram_id:
        background_tasks.add_task(
            notify_candidate_status,
            telegram_id=telegram_id,
            msg_type=msg_type
        )
    else:
        logger.error(f"Telegram ID is missing for Candidate ID {candidate_id}. Rejection notification skipped.")

    return {
        "status": "success",
        "message": "Nomzod arizasi rad etildi."
    }

@router.post("/sync-sheets", response_class=JSONResponse)
async def sync_sheets_endpoint(
        db: Session = Depends(get_session)
):
    try:
        # Fetch all candidate applications
        applications = db.exec(select(CandidateApplication)).all()

        candidates_data = []
        for app in applications:
            # Resolve relational data for the sync payload
            user = db.get(User, app.user_id)
            vacancy = db.get(Vacancy, app.vacancy_id)

            # Format status safely based on Enum structure
            status_val = app.status.value if hasattr(app.status, "value") else str(app.status)

            candidates_data.append({
                "full_name": user.full_name if user and user.full_name else "Noma'lum nomzod",
                "phone_number": user.phone_number if user and user.phone_number else "-",
                "vacancy_title": vacancy.title if vacancy else "-",
                "base_score": app.objective_score or 0,
                "ai_score": app.ai_score or 0,
                "total_score": app.total_score or 0,
                "status": status_val
            })

        # Push to Google Sheets asynchronously
        synced_rows = await sync_candidates_to_sheet(candidates_data)

        return {
            "status": "success",
            "message": "Ma'lumotlar Google Sheets-ga muvaffaqiyatli sinxronizatsiya qilindi.",
            "synced_rows": synced_rows
        }

    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail="Google Sheets credentials topilmadi.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sinxronizatsiyada xatolik yuz berdi: {str(e)}")