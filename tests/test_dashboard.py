import unittest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, Session, create_engine, select
from sqlmodel.pool import StaticPool

from db.database import get_session
from db.models import Branch, LLMActionType, LLMUsageLog, Vacancy
from main import app


class TestHRDashboard(unittest.TestCase):
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

    def test_hr_dashboard_empty(self):
        response = self.client.get("/dashboard/hr")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers["content-type"])
        
        content = response.text
        # Check Mega Star branding logo
        self.assertIn("Mega", content)
        self.assertIn("Star", content)
        self.assertIn("★", content)
        self.assertIn("HR Portal", content)
        self.assertIn("MegaStar★ HR Portal", content)

        # Check Uzbek Page Title & Subtitle
        self.assertIn("HR Boshqaruv Paneli", content)
        self.assertIn("Vakansiyalarni boshqarish va AI xarajatlarini real vaqt rejimida monitoring qilish.", content)
        
        # Check "+ Yangi Vakansiya Yaratish" button
        self.assertIn("Yangi Vakansiya Yaratish", content)
        self.assertIn("/dashboard/vacancies/new", content)

        # Check Tailwind CDN
        self.assertIn("https://cdn.tailwindcss.com", content)

        # Check Metric Cards in Uzbek
        self.assertIn("JAMI AI XARAJATI (USD)", content)
        self.assertIn("Generatsiyalar uchun sarflangan mablag'", content)
        self.assertIn("FAOL VAKANSIYALAR", content)
        self.assertIn("Nomzodlar uchun ochiq", content)
        self.assertIn("JAMI VAKANSIYALAR", content)
        self.assertIn("Barcha filiallar bo'yicha", content)
        self.assertIn("$ 0.0000000", content)

        # Check Table Headers in Uzbek
        self.assertIn("Vakansiyalar Ro'yxati", content)
        self.assertIn("Barcha ro'yxatdan o'tgan vakansiyalarning Excel-style jadvali", content)
        self.assertIn("ID", content)
        self.assertIn("VAKANSIYA NOMI", content)
        self.assertIn("BO'LIM", content)
        self.assertIn("FILIAL", content)
        self.assertIn("HOLATI", content)
        self.assertIn("AI XARAJATI", content)
        self.assertIn("YARATILGAN VAQTI", content)
        self.assertIn("AMALLAR", content)
        self.assertIn("Vakansiyalar topilmadi", content)

    def test_hr_dashboard_with_vacancies_and_precision(self):
        with Session(self.engine) as session:
            branch = Branch(name="Toshkent Markaz", address="Amir Temur 1")
            session.add(branch)
            session.commit()
            session.refresh(branch)

            v1 = Vacancy(
                title="Frontend Developer",
                department="IT Department",
                description="Vue / Tailwind experience",
                branch_id=branch.id,
                generated_hard_skill_q1="q1",
                generated_hard_skill_q2="q2",
                generated_soft_skill_q1="q3",
                generated_soft_skill_q2="q4",
                llm_cost_usd=0.000123,
                is_active=True,
            )
            v2 = Vacancy(
                title="HR Manager",
                department="Human Resources",
                description="Recruitment lead",
                branch_id=branch.id,
                generated_hard_skill_q1="q1",
                generated_hard_skill_q2="q2",
                generated_soft_skill_q1="q3",
                generated_soft_skill_q2="q4",
                llm_cost_usd=0.000075,
                is_active=False,
            )
            session.add_all([v1, v2])
            session.commit()
            session.refresh(v1)
            session.refresh(v2)

        response = self.client.get("/dashboard/hr")
        self.assertEqual(response.status_code, 200)
        content = response.text

        # Verify vacancies are listed
        self.assertIn("Frontend Developer", content)
        self.assertIn("HR Manager", content)
        self.assertIn("IT Department", content)
        self.assertIn("Human Resources", content)

        # Verify active/inactive pills
        self.assertIn("Faol", content)
        self.assertIn("Nofaol", content)

        # Verify 7 decimal places cost formatting
        self.assertIn("$ 0.0001230", content)
        self.assertIn("$ 0.0000750", content)
        self.assertIn("$ 0.0001980", content)  # total: 0.000123 + 0.000075

        # Verify clickable title link and actions button
        self.assertIn(f'/dashboard/vacancies/{v1.id}', content)
        self.assertIn(f'/dashboard/vacancies/{v2.id}', content)
        self.assertIn("👁️ Ko'rish", content)

    def test_vacancy_detail_page(self):
        with Session(self.engine) as session:
            branch = Branch(name="Yunusobod Filiali", address="Amir Temur 45")
            session.add(branch)
            session.commit()
            session.refresh(branch)

            v = Vacancy(
                title="Senior Python Backend",
                department="IT Engineering",
                description="FastAPI, PostgreSQL, Redis, Docker bo'yicha 3 yillik tajriba.",
                branch_id=branch.id,
                generated_hard_skill_q1="FastAPI da async dependency injection qanday ishlaydi?",
                generated_hard_skill_q2="PostgreSQL indekslash turlari va ularning farqi?",
                generated_soft_skill_q1="Jamoada nizoli vaziyat bo'lganda qanday yechasiz?",
                generated_soft_skill_q2="Deadline yaqinlashganda vazifalarni qanday ustuvorlashtirasiz?",
                llm_cost_usd=0.000142,
                is_active=True,
            )
            session.add(v)
            session.commit()
            session.refresh(v)
            v_id = v.id

        response = self.client.get(f"/dashboard/vacancies/{v_id}")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers["content-type"])
        content = response.text

        # Check Back Button
        self.assertIn("← Orqaga dashboardga", content)
        self.assertIn("/dashboard/hr", content)

        # Check Vacancy Information Card
        self.assertIn("Senior Python Backend", content)
        self.assertIn("IT Engineering", content)
        self.assertIn("Yunusobod Filiali", content)
        self.assertIn("$ 0.0001420", content)
        self.assertIn("Faol", content)

        # Check Description
        self.assertIn("FastAPI, PostgreSQL, Redis, Docker", content)

        # Check AI Generated Questions Section
        self.assertIn("AI Generatsiya Qilingan Savollar", content)
        self.assertIn("Intervyu jarayonida nomzodga beriladigan maxsus avtomatik savollar", content)
        self.assertNotIn("Rakhimov", content)
        self.assertIn("Hard-Skill Savollari", content)
        self.assertIn("Soft-Skill Savollari", content)
        self.assertIn("FastAPI da async dependency injection qanday ishlaydi?", content)
        self.assertIn("PostgreSQL indekslash turlari va ularning farqi?", content)
        self.assertIn("Jamoada nizoli vaziyat", content)
        self.assertIn("Deadline yaqinlashganda vazifalarni qanday ustuvorlashtirasiz?", content)

    def test_vacancy_detail_not_found(self):
        response = self.client.get("/dashboard/vacancies/99999")
        self.assertEqual(response.status_code, 404)

    def test_vacancy_create_page(self):
        with Session(self.engine) as session:
            b1 = Branch(name="Toshkent Markaz", address="Amir Temur 10")
            b2 = Branch(name="Samarqand Filiali", address="Registon 5")
            session.add_all([b1, b2])
            session.commit()

        response = self.client.get("/dashboard/vacancies/new")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers["content-type"])
        content = response.text

        # Check Header and Subtitle
        self.assertIn("Yangi Vakansiya Biriktirish", content)
        self.assertIn("Vakansiya tafsilotlarini kiriting. AI tizimi avtomatik ravishda intervyu savollarini shakllantiradi.", content)

        # Check Form Fields
        self.assertIn('name="title"', content)
        self.assertIn('name="department"', content)
        self.assertIn('name="branch_id"', content)
        self.assertIn('name="description"', content)

        # Check Branches rendered in select
        self.assertIn("Toshkent Markaz", content)
        self.assertIn("Samarqand Filiali", content)

        # Check Navigation and Loading State
        self.assertIn("← Bekor qilish", content)
        self.assertIn("/dashboard/hr", content)
        self.assertIn("AI Savollar generatsiya qilinmoqda...", content)

    def test_create_vacancy_form_submit_branch_not_found(self):
        response = self.client.post(
            "/dashboard/vacancies/new",
            data={
                "title": "Menejer",
                "department": "Savdo",
                "description": "Savdo bo'limi menejeri",
                "branch_id": 99999,
            },
        )
        self.assertEqual(response.status_code, 404)
        self.assertIn("Branch with id 99999 not found", response.json()["detail"])

    def test_create_vacancy_form_submit_success(self):
        with Session(self.engine) as session:
            branch = Branch(name="Chilonzor Filiali", address="Chilonzor 7")
            session.add(branch)
            session.commit()
            session.refresh(branch)
            branch_id = branch.id

        mock_llm_result = {
            "questions": {
                "hard_skill_q1": "Savdo rejasini qanday tuzasiz?",
                "hard_skill_q2": "1C Savdo dasturida ishlash tajribangiz bormi?",
                "soft_skill_q1": "Mijoz e'tiroz bildirganda qanday yo'l tutasiz?",
                "soft_skill_q2": "Stress holatida ishlash qobiliyatingizni qanday baholaysiz?",
            },
            "tokens_input": 120,
            "tokens_output": 70,
            "cost_usd": 0.0000600,
        }

        with patch("api.dashboard.generate_vacancy_questions", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = mock_llm_result

            response = self.client.post(
                "/dashboard/vacancies/new",
                data={
                    "title": "Sotuvchi-Konsultant",
                    "department": "Savdo",
                    "description": "Mijozlarga xizmat ko'rsatish va tovarlarni tavsiya qilish",
                    "branch_id": branch_id,
                },
                follow_redirects=False,
            )

            self.assertEqual(response.status_code, 303)
            self.assertEqual(response.headers["location"], "/dashboard/hr")

            # Check DB Vacancy
            with Session(self.engine) as session:
                vacancies = session.exec(select(Vacancy)).all()
                self.assertEqual(len(vacancies), 1)
                v = vacancies[0]
                self.assertEqual(v.title, "Sotuvchi-Konsultant")
                self.assertEqual(v.department, "Savdo")
                self.assertEqual(v.branch_id, branch_id)
                self.assertEqual(v.generated_hard_skill_q1, "Savdo rejasini qanday tuzasiz?")
                self.assertEqual(v.generated_hard_skill_q2, "1C Savdo dasturida ishlash tajribangiz bormi?")
                self.assertEqual(v.generated_soft_skill_q1, "Mijoz e'tiroz bildirganda qanday yo'l tutasiz?")
                self.assertEqual(v.generated_soft_skill_q2, "Stress holatida ishlash qobiliyatingizni qanday baholaysiz?")
                self.assertAlmostEqual(v.llm_cost_usd, 0.0000600, places=7)

                # Check DB LLMUsageLog
                logs = session.exec(select(LLMUsageLog)).all()
                self.assertEqual(len(logs), 1)
                self.assertEqual(logs[0].action_type, LLMActionType.VACANCY_GEN)
                self.assertEqual(logs[0].tokens_input, 120)
                self.assertEqual(logs[0].tokens_output, 70)
                self.assertAlmostEqual(logs[0].cost_usd, 0.0000600, places=7)

    def test_dashboard_amallar_actions_rendering(self):
        with Session(self.engine) as session:
            v_active = Vacancy(
                title="Sotuvchi Faol",
                department="Savdo",
                description="Tavsif 1",
                branch_id=1,
                generated_hard_skill_q1="Q1",
                generated_hard_skill_q2="Q2",
                generated_soft_skill_q1="SQ1",
                generated_soft_skill_q2="SQ2",
                is_active=True,
                llm_cost_usd=0.0001,
            )
            v_inactive = Vacancy(
                title="Kassir Nofaol",
                department="Moliya",
                description="Tavsif 2",
                branch_id=1,
                generated_hard_skill_q1="Q1",
                generated_hard_skill_q2="Q2",
                generated_soft_skill_q1="SQ1",
                generated_soft_skill_q2="SQ2",
                is_active=False,
                llm_cost_usd=0.0002,
            )
            session.add_all([v_active, v_inactive])
            session.commit()
            session.refresh(v_active)
            session.refresh(v_inactive)

        response = self.client.get("/dashboard/hr")
        self.assertEqual(response.status_code, 200)
        content = response.text

        # Check Action buttons for active vacancy
        self.assertIn(f"/dashboard/vacancies/{v_active.id}", content)
        self.assertIn(f"/dashboard/vacancies/{v_active.id}/toggle", content)
        self.assertIn(f"/dashboard/vacancies/{v_active.id}/edit", content)
        self.assertIn(f"/dashboard/vacancies/{v_active.id}/delete", content)
        self.assertIn("⏸️ Nofaol qilish", content)

        # Check Action buttons for inactive vacancy
        self.assertIn(f"/dashboard/vacancies/{v_inactive.id}", content)
        self.assertIn(f"/dashboard/vacancies/{v_inactive.id}/toggle", content)
        self.assertIn(f"/dashboard/vacancies/{v_inactive.id}/edit", content)
        self.assertIn(f"/dashboard/vacancies/{v_inactive.id}/delete", content)
        self.assertIn("▶️ Faollashtirish", content)

    def test_toggle_vacancy_status(self):
        with Session(self.engine) as session:
            v = Vacancy(
                title="Kuryer",
                department="Logistika",
                description="Tavsif",
                branch_id=1,
                generated_hard_skill_q1="Q1",
                generated_hard_skill_q2="Q2",
                generated_soft_skill_q1="SQ1",
                generated_soft_skill_q2="SQ2",
                is_active=True,
            )
            session.add(v)
            session.commit()
            session.refresh(v)
            vacancy_id = v.id

        # Toggle from True to False
        response = self.client.post(
            f"/dashboard/vacancies/{vacancy_id}/toggle",
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/dashboard/hr")

        with Session(self.engine) as session:
            updated_v = session.get(Vacancy, vacancy_id)
            self.assertFalse(updated_v.is_active)

        # Toggle from False to True
        response = self.client.post(
            f"/dashboard/vacancies/{vacancy_id}/toggle",
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/dashboard/hr")

        with Session(self.engine) as session:
            updated_v = session.get(Vacancy, vacancy_id)
            self.assertTrue(updated_v.is_active)

    def test_toggle_vacancy_status_not_found(self):
        response = self.client.post("/dashboard/vacancies/99999/toggle")
        self.assertEqual(response.status_code, 404)

    def test_edit_vacancy_page(self):
        with Session(self.engine) as session:
            b1 = Branch(name="Filial A", address="Manzil A")
            b2 = Branch(name="Filial B", address="Manzil B")
            session.add_all([b1, b2])
            session.commit()
            session.refresh(b1)

            v = Vacancy(
                title="Bosh Mutaxassis",
                department="IT",
                description="Python va FastAPI tajribasi",
                branch_id=b1.id,
                generated_hard_skill_q1="Q1",
                generated_hard_skill_q2="Q2",
                generated_soft_skill_q1="SQ1",
                generated_soft_skill_q2="SQ2",
                is_active=True,
            )
            session.add(v)
            session.commit()
            session.refresh(v)
            vacancy_id = v.id

        response = self.client.get(f"/dashboard/vacancies/{vacancy_id}/edit")
        self.assertEqual(response.status_code, 200)
        content = response.text

        # Check page titles and pre-filled form fields
        self.assertIn("Vakansiyani Tahrirlash", content)
        self.assertIn('value="Bosh Mutaxassis"', content)
        self.assertIn('value="IT"', content)
        self.assertIn("Python va FastAPI tajribasi", content)
        self.assertIn("Filial A", content)
        self.assertIn("Filial B", content)
        self.assertIn('name="regenerate_ai"', content)
        self.assertIn('name="is_active"', content)

    def test_edit_vacancy_page_not_found(self):
        response = self.client.get("/dashboard/vacancies/99999/edit")
        self.assertEqual(response.status_code, 404)

    def test_update_vacancy_without_regenerate_ai(self):
        with Session(self.engine) as session:
            b1 = Branch(name="Filial 1", address="Manzil 1")
            b2 = Branch(name="Filial 2", address="Manzil 2")
            session.add_all([b1, b2])
            session.commit()
            session.refresh(b1)
            session.refresh(b2)
            b2_id = b2.id

            v = Vacancy(
                title="Dastlabki Nomi",
                department="Savdo",
                description="Dastlabki Tavsif",
                branch_id=b1.id,
                generated_hard_skill_q1="Old HQ1",
                generated_hard_skill_q2="Old HQ2",
                generated_soft_skill_q1="Old SQ1",
                generated_soft_skill_q2="Old SQ2",
                llm_cost_usd=0.00005,
                is_active=True,
            )
            session.add(v)
            session.commit()
            session.refresh(v)
            vacancy_id = v.id

        response = self.client.post(
            f"/dashboard/vacancies/{vacancy_id}/edit",
            data={
                "title": "Yangilangan Nomi",
                "department": "Yangi Bo'lim",
                "description": "Yangilangan Tavsif",
                "branch_id": b2_id,
                # is_active not provided -> False
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/dashboard/hr")

        with Session(self.engine) as session:
            updated_v = session.get(Vacancy, vacancy_id)
            self.assertEqual(updated_v.title, "Yangilangan Nomi")
            self.assertEqual(updated_v.department, "Yangi Bo'lim")
            self.assertEqual(updated_v.description, "Yangilangan Tavsif")
            self.assertEqual(updated_v.branch_id, b2_id)
            self.assertFalse(updated_v.is_active)
            # AI questions and cost should remain untouched
            self.assertEqual(updated_v.generated_hard_skill_q1, "Old HQ1")
            self.assertEqual(updated_v.generated_hard_skill_q2, "Old HQ2")
            self.assertEqual(updated_v.generated_soft_skill_q1, "Old SQ1")
            self.assertEqual(updated_v.generated_soft_skill_q2, "Old SQ2")
            self.assertAlmostEqual(updated_v.llm_cost_usd, 0.00005, places=7)

    def test_update_vacancy_with_regenerate_ai(self):
        with Session(self.engine) as session:
            branch = Branch(name="Filial Markaz", address="Markaziy Ko'cha")
            session.add(branch)
            session.commit()
            session.refresh(branch)
            branch_id = branch.id

            v = Vacancy(
                title="Eski Lavozim",
                department="Marketing",
                description="Eski Tavsif",
                branch_id=branch_id,
                generated_hard_skill_q1="Old HQ1",
                generated_hard_skill_q2="Old HQ2",
                generated_soft_skill_q1="Old SQ1",
                generated_soft_skill_q2="Old SQ2",
                llm_cost_usd=0.0000500,
                is_active=False,
            )
            session.add(v)
            session.commit()
            session.refresh(v)
            vacancy_id = v.id

        mock_llm_result = {
            "questions": {
                "hard_skill_q1": "New HQ1",
                "hard_skill_q2": "New HQ2",
                "soft_skill_q1": "New SQ1",
                "soft_skill_q2": "New SQ2",
            },
            "tokens_input": 150,
            "tokens_output": 80,
            "cost_usd": 0.0000750,
        }

        with patch("api.dashboard.generate_vacancy_questions", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = mock_llm_result

            response = self.client.post(
                f"/dashboard/vacancies/{vacancy_id}/edit",
                data={
                    "title": "Katta Marketing Menejeri",
                    "department": "Marketing",
                    "description": "Raqamli marketing va SMM strategiyasini boshqarish",
                    "branch_id": branch_id,
                    "is_active": "on",
                    "regenerate_ai": "on",
                },
                follow_redirects=False,
            )

            self.assertEqual(response.status_code, 303)
            self.assertEqual(response.headers["location"], "/dashboard/hr")

            with Session(self.engine) as session:
                updated_v = session.get(Vacancy, vacancy_id)
                self.assertEqual(updated_v.title, "Katta Marketing Menejeri")
                self.assertTrue(updated_v.is_active)
                self.assertEqual(updated_v.generated_hard_skill_q1, "New HQ1")
                self.assertEqual(updated_v.generated_hard_skill_q2, "New HQ2")
                self.assertEqual(updated_v.generated_soft_skill_q1, "New SQ1")
                self.assertEqual(updated_v.generated_soft_skill_q2, "New SQ2")
                # Cost should be accumulated: 0.0000500 + 0.0000750 = 0.0001250
                self.assertAlmostEqual(updated_v.llm_cost_usd, 0.0001250, places=7)

                # Check usage log
                logs = session.exec(select(LLMUsageLog)).all()
                self.assertEqual(len(logs), 1)
                self.assertEqual(logs[0].tokens_input, 150)
                self.assertEqual(logs[0].tokens_output, 80)
                self.assertAlmostEqual(logs[0].cost_usd, 0.0000750, places=7)

    def test_update_vacancy_not_found(self):
        response = self.client.post(
            "/dashboard/vacancies/99999/edit",
            data={
                "title": "Nomi",
                "department": "Bo'lim",
                "description": "Tavsif",
                "branch_id": 1,
            },
        )
        self.assertEqual(response.status_code, 404)

    def test_update_vacancy_branch_not_found(self):
        with Session(self.engine) as session:
            v = Vacancy(
                title="Nomi",
                department="Bo'lim",
                description="Tavsif",
                branch_id=1,
                generated_hard_skill_q1="Q1",
                generated_hard_skill_q2="Q2",
                generated_soft_skill_q1="SQ1",
                generated_soft_skill_q2="SQ2",
            )
            session.add(v)
            session.commit()
            session.refresh(v)
            vacancy_id = v.id

        response = self.client.post(
            f"/dashboard/vacancies/{vacancy_id}/edit",
            data={
                "title": "Yangi Nomi",
                "department": "Bo'lim",
                "description": "Tavsif",
                "branch_id": 99999,
            },
        )
        self.assertEqual(response.status_code, 404)
        self.assertIn("Branch with id 99999 not found", response.json()["detail"])

    def test_delete_vacancy_success(self):
        with Session(self.engine) as session:
            v = Vacancy(
                title="O'chiriladigan Vakansiya",
                department="Bo'lim",
                description="Tavsif",
                branch_id=1,
                generated_hard_skill_q1="Q1",
                generated_hard_skill_q2="Q2",
                generated_soft_skill_q1="SQ1",
                generated_soft_skill_q2="SQ2",
            )
            session.add(v)
            session.commit()
            session.refresh(v)
            vacancy_id = v.id

        response = self.client.post(
            f"/dashboard/vacancies/{vacancy_id}/delete",
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/dashboard/hr")

        with Session(self.engine) as session:
            deleted_v = session.get(Vacancy, vacancy_id)
            self.assertIsNone(deleted_v)

    def test_delete_vacancy_not_found(self):
        response = self.client.post("/dashboard/vacancies/99999/delete")
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
