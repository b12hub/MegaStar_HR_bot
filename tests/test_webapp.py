import unittest
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, Session, create_engine, select
from sqlmodel.pool import StaticPool

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
from main import app


class TestCandidateWebAppRoutes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        SQLModel.metadata.create_all(cls.engine)

        def override_get_session():
            with Session(cls.engine) as session:
                yield session

        app.dependency_overrides[get_session] = override_get_session
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        app.dependency_overrides.clear()

    def setUp(self):
        SQLModel.metadata.drop_all(self.engine)
        SQLModel.metadata.create_all(self.engine)

    def test_get_cascade_data(self):
        # Setup test data: 2 branches and 2 vacancies
        with Session(self.engine) as session:
            b1 = Branch(name="Chilonzor", address="Chilonzor 1-mavze")
            b2 = Branch(name="Yunusobod", address="Yunusobod 4-mavze")
            session.add(b1)
            session.add(b2)
            session.commit()
            session.refresh(b1)
            session.refresh(b2)

            v1 = Vacancy(
                title="Kassir",
                department="Savdo",
                description="Kassir lavozimi",
                branch_id=b1.id,
                generated_hard_skill_q1="q1",
                generated_hard_skill_q2="q2",
                generated_soft_skill_q1="q3",
                generated_soft_skill_q2="q4",
                is_active=True,
            )
            v2 = Vacancy(
                title="Kassir",
                department="Savdo",
                description="Kassir lavozimi",
                branch_id=b2.id,
                generated_hard_skill_q1="q1",
                generated_hard_skill_q2="q2",
                generated_soft_skill_q1="q3",
                generated_soft_skill_q2="q4",
                is_active=True,
            )
            v3_inactive = Vacancy(
                title="Menejer",
                department="Boshqaruv",
                description="Menejer lavozimi",
                branch_id=b1.id,
                generated_hard_skill_q1="q1",
                generated_hard_skill_q2="q2",
                generated_soft_skill_q1="q3",
                generated_soft_skill_q2="q4",
                is_active=False,
            )
            session.add_all([v1, v2, v3_inactive])
            session.commit()

        response = self.client.get("/apply/data")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertIn("vacancies", data)
        self.assertIn("branches", data)

        # Check branches
        self.assertEqual(len(data["branches"]), 2)
        branch_names = [b["name"] for b in data["branches"]]
        self.assertIn("Chilonzor", branch_names)
        self.assertIn("Yunusobod", branch_names)

        # Check vacancies (inactive vacancy should not be present, Kassir should have both branches)
        self.assertEqual(len(data["vacancies"]), 1)
        self.assertEqual(data["vacancies"][0]["title"], "Kassir")
        self.assertEqual(set(data["vacancies"][0]["branch_ids"]), {1, 2})

    def test_submit_candidate_application_success(self):
        # Create branch and vacancy
        with Session(self.engine) as session:
            b = Branch(name="Mirzo Ulugbek", address="Mustaqillik shoh ko'chasi")
            session.add(b)
            session.commit()
            session.refresh(b)

            v = Vacancy(
                title="Sotuvchi-maslahatchi",
                department="Savdo",
                description="Mijozlar bilan ishlash",
                branch_id=b.id,
                generated_hard_skill_q1="hs1",
                generated_hard_skill_q2="hs2",
                generated_soft_skill_q1="ss1",
                generated_soft_skill_q2="ss2",
            )
            session.add(v)
            session.commit()
            session.refresh(v)
            branch_id = b.id
            vacancy_id = v.id

        payload = {
            "full_name": "Ali Valiyev",
            "phone_number": "+998901234567",
            "telegram_id": 123456789,
            "birth_date": "1998-05-15",
            "gender": "Erkak",
            "languages": ["O'zbek", "Rus"],
            "pc_skills": ["Excel", "1C", "Word"],
            "vacancy_id": vacancy_id,
            "branch_id": branch_id,
            "experience": [
                {
                    "company_name": "Korzinka",
                    "position": "Kassir",
                    "start_date": "2021-01",
                    "end_date": "2023-05",
                    "description": "Kassa operatsiyalari va mijozlarga xizmat",
                }
            ],
            "education": [
                {
                    "institution": "Toshkent Davlat Iqtisodiyot Universiteti",
                    "degree": "Bakalavr",
                    "field_of_study": "Moliya",
                    "graduation_year": 2020,
                }
            ],
            "hard_skill_a1": "Kassadagi barcha amallarni bilaman",
            "hard_skill_a2": "Kamchilik bo'lsa darhol hisobot beraman",
            "soft_skill_a1": "Mijoz bilan muloyim muomala qilaman",
            "soft_skill_a2": "Jamoa bilan birga ishlayman",
        }

        response = self.client.post("/apply/submit", json=payload)
        self.assertEqual(response.status_code, 201)
        resp_data = response.json()
        self.assertTrue(resp_data["success"])
        self.assertIn("application_id", resp_data)
        app_id = resp_data["application_id"]

        # Verify in DB
        with Session(self.engine) as session:
            user = session.exec(select(User).where(User.telegram_id == 123456789)).first()
            self.assertIsNotNone(user)
            self.assertEqual(user.full_name, "Ali Valiyev")
            self.assertEqual(user.role, UserRole.CANDIDATE)

            app_rec = session.get(CandidateApplication, app_id)
            self.assertIsNotNone(app_rec)
            self.assertEqual(app_rec.user_id, user.id)
            self.assertEqual(app_rec.vacancy_id, vacancy_id)
            self.assertEqual(app_rec.branch_id, branch_id)
            self.assertEqual(app_rec.status, ApplicationStatus.PENDING)
            self.assertEqual(app_rec.stage, InterviewStage.HR_VERIFICATION)
            self.assertEqual(app_rec.hard_skill_a1, "Kassadagi barcha amallarni bilaman")

            # Check WorkExperience
            work_exps = session.exec(select(WorkExperience).where(WorkExperience.application_id == app_id)).all()
            self.assertEqual(len(work_exps), 1)
            self.assertEqual(work_exps[0].company_name, "Korzinka")

            # Check Education
            educations = session.exec(select(Education).where(Education.application_id == app_id)).all()
            self.assertEqual(len(educations), 1)
            self.assertEqual(educations[0].institution, "Toshkent Davlat Iqtisodiyot Universiteti")

    def test_submit_candidate_application_invalid_vacancy(self):
        with Session(self.engine) as session:
            b = Branch(name="Test Branch", address="Test Address")
            session.add(b)
            session.commit()
            session.refresh(b)
            branch_id = b.id

        payload = {
            "full_name": "Ali Valiyev",
            "phone_number": "+998901234567",
            "vacancy_id": 9999,
            "branch_id": branch_id,
            "experience": [],
            "education": [],
        }

        response = self.client.post("/apply/submit", json=payload)
        self.assertEqual(response.status_code, 404)
        self.assertIn("Vacancy with id 9999 not found", response.json()["detail"])

    def test_submit_candidate_application_invalid_branch(self):
        with Session(self.engine) as session:
            b = Branch(name="Test Branch", address="Test Address")
            session.add(b)
            session.commit()
            session.refresh(b)

            v = Vacancy(
                title="Test Vacancy",
                department="Test Dept",
                description="Test Desc",
                branch_id=b.id,
                generated_hard_skill_q1="hs1",
                generated_hard_skill_q2="hs2",
                generated_soft_skill_q1="ss1",
                generated_soft_skill_q2="ss2",
            )
            session.add(v)
            session.commit()
            session.refresh(v)
            vacancy_id = v.id

        payload = {
            "full_name": "Ali Valiyev",
            "phone_number": "+998901234567",
            "vacancy_id": vacancy_id,
            "branch_id": 9999,
            "experience": [],
            "education": [],
        }

        response = self.client.post("/apply/submit", json=payload)
        self.assertEqual(response.status_code, 404)
        self.assertIn("Branch with id 9999 not found", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
