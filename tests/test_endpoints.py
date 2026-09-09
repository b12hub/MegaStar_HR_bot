"""
test_endpoints.py
==================
Comprehensive pytest suite for:
    - api/portal.py     (HR Portal:      POST /hr/vacancies/create)
    - api/webapp.py      (Candidate Portal: /apply/*)
    - api/dashboard.py   (Dashboard:      /dashboard/*)

Run with:
    pytest test_endpoints.py -v

Design notes (read before extending)
-------------------------------------
1. DB isolation: a single in-memory SQLite engine (StaticPool, single shared
   connection) backs `get_session`. Tables are created/dropped around every
   single test function, so tests never see another test's data and never
   touch the real Postgres database.

2. Template rendering: `dashboard.py` and `webapp.py` both build
   `Jinja2Templates(directory="templates")` at import time and call
   `.TemplateResponse(request=..., name=..., context=..., status_code=...)`.
   Real template *files* are a front-end/rendering concern, not something
   these route-logic tests should depend on. We monkeypatch
   `Jinja2Templates.TemplateResponse` (a single patch point, since both
   modules import the exact same class from `fastapi.templating`) with a
   fake that (a) never touches disk, (b) returns a real HTMLResponse with
   the requested status code, and (c) records the `name`/`context` it was
   given so tests can assert on the *data* the route computed, which is the
   part that actually matters for backend QA.

3. External services: every outbound call (LLM evaluator, Zoom, Google
   Sheets, Telegram notifications) is patched with unittest.mock so tests
   run fully offline. Two import styles are patched deliberately:
     - Module-level imports (`from services.x import y` at the top of
       dashboard.py / webapp.py) are patched at `api.dashboard.y` /
       `api.webapp.y` ("patch where it's used").
     - The *local* imports inside `submit_candidate_application()` in
       webapp.py (`from services.scoring import calculate_objective_score`
       executed at call time) are patched at their *source*
       (`services.scoring.calculate_objective_score`), because a fresh
       import executes on every call and would otherwise bypass a patch
       applied to `api.webapp`.
   `webapp.process_async_candidate_evaluation` (a BackgroundTask) opens its
   own `Session(db.database.engine)` against the real engine -- it is
   replaced wholesale with an AsyncMock so background tasks never touch a
   real database during tests.

4. Two bugs were found via line-by-line review and are pinned with explicit
   regression tests rather than silently worked around:
     a. `dashboard.py` imports `select` from `sqlmodel` (line 4) and then
        re-imports it from `sqlalchemy` (line 8), silently shadowing the
        first. Because of this, `db.exec(select(Model))` in dashboard.py no
        longer auto-scalars, and most call sites compensate with an extra
        `.scalars()` -- except `get_meetings_page`, which forgot it. Any
        non-empty `meetings` table makes that endpoint crash with an
        AttributeError (returned as a 500 through the ASGI app).
     b. `create_vacancy_form` / `update_vacancy` auto-create a `Branch` via
        `Branch(name=branch_name, address=branch_name)`. `Branch` has no
        `address` column (silently dropped) and, critically, never
        supplies the *required* `region` / `location_url` fields, so
        creating a *brand-new* branch by name crashes with a
        pydantic ValidationError (500) instead of succeeding.
   These are marked `# BUG:` in the test names/docstrings below.
"""
import os
import sys
import contextlib
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.templating import Jinja2Templates
from fastapi.testclient import TestClient
from fastapi.responses import HTMLResponse
from sqlmodel import Session, SQLModel, create_engine, select
from sqlalchemy.pool import StaticPool

# --------------------------------------------------------------------------
# Defensive env-var fallbacks. Several imported modules (bot.main,
# services.zoom_service, services.google_sheets, db.database, ...) may read
# config from the environment at *import* time. These are harmless no-ops
# if the real project doesn't need them, and prevent an unrelated missing
# env var from blocking test collection. Adjust/remove for your project.
# --------------------------------------------------------------------------
os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/megastar_hr")
os.environ.setdefault("BOT_TOKEN", "8749115733:AAEx3xJxsXrFuak5kxlvSqSXFSCcliyb8pk")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "8749115733:AAEx3xJxsXrFuak5kxlvSqSXFSCcliyb8pk")
os.environ.setdefault("TELEGRAM_TOKEN", "8749115733:AAEx3xJxsXrFuak5kxlvSqSXFSCcliyb8pk")
os.environ.setdefault("OPENAI_API_KEY", "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")
os.environ.setdefault("ANTHROPIC_API_KEY", "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")
os.environ.setdefault("ZOOM_ACCOUNT_ID", "mXvHCfLtSRanATSkxXp5yw")
os.environ.setdefault("ZOOM_CLIENT_ID", "gDay83XKRQKEuvNtKeKqPA")
os.environ.setdefault("ZOOM_CLIENT_SECRET", "bGlb7ddQxYEVyQjOZkienmaugyyNyWCn")
os.environ.setdefault("GOOGLE_APPLICATION_CREDENTIALS", "credentials.json")
os.environ.setdefault("GOOGLE_SHEETS_ID", "16v-xAYrr1tKuicbypcIDjc9norfrVdh3CDDLRVxELGM")

sys.path.insert(0, os.getcwd())

from db.database import get_session  # noqa: E402
from db.models import (  # noqa: E402
    ApplicationStatus,
    Branch,
    CandidateApplication,
    CandidateStage,
    Education,
    JobOffer,
    LLMActionType,
    LLMUsageLog,
    Meeting,
    PipelineStage,
    User,
    UserRole,
    Vacancy,
    WorkExperience,
)
from api.dashboard import router as dashboard_router  # noqa: E402
from api.webapp import router as webapp_router  # noqa: E402
from api.portal import router as portal_router  # noqa: E402


# ==========================================================================
# Database setup: isolated in-memory SQLite engine, shared across sessions
# via StaticPool so all Session() instances (the app's and the test's) see
# the same data.
# ==========================================================================
engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


@pytest.fixture(scope="function", autouse=True)
def create_test_database():
    """Fresh schema before every test, dropped after -- full isolation."""
    SQLModel.metadata.create_all(engine)
    yield
    SQLModel.metadata.drop_all(engine)


@pytest.fixture()
def db_session():
    """A raw session for seeding data / asserting mutations directly."""
    with Session(engine) as session:
        yield session


# ==========================================================================
# App under test
# ==========================================================================
app = FastAPI()
app.include_router(dashboard_router)
app.include_router(webapp_router)
app.include_router(portal_router)


@pytest.fixture(scope="session", autouse=True)
def override_get_session_dependency():
    """Swap the real `get_session` dependency for one bound to the test
    engine, so no route in the app ever touches PostgreSQL."""

    def _get_session_override():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = _get_session_override
    yield
    app.dependency_overrides.clear()


@pytest.fixture()
def client():
    return TestClient(app)


@pytest.fixture()
def client_no_raise():
    """A client that returns 5xx responses instead of re-raising server
    exceptions -- used for the two bug-reproduction tests."""
    return TestClient(app, raise_server_exceptions=False)


# ==========================================================================
# Template rendering stub (see module docstring, point 2).
# ==========================================================================
def _fake_template_response(self, *args, request=None, name=None, context=None,
                             status_code=200, **kwargs):
    ctx = context or {}
    _fake_template_response.calls.append({"name": name, "context": ctx, "status_code": status_code})
    return HTMLResponse(content=f"<html data-template='{name}'></html>", status_code=status_code)


_fake_template_response.calls = []


@pytest.fixture(autouse=True)
def template_calls(monkeypatch):
    _fake_template_response.calls = []
    monkeypatch.setattr(Jinja2Templates, "TemplateResponse", _fake_template_response)
    yield _fake_template_response.calls


# ==========================================================================
# External-service mocking (see module docstring, point 3).
# ==========================================================================
@pytest.fixture(autouse=True)
def mock_external_services():
    with contextlib.ExitStack() as stack:
        m = SimpleNamespace(
            # dashboard.py module-level imports
            dash_evaluate=stack.enter_context(patch("api.dashboard.evaluate_candidate_answers", new_callable=AsyncMock)),
            dash_generate_vq=stack.enter_context(patch("api.dashboard.generate_vacancy_questions", new_callable=AsyncMock)),
            dash_zoom=stack.enter_context(patch("api.dashboard.create_zoom_meeting", new_callable=AsyncMock)),
            dash_sync_sheets=stack.enter_context(patch("api.dashboard.sync_candidates_to_sheet", new_callable=AsyncMock)),
            dash_notify_status=stack.enter_context(patch("api.dashboard.notify_candidate_status", new_callable=AsyncMock)),
            dash_notify_offer=stack.enter_context(patch("api.dashboard.notify_candidate_job_offer", new_callable=AsyncMock)),
            dash_notify_director=stack.enter_context(patch("api.dashboard.notify_director_on_third_stage", new_callable=AsyncMock)),
            dash_notify_pm=stack.enter_context(patch("api.dashboard.notify_branch_pm_on_job_offer", new_callable=AsyncMock)),
            dash_notify_meeting=stack.enter_context(patch("api.dashboard.notify_hr_meeting_scheduled", new_callable=AsyncMock)),
            # webapp.py module-level imports
            webapp_evaluate=stack.enter_context(patch("api.webapp.evaluate_candidate_answers", new_callable=AsyncMock)),
            webapp_calc_score=stack.enter_context(patch("api.webapp.calculate_objective_score")),
            webapp_notify_hr=stack.enter_context(patch("api.webapp.notify_hr_new_application", new_callable=AsyncMock)),
            webapp_bg_eval=stack.enter_context(patch("api.webapp.process_async_candidate_evaluation", new_callable=AsyncMock)),
            # webapp.submit_candidate_application() re-imports these locally
            # at call time -> must patch the source module, not api.webapp.
            svc_calc_score=stack.enter_context(patch("services.scoring.calculate_objective_score")),
            svc_evaluate=stack.enter_context(patch("services.llm_evaluator.evaluate_candidate_answers", new_callable=AsyncMock)),
            # portal.py module-level import
            portal_generate_vq=stack.enter_context(patch("api.portal.generate_vacancy_questions", new_callable=AsyncMock)),
        )

        # sensible defaults
        vq_result = {
            "questions": {
                "hard_skill_q1": "Sizningcha CRM tizimlari qanday ishlaydi?",
                "hard_skill_q2": "Savdo hisobotini qanday tuzasiz?",
                "soft_skill_q1": "Qiyin mijoz bilan qanday ishlaysiz?",
                "soft_skill_q2": "Jamoada ziddiyatni qanday hal qilasiz?",
            },
            "tokens_input": 120,
            "tokens_output": 80,
            "cost_usd": 0.015,
        }
        m.dash_generate_vq.return_value = vq_result
        m.portal_generate_vq.return_value = vq_result
        m.dash_evaluate.return_value = {"ai_score": 8, "feedback": "Yaxshi javoblar."}
        m.webapp_evaluate.return_value = {"ai_score": 7, "feedback": "Qoniqarli."}
        m.svc_evaluate.return_value = {"ai_score": 7, "feedback": "Qoniqarli."}
        m.webapp_calc_score.return_value = 5
        m.svc_calc_score.return_value = 5
        m.dash_zoom.return_value = {"join_url": "https://zoom.example.com/j/123456"}
        m.dash_sync_sheets.return_value = 3

        yield m


# ==========================================================================
# Cascading data fixtures (foreign keys satisfied bottom-up)
# ==========================================================================
@pytest.fixture()
def seed_branch(db_session):
    branch = Branch(
        name="Chilonzor filiali",
        region="Toshkent",
        location_url="https://maps.example.com/chilonzor",
        is_active=True,
    )
    db_session.add(branch)
    db_session.commit()
    db_session.refresh(branch)
    return branch


@pytest.fixture()
def seed_vacancy(db_session, seed_branch):
    vacancy = Vacancy(
        title="Sotuv menejeri",
        department="Savdo",
        description="Do'kon uchun tajribali sotuv menejeri talab etiladi.",
        branch_id=seed_branch.id,
        is_active=True,
    )
    db_session.add(vacancy)
    db_session.commit()
    db_session.refresh(vacancy)
    return vacancy


@pytest.fixture()
def seed_user(db_session):
    user = User(
        telegram_id=123456789,
        telegram_username="vali_aliyev",
        full_name="Aliyev Vali",
        phone_number="+998901234567",
        role=UserRole.CANDIDATE.value,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture()
def seed_application(db_session, seed_vacancy, seed_branch, seed_user):
    application = CandidateApplication(
        user_id=seed_user.id,
        vacancy_id=seed_vacancy.id,
        branch_id=seed_branch.id,
        status=ApplicationStatus.PENDING,
        stage=CandidateStage.NEW,
        pipeline_stage=PipelineStage.YANGI,
        objective_score=5,
        ai_score=None,
        total_score=5,
        hard_skill_a1="Python asoslari",
        hard_skill_a2="SQL so'rovlari",
        soft_skill_a1="Jamoada ishlash",
        soft_skill_a2="Vaqtni boshqarish",
    )
    db_session.add(application)
    db_session.commit()
    db_session.refresh(application)
    return application


@pytest.fixture()
def seed_meeting(db_session, seed_application):
    meeting = Meeting(
        candidate_id=seed_application.id,
        vacancy_id=seed_application.vacancy_id,
        meeting_time=datetime.now(timezone.utc) + timedelta(days=1),
        meeting_link="https://zoom.example.com/j/999999",
        status="scheduled",
        stage=PipelineStage.HR_ONLINE,
        is_completed=False,
    )
    db_session.add(meeting)
    db_session.commit()
    db_session.refresh(meeting)
    return meeting


@pytest.fixture()
def seed_job_offer(db_session, seed_application):
    offer = JobOffer(
        candidate_id=seed_application.id,
        starting_salary="5,000,000 so'm",
        work_days="Dushanba - Juma",
        work_hours="09:00-18:00",
        start_datetime=datetime.now(timezone.utc) + timedelta(days=7),
        location="Chilonzor filiali",
    )
    db_session.add(offer)
    db_session.commit()
    db_session.refresh(offer)
    return offer


# ==========================================================================
# api/portal.py -- POST /hr/vacancies/create
# ==========================================================================
class TestPortalCreateVacancy:
    def test_create_vacancy_happy_path(self, client, db_session, seed_branch, mock_external_services):
        payload = {
            "title": "Backend dasturchi",
            "department": "IT",
            "description": "Python/FastAPI tajribasi bo'lgan dasturchi kerak.",
            "branch_id": seed_branch.id,
        }
        response = client.post("/hr/vacancies/create", json=payload)

        assert response.status_code == 201
        body = response.json()
        assert body["vacancy"]["title"] == "Backend dasturchi"
        assert body["vacancy"]["branch_id"] == seed_branch.id
        assert body["generated_questions"]["hard_skill_q1"]
        assert body["llm_cost_usd"] == pytest.approx(0.015)

        # DB mutation checks
        vacancy_id = body["vacancy"]["id"]
        vacancy = db_session.get(Vacancy, vacancy_id)
        assert vacancy is not None
        assert vacancy.llm_cost_usd == pytest.approx(0.015)

        usage_logs = db_session.exec(select(LLMUsageLog)).all()
        assert len(usage_logs) == 1
        assert usage_logs[0].action_type == LLMActionType.VACANCY_GEN
        assert usage_logs[0].cost_usd == pytest.approx(0.015)

        mock_external_services.portal_generate_vq.assert_awaited_once()

    def test_create_vacancy_branch_not_found_returns_404(self, client, mock_external_services):
        payload = {
            "title": "Backend dasturchi",
            "department": "IT",
            "description": "Tavsif",
            "branch_id": 999999,
        }
        response = client.post("/hr/vacancies/create", json=payload)

        assert response.status_code == 404
        assert "not found" in response.json()["detail"]
        mock_external_services.portal_generate_vq.assert_not_awaited()

    def test_create_vacancy_missing_required_field_returns_422(self, client):
        # `title` is required by VacancyCreateRequest and is omitted.
        payload = {
            "department": "IT",
            "description": "Tavsif",
            "branch_id": 1,
        }
        response = client.post("/hr/vacancies/create", json=payload)
        assert response.status_code == 422


# ==========================================================================
# api/webapp.py -- Candidate Portal
# ==========================================================================
class TestGetCascadeData:
    def test_get_cascade_data_groups_branch_ids_by_title(self, client, db_session, seed_branch):
        """Two active vacancies sharing a title should collapse into one
        cascade entry whose branch_ids list contains both branches."""
        second_branch = Branch(name="Yunusobod filiali", region="Toshkent",
                                location_url="https://maps.example.com/yunusobod")
        db_session.add(second_branch)
        db_session.commit()
        db_session.refresh(second_branch)

        v1 = Vacancy(title="Sotuv menejeri", department="Savdo", description="d",
                      branch_id=seed_branch.id, is_active=True)
        v2 = Vacancy(title="Sotuv menejeri", department="Savdo", description="d",
                      branch_id=second_branch.id, is_active=True)
        inactive = Vacancy(title="Yopiq lavozim", department="Savdo", description="d",
                            branch_id=seed_branch.id, is_active=False)
        db_session.add_all([v1, v2, inactive])
        db_session.commit()

        response = client.get("/apply/data")

        assert response.status_code == 200
        body = response.json()
        assert len(body["vacancies"]) == 1  # deduped by title
        assert sorted(body["vacancies"][0]["branch_ids"]) == sorted([seed_branch.id, second_branch.id])
        assert {b["id"] for b in body["branches"]} == {seed_branch.id, second_branch.id}
        assert all(v["title"] != "Yopiq lavozim" for v in body["vacancies"])

    def test_get_cascade_data_empty_state(self, client):
        response = client.get("/apply/data")
        assert response.status_code == 200
        assert response.json() == {"vacancies": [], "branches": []}


class TestShowPortal:
    def test_show_portal_happy_path(self, client, seed_vacancy, template_calls):
        response = client.get("/apply/portal")
        assert response.status_code == 200

        rendered = next(c for c in template_calls if c["name"] == "portal.html")
        assert len(rendered["context"]["vacancies"]) == 1
        assert rendered["context"]["vacancies"][0].id == seed_vacancy.id
        assert "Toshkent" in rendered["context"]["regions"]
        assert "Savdo" in rendered["context"]["departments"]

    def test_show_portal_empty_state(self, client, template_calls):
        response = client.get("/apply/portal")
        assert response.status_code == 200
        rendered = next(c for c in template_calls if c["name"] == "portal.html")
        assert rendered["context"]["vacancies"] == []


class TestShowVacancyDetail:
    def test_show_vacancy_detail_happy_path(self, client, seed_vacancy, template_calls):
        response = client.get(f"/apply/vacancy/{seed_vacancy.id}")
        assert response.status_code == 200
        rendered = next(c for c in template_calls if c["name"] == "vacancy_public_detail.html")
        assert rendered["context"]["vacancy"].id == seed_vacancy.id

    def test_show_vacancy_detail_not_found_returns_404(self, client, template_calls):
        response = client.get("/apply/vacancy/999999")
        assert response.status_code == 404
        rendered = next(c for c in template_calls if c["name"] == "error.html")
        assert rendered["status_code"] == 404

    def test_show_vacancy_detail_inactive_returns_404(self, client, db_session, seed_vacancy):
        seed_vacancy.is_active = False
        db_session.add(seed_vacancy)
        db_session.commit()

        response = client.get(f"/apply/vacancy/{seed_vacancy.id}")
        assert response.status_code == 404


class TestServeIntakeForm:
    def test_serve_intake_form_happy_path(self, client, seed_vacancy, template_calls):
        response = client.get(f"/apply/{seed_vacancy.id}")
        assert response.status_code == 200
        rendered = next(c for c in template_calls if c["name"] == "apply.html")
        assert rendered["context"]["vacancy"].id == seed_vacancy.id

    def test_serve_intake_form_not_found_returns_404(self, client):
        response = client.get("/apply/999999")
        assert response.status_code == 404


class TestSubmitCandidateApplicationJson:
    """POST /apply/submit -- JSON intake, creates User + Application +
    WorkExperience + Education rows, scores synchronously."""

    def _payload(self, vacancy_id, branch_id, **overrides):
        payload = {
            "full_name": "Aliyev Vali",
            "phone_number": "+998901234567",
            "telegram_id": 555111222,
            "telegram_username": "vali_aliyev",
            "birth_date": "1998-05-12",
            "gender": "male",
            "languages": ["uz", "ru"],
            "pc_skills": ["Excel", "Word"],
            "vacancy_id": vacancy_id,
            "branch_id": branch_id,
            "experience": [
                {"company_name": "ABC LLC", "position": "Sotuvchi",
                 "start_date": "2020-01-01", "end_date": "2022-01-01",
                 "description": "Chakana savdo"}
            ],
            "education": [
                {"institution": "TDIU", "degree": "Bakalavr",
                 "field_of_study": "Iqtisodiyot", "graduation_year": 2019}
            ],
            "hard_skill_a1": "Python asoslari",
            "hard_skill_a2": "SQL so'rovlari",
            "soft_skill_a1": "Jamoada ishlash",
            "soft_skill_a2": "Vaqtni boshqarish",
        }
        payload.update(overrides)
        return payload

    def test_submit_candidate_application_happy_path(self, client, db_session, seed_vacancy,
                                                       seed_branch, mock_external_services):
        response = client.post("/apply/submit", json=self._payload(seed_vacancy.id, seed_branch.id))

        assert response.status_code == 201
        body = response.json()
        assert body["success"] is True
        assert body["application_id"] > 0

        application = db_session.get(CandidateApplication, body["application_id"])
        assert application is not None
        assert application.status == ApplicationStatus.PENDING
        assert application.vacancy_id == seed_vacancy.id
        assert application.branch_id == seed_branch.id
        assert application.ai_score == 7
        assert application.objective_score == 5
        assert application.total_score == 12

        work_experiences = db_session.exec(
            select(WorkExperience).where(WorkExperience.application_id == application.id)
        ).all()
        educations = db_session.exec(
            select(Education).where(Education.application_id == application.id)
        ).all()
        assert len(work_experiences) == 1
        assert work_experiences[0].company_name == "ABC LLC"
        assert len(educations) == 1
        assert educations[0].institution == "TDIU"

        created_user = db_session.exec(select(User).where(User.telegram_id == 555111222)).first()
        assert created_user is not None
        assert created_user.full_name == "Aliyev Vali"

        mock_external_services.svc_evaluate.assert_awaited_once()
        mock_external_services.svc_calc_score.assert_called_once()

    def test_submit_candidate_application_vacancy_not_found_returns_404(self, client, seed_branch):
        response = client.post("/apply/submit", json=self._payload(999999, seed_branch.id))
        assert response.status_code == 404
        assert "Vacancy" in response.json()["detail"]

    def test_submit_candidate_application_branch_not_found_returns_404(self, client, seed_vacancy):
        response = client.post("/apply/submit", json=self._payload(seed_vacancy.id, 999999))
        assert response.status_code == 404
        assert "Branch" in response.json()["detail"]

    def test_submit_candidate_application_missing_required_field_returns_422(self, client, seed_vacancy, seed_branch):
        payload = self._payload(seed_vacancy.id, seed_branch.id)
        del payload["full_name"]
        response = client.post("/apply/submit", json=payload)
        assert response.status_code == 422


class TestSubmitIntakeFormMultipart:
    """POST /apply/{vacancy_id} -- multipart/form-data intake. Does NOT
    create WorkExperience/Education rows (experience_json/education_json
    are accepted as parameters but never parsed/persisted -- verified by
    reading the route body)."""

    def test_submit_intake_form_happy_path(self, client, db_session, seed_vacancy,
                                            seed_branch, mock_external_services):
        form_data = {
            "full_name": "Karimova Nodira",
            "phone_number": "+998977654321",
            "branch_id": str(seed_branch.id),
            "email": "nodira@example.com",
            "why_you": "Men mas'uliyatli va tez o'rganuvchanman.",
            "hard_skill_a1": "Excel",
            "hard_skill_a2": "1C",
            "accept_offer": "ha",
        }
        response = client.post(f"/apply/{seed_vacancy.id}", data=form_data)

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        application_id = body["application_id"]

        application = db_session.get(CandidateApplication, application_id)
        assert application is not None
        assert application.status == ApplicationStatus.PENDING
        assert application.accept_offer is True
        assert application.branch_id == seed_branch.id

        work_experiences = db_session.exec(
            select(WorkExperience).where(WorkExperience.application_id == application.id)
        ).all()
        assert work_experiences == []  # confirmed dead field, not persisted

        mock_external_services.webapp_calc_score.assert_called_once()
        mock_external_services.webapp_bg_eval.assert_called_once()
        mock_external_services.webapp_notify_hr.assert_called_once()

    def test_submit_intake_form_vacancy_not_found_returns_404(self, client, seed_branch):
        response = client.post(
            "/apply/999999",
            data={"full_name": "Test User", "phone_number": "+998900000000",
                  "branch_id": str(seed_branch.id)},
        )
        assert response.status_code == 404

    def test_submit_intake_form_missing_required_field_returns_422(self, client, seed_vacancy, seed_branch):
        # `phone_number` is a required Form(...) field.
        response = client.post(
            f"/apply/{seed_vacancy.id}",
            data={"full_name": "Test User", "branch_id": str(seed_branch.id)},
        )
        assert response.status_code == 422


# class TestCheckApplicationStatus:
#     def test_check_status_applied_with_meeting(self, client, seed_user, seed_vacancy, seed_application, seed_meeting):
#         # Change URL to match path parameter if your app uses /apply/{vacancy_id}/status
#         response = client.get(
#             f"/apply/{seed_vacancy.id}/status",
#             params={"telegram_id": seed_user.telegram_id},
#         )
#         assert response.status_code == 200
#         body = response.json()
#         assert body["applied"] is True
#         assert body.get("stage") is not None
#         assert body.get("meeting") is not None
#         assert body["meeting"]["link"] == seed_meeting.meeting_link
#
#     def test_check_status_not_applied_returns_false(self, client):
#         response = client.get(
#             "/apply/1/status",
#             params={"telegram_id": 5375706608},
#         )
#         assert response.status_code == 200
#         assert response.json() == {"applied": False}
#
#     def test_check_status_missing_required_query_params_returns_422(self, client):
#         response = client.get("/apply/1/status")
#         assert response.status_code == 422

# ==========================================================================
# api/dashboard.py
# ==========================================================================
class TestDashboardNotifications:
    def test_get_notifications_happy_path(self, client, seed_application):
        response = client.get("/dashboard/api/notifications")
        assert response.status_code == 200
        body = response.json()
        assert len(body) >= 1
        assert body[0]["type"] == "new_application"

    def test_get_notifications_empty_state(self, client):
        response = client.get("/dashboard/api/notifications")
        assert response.status_code == 200
        assert response.json() == []


class TestCandidatesList:
    def test_get_candidates_list_happy_path(self, client, seed_application, template_calls):
        response = client.get("/dashboard/candidates")
        assert response.status_code == 200
        rendered = next(c for c in template_calls if c["name"] == "candidates.html")
        rows = rendered["context"]["candidates"]
        assert len(rows) == 1
        assert rows[0]["full_name"] == "Aliyev Vali"
        assert rows[0]["status_label"] == "Kutilmoqda"

    def test_get_candidates_list_empty_state(self, client, template_calls):
        response = client.get("/dashboard/candidates")
        assert response.status_code == 200
        rendered = next(c for c in template_calls if c["name"] == "candidates.html")
        assert rendered["context"]["candidates"] == []


class TestCandidateBoard:
    def test_get_candidate_board_groups_by_stage(self, client, db_session, seed_application, template_calls):
        seed_application.stage = CandidateStage.NEW
        db_session.add(seed_application)

        second_app = CandidateApplication(
            user_id=seed_application.user_id,
            vacancy_id=seed_application.vacancy_id,
            branch_id=seed_application.branch_id,
            status=ApplicationStatus.PENDING,
            stage=CandidateStage.INTERVIEW_SCHEDULED,
            pipeline_stage=PipelineStage.HR_ONLINE,
        )
        db_session.add(second_app)
        db_session.commit()

        response = client.get("/dashboard/candidates/board")
        assert response.status_code == 200
        rendered = next(c for c in template_calls if c["name"] == "candidates.html")
        board = {col["key"]: col["items"] for col in rendered["context"]["board"]}
        assert len(board[CandidateStage.NEW.value]) == 1
        assert len(board[CandidateStage.INTERVIEW_SCHEDULED.value]) == 1

    def test_get_candidate_board_filters_by_vacancy_id(self, client, seed_application):
        response = client.get("/dashboard/candidates/board", params={"vacancy_id": seed_application.vacancy_id})
        assert response.status_code == 200

    def test_get_candidate_board_invalid_vacancy_id_returns_422(self, client):
        response = client.get("/dashboard/candidates/board", params={"vacancy_id": "not-an-int"})
        assert response.status_code == 422


class TestMeetingsPage:
    """BUG: `get_meetings_page` runs `db.exec(select(Meeting)).all()`
    without `.scalars()`. Because dashboard.py's `select` is shadowed by
    `sqlalchemy.select` (see module docstring), this returns raw `Row`
    objects instead of `Meeting` instances, and the very next line
    (`meeting.meeting_link`) raises AttributeError on any non-empty
    `meetings` table. The empty-table case never enters the loop, so it
    "works" -- which is exactly how this kind of bug hides in manual QA."""

    def test_get_meetings_page_empty_returns_200(self, client):
        response = client.get("/dashboard/meetings")
        assert response.status_code == 200

    def test_get_meetings_page_with_seeded_meeting_returns_500_bug(self, client_no_raise, seed_meeting):
        response = client_no_raise.get("/dashboard/meetings")
        assert response.status_code == 500


class TestHrDashboard:
    def test_get_hr_dashboard_happy_path(self, client, db_session, seed_application, seed_meeting, template_calls):
        response = client.get("/dashboard/hr")
        assert response.status_code == 200
        rendered = next(c for c in template_calls if c["name"] == "hr_dashboard.html")
        ctx = rendered["context"]
        assert ctx["total_candidates"] == 1
        assert ctx["pending_candidates"] == 1
        assert ctx["active_vacancies_count"] == 1
        assert ctx["scheduled_meetings"] == 1

    def test_get_hr_dashboard_empty_state(self, client, template_calls):
        response = client.get("/dashboard/hr")
        assert response.status_code == 200
        rendered = next(c for c in template_calls if c["name"] == "hr_dashboard.html")
        assert rendered["context"]["total_candidates"] == 0


class TestVacancyNewPage:
    def test_new_vacancy_page_happy_path(self, client, seed_branch, template_calls):
        response = client.get("/dashboard/vacancies/new")
        assert response.status_code == 200
        rendered = next(c for c in template_calls if c["name"] == "vacancy_create.html")
        assert len(rendered["context"]["branches"]) == 1


class TestCreateVacancyForm:
    def test_create_vacancy_form_with_existing_branch_id_happy_path(self, client, db_session, seed_branch,
                                                                      mock_external_services):
        form_data = {
            "title": "Frontend dasturchi",
            "department": "IT",
            "description": "React tajribasi bo'lishi kerak.",
            "branch_id": str(seed_branch.id),
            "reports_to": "IT Direktori",
            "duties_responsibilities": "UI komponentlarini yozish",
            "required_qualifications": "2+ yil tajriba",
        }
        response = client.post("/dashboard/vacancies/new", data=form_data)

        assert response.status_code in (200, 303)
        if "location" in response.headers:
            assert response.headers["location"] == "/dashboard/hr"

        vacancies = db_session.exec(select(Vacancy).where(Vacancy.title == "Frontend dasturchi")).all()
        assert len(vacancies) == 1
        assert vacancies[0].branch_id == seed_branch.id
        assert vacancies[0].llm_cost_usd == pytest.approx(0.015)
        mock_external_services.dash_generate_vq.assert_awaited_once()

    def test_create_vacancy_form_missing_required_field_returns_422(self, client):
        response = client.post("/dashboard/vacancies/new", data={"department": "IT", "description": "x"})
        assert response.status_code == 422

    def test_create_vacancy_form_new_branch_name_returns_500_bug(self, client_no_raise, mock_external_services):
        """BUG: auto-creating a brand-new Branch via
        `Branch(name=branch_name, address=branch_name)` never supplies the
        required `region` / `location_url` fields (and `address` isn't a
        real column at all), so this raises a pydantic ValidationError
        before the vacancy is ever created."""
        form_data = {
            "title": "Ombor mudiri",
            "department": "Logistika",
            "description": "Yangi filial uchun ombor mudiri.",
            "branch": "Mutlaqo Yangi Filial",
        }
        response = client_no_raise.post("/dashboard/vacancies/new", data=form_data)
        assert response.status_code == 500


class TestVacancyDetail:
    def test_get_vacancy_detail_happy_path(self, client, seed_vacancy, template_calls):
        response = client.get(f"/dashboard/vacancies/{seed_vacancy.id}")
        assert response.status_code == 200
        rendered = next(c for c in template_calls if c["name"] == "vacancy_detail.html")
        assert rendered["context"]["vacancy"].id == seed_vacancy.id

    def test_get_vacancy_detail_not_found_returns_404(self, client):
        response = client.get("/dashboard/vacancies/999999")
        assert response.status_code == 404


class TestVacancyCandidates:
    def test_get_vacancy_candidates_sorted_by_score(self, client, db_session, seed_vacancy, seed_branch,
                                                      seed_application, template_calls):
        low_score_user = User(full_name="Past ball", phone_number="+998900000001", role="candidate")
        db_session.add(low_score_user)
        db_session.commit()
        db_session.refresh(low_score_user)

        low_score_app = CandidateApplication(
            user_id=low_score_user.id, vacancy_id=seed_vacancy.id, branch_id=seed_branch.id,
            status=ApplicationStatus.PENDING, total_score=1,
        )
        db_session.add(low_score_app)
        db_session.commit()

        response = client.get(f"/dashboard/vacancies/{seed_vacancy.id}/candidates", params={"sort_by": "score"})
        assert response.status_code == 200
        rendered = next(c for c in template_calls if c["name"] == "candidate_list.html")
        candidates = rendered["context"]["candidates"]
        assert len(candidates) == 2
        assert candidates[0]["total_score"] >= candidates[1]["total_score"]

    def test_get_vacancy_candidates_not_found_returns_404(self, client):
        response = client.get("/dashboard/vacancies/999999/candidates")
        assert response.status_code == 404


class TestCandidateDetail:
    def test_get_candidate_detail_happy_path(self, client, seed_application, template_calls):
        response = client.get(f"/dashboard/candidates/{seed_application.id}")
        assert response.status_code == 200
        rendered = next(c for c in template_calls if c["name"] == "candidate_detail.html")
        assert rendered["context"]["candidate"].id == seed_application.id

    def test_get_candidate_detail_not_found_returns_404(self, client):
        response = client.get("/dashboard/candidates/999999")
        assert response.status_code == 404


class TestEvaluateCandidate:
    def test_evaluate_candidate_happy_path(self, client, db_session, seed_application, mock_external_services):
        response = client.post(f"/dashboard/candidates/{seed_application.id}/evaluate")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "success"
        assert body["score"] == 8

        db_session.refresh(seed_application)
        assert seed_application.ai_score == 8
        assert seed_application.total_score == seed_application.objective_score + 8
        mock_external_services.dash_evaluate.assert_awaited_once()

    def test_evaluate_candidate_not_found_returns_404(self, client):
        response = client.post("/dashboard/candidates/999999/evaluate")
        assert response.status_code == 404

    def test_evaluate_candidate_llm_failure_returns_500(self, client, seed_application, mock_external_services):
        mock_external_services.dash_evaluate.side_effect = RuntimeError("LLM timeout")
        response = client.post(f"/dashboard/candidates/{seed_application.id}/evaluate")
        assert response.status_code == 500


class TestToggleVacancyStatus:
    def test_toggle_vacancy_status_happy_path(self, client, db_session, seed_vacancy):
        assert seed_vacancy.is_active is True
        response = client.post(f"/dashboard/vacancies/{seed_vacancy.id}/toggle")
        assert response.status_code in (200, 303)
        if "location" in response.headers:
            assert response.headers["location"] == "/dashboard/hr"

        db_session.refresh(seed_vacancy)
        assert seed_vacancy.is_active is False

    def test_toggle_vacancy_status_not_found_returns_404(self, client):
        response = client.post("/dashboard/vacancies/999999/toggle")
        assert response.status_code == 404


class TestEditVacancyPage:
    def test_edit_vacancy_page_happy_path(self, client, seed_vacancy, template_calls):
        response = client.get(f"/dashboard/vacancies/{seed_vacancy.id}/edit")
        assert response.status_code == 200
        rendered = next(c for c in template_calls if c["name"] == "vacancy_edit.html")
        assert rendered["context"]["vacancy"].id == seed_vacancy.id

    def test_edit_vacancy_page_not_found_returns_404(self, client):
        response = client.get("/dashboard/vacancies/999999/edit")
        assert response.status_code == 404


class TestUpdateVacancy:
    def test_update_vacancy_manual_overwrite_happy_path(self, client, db_session, seed_vacancy):
        form_data = {
            "title": "Sotuv menejeri (yangilangan)",
            "department": "Savdo",
            "description": "Yangilangan tavsif",
            "work_hours": "09:00 - 18:00",
            "is_active": "true",
            "generated_hard_skill_q1": "Qo'lda kiritilgan savol 1",
        }
        response = client.post(f"/dashboard/vacancies/{seed_vacancy.id}/edit", data=form_data)
        assert response.status_code in (200, 303)
        if "location" in response.headers:
            assert response.headers["location"] == "/dashboard/hr"

        db_session.refresh(seed_vacancy)
        assert seed_vacancy.title == "Sotuv menejeri (yangilangan)"
        assert seed_vacancy.work_hours == "09:00 - 18:00"
        assert seed_vacancy.is_active is True
        assert seed_vacancy.generated_hard_skill_q1 == "Qo'lda kiritilgan savol 1"

    def test_update_vacancy_regenerate_ai_happy_path(self, client, db_session, seed_vacancy, mock_external_services):
        form_data = {
            "title": seed_vacancy.title,
            "department": seed_vacancy.department,
            "description": seed_vacancy.description,
            "regenerate_ai": "true",
            "custom_ai_prompt": "Savdo bo'yicha ko'proq texnik savollar ber",
        }
        response = client.post(f"/dashboard/vacancies/{seed_vacancy.id}/edit", data=form_data)
        assert response.status_code in (200, 303)

        mock_external_services.dash_generate_vq.assert_awaited_once()
        _, kwargs = mock_external_services.dash_generate_vq.call_args
        assert kwargs.get("custom_prompt") == "Savdo bo'yicha ko'proq texnik savollar ber"

        db_session.refresh(seed_vacancy)
        assert seed_vacancy.llm_cost_usd == pytest.approx(0.015)

    def test_update_vacancy_not_found_returns_404(self, client):
        response = client.post(
            "/dashboard/vacancies/999999/edit",
            data={"title": "x", "department": "x", "description": "x"},
        )
        assert response.status_code == 404


class TestDeleteVacancy:
    def test_delete_vacancy_cascades_related_rows(self, client, db_session, seed_vacancy, seed_application,
                                                  seed_meeting, seed_job_offer):
        work_exp = WorkExperience(application_id=seed_application.id, company_name="X", position="Y")
        education = Education(application_id=seed_application.id, institution="Z")
        db_session.add_all([work_exp, education])
        db_session.commit()

        # Save IDs as local variables before deletion to prevent ObjectDeletedError
        vacancy_id = seed_vacancy.id
        app_id = seed_application.id

        response = client.post(f"/dashboard/vacancies/{vacancy_id}/delete")
        assert response.status_code in (200, 303)
        if "location" in response.headers:
            assert response.headers["location"] == "/dashboard/hr"

        # Query using the raw integer IDs
        assert db_session.exec(select(Vacancy).where(Vacancy.id == vacancy_id)).first() is None
        assert db_session.exec(select(CandidateApplication).where(CandidateApplication.id == app_id)).first() is None
        assert db_session.exec(select(Meeting).where(Meeting.candidate_id == app_id)).all() == []
        assert db_session.exec(select(JobOffer).where(JobOffer.candidate_id == app_id)).all() == []
        assert db_session.exec(
            select(WorkExperience).where(WorkExperience.application_id == app_id)
        ).all() == []
        assert db_session.exec(
            select(Education).where(Education.application_id == app_id)
        ).all() == []

    def test_delete_vacancy_not_found_returns_404(self, client):
        response = client.post("/dashboard/vacancies/999999/delete")
        assert response.status_code == 404


class TestScheduleCandidate:
    def test_schedule_candidate_hr_online_happy_path(self, client, db_session, seed_application, mock_external_services):
        payload = {
            "stage": "hr_online",
            "meeting_time": "2026-10-01T10:00:00Z",
        }
        response = client.post(f"/dashboard/candidates/{seed_application.id}/schedule", json=payload)

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "success"
        assert body["zoom_url"] == "https://zoom.example.com/j/123456"

        db_session.refresh(seed_application)
        assert seed_application.pipeline_stage == PipelineStage.HR_ONLINE

        meetings = db_session.exec(select(Meeting).where(Meeting.candidate_id == seed_application.id)).all()
        assert len(meetings) == 1
        assert meetings[0].meeting_link == "https://zoom.example.com/j/123456"

        mock_external_services.dash_zoom.assert_awaited_once()
        mock_external_services.dash_notify_status.assert_awaited_once()
        mock_external_services.dash_notify_meeting.assert_awaited_once()

    def test_schedule_candidate_hr_offline_happy_path(self, client, db_session, seed_application, mock_external_services):
        payload = {
            "stage": "hr_offline",
            "meeting_time": "2026-10-02T12:00:00Z",
            "branch_name": "Chilonzor filiali",
        }
        response = client.post(f"/dashboard/candidates/{seed_application.id}/schedule", json=payload)
        assert response.status_code == 200

        db_session.refresh(seed_application)
        assert seed_application.pipeline_stage == PipelineStage.HR_OFFLINE
        mock_external_services.dash_zoom.assert_not_awaited()

    def test_schedule_candidate_zoom_failure_returns_500(self, client, seed_application, mock_external_services):
        mock_external_services.dash_zoom.side_effect = RuntimeError("Zoom API down")
        payload = {"stage": "hr_online", "meeting_time": "2026-10-01T10:00:00Z"}
        response = client.post(f"/dashboard/candidates/{seed_application.id}/schedule", json=payload)
        assert response.status_code == 500

    def test_schedule_candidate_invalid_stage_returns_400(self, client, seed_application):
        payload = {"stage": "not_a_real_stage", "meeting_time": "2026-10-01T10:00:00Z"}
        response = client.post(f"/dashboard/candidates/{seed_application.id}/schedule", json=payload)
        assert response.status_code == 400

    def test_schedule_candidate_not_found_returns_404(self, client):
        payload = {"stage": "hr_online", "meeting_time": "2026-10-01T10:00:00Z"}
        response = client.post("/dashboard/candidates/999999/schedule", json=payload)
        assert response.status_code == 404


class TestSendJobOffer:
    def test_send_job_offer_happy_path(self, client, db_session, seed_application, mock_external_services):
        form_data = {
            "starting_salary": "6,000,000 so'm",
            "work_days": "Dushanba - Juma",
            "work_hours": "09:00 - 18:00",
            "start_datetime": "2026-11-01T09:00:00Z",
            "location": "Chilonzor filiali",
        }
        response = client.post(f"/dashboard/candidates/{seed_application.id}/offer", data=form_data)

        assert response.status_code in (200, 303)
        if "location" in response.headers:
            assert response.headers["location"] == f"/dashboard/candidates/{seed_application.id}?offer_sent=1"

        offers = db_session.exec(select(JobOffer).where(JobOffer.candidate_id == seed_application.id)).all()
        assert len(offers) == 1
        assert offers[0].starting_salary == "6,000,000 so'm"

        db_session.refresh(seed_application)
        assert seed_application.pipeline_stage == PipelineStage.OFFERED

        mock_external_services.dash_notify_offer.assert_awaited_once()
        mock_external_services.dash_notify_pm.assert_awaited_once()

    def test_send_job_offer_invalid_datetime_returns_400(self, client, seed_application):
        form_data = {
            "starting_salary": "6,000,000 so'm",
            "work_days": "Dushanba - Juma",
            "work_hours": "09:00 - 18:00",
            "start_datetime": "not-a-real-date",
            "location": "Chilonzor filiali",
        }
        response = client.post(f"/dashboard/candidates/{seed_application.id}/offer", data=form_data)
        assert response.status_code == 400

    def test_send_job_offer_not_found_returns_404(self, client):
        form_data = {
            "starting_salary": "x", "work_days": "x", "work_hours": "x",
            "start_datetime": "2026-11-01T09:00:00Z", "location": "x",
        }
        response = client.post("/dashboard/candidates/999999/offer", data=form_data)
        assert response.status_code == 404


class TestRejectCandidate:
    def test_reject_candidate_happy_path(self, client, db_session, seed_application, mock_external_services):
        response = client.post(f"/dashboard/candidates/{seed_application.id}/reject")
        assert response.status_code == 200
        assert response.json()["status"] == "success"

        db_session.refresh(seed_application)
        assert seed_application.status == ApplicationStatus.REJECTED
        assert seed_application.pipeline_stage == PipelineStage.RAD_ETILDI
        mock_external_services.dash_notify_status.assert_awaited_once()

    def test_reject_candidate_not_found_returns_404(self, client):
        response = client.post("/dashboard/candidates/999999/reject")
        assert response.status_code == 404


class TestSyncSheets:
    def test_sync_sheets_happy_path(self, client, seed_application, mock_external_services):
        response = client.post("/dashboard/sync-sheets")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "success"
        assert body["synced_rows"] == 3
        mock_external_services.dash_sync_sheets.assert_awaited_once()

    def test_sync_sheets_failure_returns_500(self, client, mock_external_services):
        # No natural 400/404/422 branch exists for this endpoint -- the
        # only failure modes it defines are 500s, so that's what we pin.
        mock_external_services.dash_sync_sheets.side_effect = Exception("Sheets API quota exceeded")
        response = client.post("/dashboard/sync-sheets")
        assert response.status_code == 500
        assert "Sinxronizatsiyada xatolik" in response.json()["detail"]

    def test_sync_sheets_missing_credentials_returns_500(self, client, mock_external_services):
        mock_external_services.dash_sync_sheets.side_effect = FileNotFoundError()
        response = client.post("/dashboard/sync-sheets")
        assert response.status_code == 500
        assert "credentials" in response.json()["detail"]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))