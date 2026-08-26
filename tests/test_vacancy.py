import unittest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, Session, create_engine, select
from sqlmodel.pool import StaticPool

from db.database import get_session
from db.models import (
    Branch,
    Vacancy,
    LLMUsageLog,
    UserRole,
    ApplicationStatus,
    InterviewStage,
    LLMActionType,
)
from main import app
from services.llm_evaluator import generate_vacancy_questions, VacancyQuestionsSchema


class TestVacancyCreation(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        SQLModel.metadata.create_all(self.engine)
        self.session = Session(self.engine)

        def get_session_override():
            return self.session

        app.dependency_overrides[get_session] = get_session_override
        self.client = TestClient(app)

    def tearDown(self):
        self.session.close()
        app.dependency_overrides.clear()

    def test_enums_and_models(self):
        self.assertEqual(UserRole.CANDIDATE, "CANDIDATE")
        self.assertEqual(UserRole.HR, "HR")
        self.assertEqual(UserRole.DIRECTOR, "DIRECTOR")
        self.assertEqual(UserRole.EMPLOYEE, "EMPLOYEE")

        self.assertEqual(ApplicationStatus.PENDING, "PENDING")
        self.assertEqual(ApplicationStatus.ACCEPTED, "ACCEPTED")
        self.assertEqual(ApplicationStatus.REJECTED, "REJECTED")
        self.assertEqual(ApplicationStatus.TALENT_POOL, "TALENT_POOL")
        self.assertEqual(ApplicationStatus.HIRED, "HIRED")

        self.assertEqual(InterviewStage.HR_VERIFICATION, "HR_VERIFICATION")
        self.assertEqual(InterviewStage.BRANCH_INTERVIEW, "BRANCH_INTERVIEW")
        self.assertEqual(InterviewStage.DIRECTOR_INTERVIEW, "DIRECTOR_INTERVIEW")

        self.assertEqual(LLMActionType.VACANCY_GEN, "VACANCY_GEN")
        self.assertEqual(LLMActionType.CV_EVALUATION, "CV_EVALUATION")

        branch = Branch(name="Toshkent Markaz", address="Amir Temur ko'chasi 1", manager_telegram_chat_id=123456789)
        self.session.add(branch)
        self.session.commit()
        self.session.refresh(branch)
        self.assertIsNotNone(branch.id)

        log = LLMUsageLog(
            action_type=LLMActionType.VACANCY_GEN,
            tokens_input=1000,
            tokens_output=500,
            cost_usd=0.00045,
        )
        self.session.add(log)
        self.session.commit()
        self.session.refresh(log)
        self.assertIsNotNone(log.id)
        self.assertEqual(log.tokens_input, 1000)

        vacancy = Vacancy(
            title="Python Developer",
            department="IT",
            description="FastAPI va PostgreSQL bilishi shart",
            branch_id=branch.id,
            generated_hard_skill_q1="Q1",
            generated_hard_skill_q2="Q2",
            generated_soft_skill_q1="SQ1",
            generated_soft_skill_q2="SQ2",
        )
        self.session.add(vacancy)
        self.session.commit()
        self.session.refresh(vacancy)
        self.assertIsNotNone(vacancy.id)
        self.assertTrue(vacancy.is_active)

    def test_llm_evaluator_cost_and_parsing(self):
        mock_parsed_data = VacancyQuestionsSchema(
            hard_skill_q1="FastAPI da dependency injection qanday ishlaydi?",
            hard_skill_q2="SQLAlchemy va SQLModel o'rtasidagi farq nima?",
            soft_skill_q1="Jamoada nizoli vaziyat bo'lganda nima qilasiz?",
            soft_skill_q2="Kutilmagan muammoga duch kelganda vaqtni qanday rejalashtirasiz?",
        )

        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.parsed = mock_parsed_data
        mock_response.choices = [mock_choice]
        mock_response.usage.prompt_tokens = 200
        mock_response.usage.completion_tokens = 100

        with patch("services.llm_evaluator.client.beta.chat.completions.parse", new_callable=AsyncMock) as mock_parse:
            mock_parse.return_value = mock_response

            res = asyncio.run(
                generate_vacancy_questions(
                    title="Senior Python Backend",
                    description="Microservices va FastAPI bilan ishlash",
                )
            )

            self.assertEqual(res["tokens_input"], 200)
            self.assertEqual(res["tokens_output"], 100)
            expected_cost = (200 * 0.15 / 1_000_000) + (100 * 0.60 / 1_000_000)
            self.assertAlmostEqual(res["cost_usd"], expected_cost, places=8)
            self.assertEqual(res["questions"]["hard_skill_q1"], "FastAPI da dependency injection qanday ishlaydi?")

    def test_create_vacancy_branch_not_found(self):
        response = self.client.post(
            "/hr/vacancies/create",
            json={
                "title": "Cashier",
                "department": "Sales",
                "description": "Mijozlarga xizmat ko'rsatish",
                "branch_id": 9999,
            },
        )
        self.assertEqual(response.status_code, 404)
        self.assertIn("Branch with id 9999 not found", response.json()["detail"])

    def test_create_vacancy_success(self):
        branch = Branch(name="Chilonzor filiali", address="Chilonzor 9-mavze", manager_telegram_chat_id=987654321)
        self.session.add(branch)
        self.session.commit()
        self.session.refresh(branch)

        mock_llm_result = {
            "questions": {
                "hard_skill_q1": "Kassada 1C dasturi bilan ishlaganmisiz?",
                "hard_skill_q2": "Kunlik hisobot qanday yopiladi?",
                "soft_skill_q1": "Asabiy mijoz bilan qanday gaplashasiz?",
                "soft_skill_q2": "Navbat ko'payganda stressni qanday boshqarasiz?",
            },
            "tokens_input": 150,
            "tokens_output": 80,
            "cost_usd": 0.0000705,
        }

        with patch("api.portal.generate_vacancy_questions", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = mock_llm_result

            response = self.client.post(
                "/hr/vacancies/create",
                json={
                    "title": "Kassir-operator",
                    "department": "Savdo",
                    "description": "Kassa amaliyotlari va mijozlar bilan ishlash",
                    "branch_id": branch.id,
                },
            )

            self.assertEqual(response.status_code, 201)
            data = response.json()
            self.assertEqual(data["vacancy"]["title"], "Kassir-operator")
            self.assertEqual(data["vacancy"]["branch_id"], branch.id)
            self.assertEqual(data["vacancy"]["generated_hard_skill_q1"], "Kassada 1C dasturi bilan ishlaganmisiz?")
            self.assertEqual(data["generated_questions"]["soft_skill_q1"], "Asabiy mijoz bilan qanday gaplashasiz?")
            self.assertEqual(data["llm_cost_usd"], 0.0000705)

            # Check in DB
            vacancies = self.session.exec(select(Vacancy)).all()
            self.assertEqual(len(vacancies), 1)
            self.assertEqual(vacancies[0].title, "Kassir-operator")
            self.assertAlmostEqual(vacancies[0].llm_cost_usd, 0.0000705, places=7)

            usage_logs = self.session.exec(select(LLMUsageLog)).all()
            self.assertEqual(len(usage_logs), 1)
            self.assertEqual(usage_logs[0].action_type, LLMActionType.VACANCY_GEN)
            self.assertEqual(usage_logs[0].tokens_input, 150)
            self.assertEqual(usage_logs[0].tokens_output, 80)


if __name__ == "__main__":
    unittest.main()
