from fastapi import APIRouter, Depends, HTTPException, status, Header
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from sqlmodel import Session, select

from db.database import get_session, engine
from db.models import Meeting, CandidateApplication, Vacancy, User, UserRole
from services.notifications import notify_candidate_status

router = APIRouter(prefix="/api/meetings", tags=["Meetings"])


class MeetingCreate(BaseModel):
    candidate_id: int
    vacancy_id: int
    meeting_time: datetime
    meeting_link: Optional[str] = None
    hr_chat_id: Optional[int] = None
    boss_chat_id: Optional[int] = None
    candidate_chat_id: Optional[int] = None
    status: Optional[str] = Field(default="scheduled")


class MeetingUpdate(BaseModel):
    meeting_time: Optional[datetime] = None
    meeting_link: Optional[str] = None
    hr_chat_id: Optional[int] = None
    boss_chat_id: Optional[int] = None
    candidate_chat_id: Optional[int] = None
    status: Optional[str] = None


# Simple dependency to resolve the current user from a request header.
# NOTE: This is a lightweight placeholder. In production replace with proper auth (OAuth/JWT/session).
def get_current_user(x_user_id: Optional[int] = Header(None), db: Session = Depends(get_session)) -> User:
    if not x_user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required (X-User-Id header missing)")
    user = db.get(User, int(x_user_id))
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


def require_hr_or_director(current_user: User = Depends(get_current_user)) -> User:
    role_val = getattr(current_user, 'role', None)
    # Normalize to uppercase for comparison (handles both enum values and raw strings)
    if hasattr(role_val, 'value'):
        role_str = role_val.value.upper()
    else:
        role_str = str(role_val).upper() if role_val is not None else ''

    if role_str not in (UserRole.HR.value, UserRole.DIRECTOR.value):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden: insufficient privileges")
    return current_user


@router.post("", status_code=status.HTTP_201_CREATED)
def create_meeting(payload: MeetingCreate, db: Session = Depends(get_session), current_user: User = Depends(require_hr_or_director)):
    # Validate candidate and vacancy
    app = db.get(CandidateApplication, payload.candidate_id)
    if not app:
        raise HTTPException(status_code=404, detail="Candidate application not found")
    vac = db.get(Vacancy, payload.vacancy_id)
    if not vac:
        raise HTTPException(status_code=404, detail="Vacancy not found")

    meeting = Meeting(
        candidate_id=payload.candidate_id,
        vacancy_id=payload.vacancy_id,
        meeting_time=payload.meeting_time,
        meeting_link=payload.meeting_link,
        hr_chat_id=payload.hr_chat_id,
        boss_chat_id=payload.boss_chat_id,
        candidate_chat_id=payload.candidate_chat_id,
        status=payload.status,
        is_completed=False,
        reminders_sent=0,
    )
    db.add(meeting)
    db.commit()
    db.refresh(meeting)

    return meeting


@router.put("/{meeting_id}")
def update_meeting(meeting_id: int, payload: MeetingUpdate, db: Session = Depends(get_session), current_user: User = Depends(require_hr_or_director)):
    meeting = db.get(Meeting, meeting_id)
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    updated = False
    for field, value in payload.dict(exclude_unset=True).items():
        setattr(meeting, field, value)
        updated = True

    if updated:
        db.add(meeting)
        db.commit()
        db.refresh(meeting)

    return meeting


@router.delete("/{meeting_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_meeting(meeting_id: int, db: Session = Depends(get_session), current_user: User = Depends(require_hr_or_director)):
    meeting = db.get(Meeting, meeting_id)
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    db.delete(meeting)
    db.commit()
    return {"status": "deleted"}
