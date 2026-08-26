import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from sqlmodel import SQLModel, create_engine, Session

from bot.config import settings
from bot.handlers.commands import (
    command_start_handler,
    command_me_handler,
    command_meetings_handler,
    command_support_handler,
    command_help_handler,
    router,
)
from db.models import ApplicationStatus, Branch, CandidateApplication, InterviewStage, User, UserRole, Vacancy


class TestBotHandlers(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        # Use an in-memory SQLite database for test isolation
        cls.test_engine = create_engine("sqlite:///:memory:")
        SQLModel.metadata.create_all(cls.test_engine)

    def setUp(self):
        # Recreate tables before each test
        SQLModel.metadata.drop_all(self.test_engine)
        SQLModel.metadata.create_all(self.test_engine)

    @patch("bot.handlers.commands.engine")
    async def test_command_start(self, mock_engine):
        message = AsyncMock()
        await command_start_handler(message)

        message.answer.assert_called_once()
        args, kwargs = message.answer.call_args
        self.assertIn("Mega Star HR botiga xush kelibsiz", args[0])
        self.assertIn("reply_markup", kwargs)
        markup = kwargs["reply_markup"]
        button = markup.inline_keyboard[0][0]
        self.assertEqual(button.text, "🚀 Portalni ochish")
        self.assertEqual(button.web_app.url, f"{settings.WEBAPP_URL.rstrip('/')}/apply")

    @patch("bot.handlers.commands.engine")
    async def test_command_me_not_found(self, mock_engine):
        mock_engine.connect = self.test_engine.connect
        # Mock Session to use test_engine
        with patch("bot.handlers.commands.Session", side_effect=lambda eng=None: Session(self.test_engine)):
            message = AsyncMock()
            message.from_user = MagicMock(id=12345678)
            await command_me_handler(message)

            message.answer.assert_called_once()
            args, _ = message.answer.call_args
            self.assertIn("Siz hali ariza topshirmagansiz", args[0])

    @patch("bot.handlers.commands.engine")
    async def test_command_me_found(self, mock_engine):
        with Session(self.test_engine) as session:
            user = User(telegram_id=999888, full_name="John Doe", phone_number="+998901234567")
            session.add(user)
            branch = Branch(name="Chilonzor", address="Chilonzor 1-mavze")
            session.add(branch)
            session.commit()
            session.refresh(user)
            session.refresh(branch)

            vacancy = Vacancy(
                title="Sotuvchi",
                department="Savdo",
                description="Kassir / Sotuvchi",
                branch_id=branch.id,
                generated_hard_skill_q1="Q1",
                generated_hard_skill_q2="Q2",
                generated_soft_skill_q1="Q3",
                generated_soft_skill_q2="Q4",
            )
            session.add(vacancy)
            session.commit()
            session.refresh(vacancy)

            app = CandidateApplication(
                user_id=user.id,
                vacancy_id=vacancy.id,
                branch_id=branch.id,
                status=ApplicationStatus.PENDING,
                stage=InterviewStage.HR_VERIFICATION,
            )
            session.add(app)
            session.commit()

        with patch("bot.handlers.commands.Session", side_effect=lambda eng=None: Session(self.test_engine)):
            message = AsyncMock()
            message.from_user = MagicMock(id=999888)
            await command_me_handler(message)

            message.answer.assert_called_once()
            args, kwargs = message.answer.call_args
            self.assertIn("Sizning profilingiz:", args[0])
            self.assertIn("Holat: PENDING", args[0])
            self.assertIn("Filial: Chilonzor", args[0])
            self.assertIn("Bosqich: HR_VERIFICATION", args[0])

    @patch("bot.handlers.commands.engine")
    async def test_command_meetings_no_application(self, mock_engine):
        with patch("bot.handlers.commands.Session", side_effect=lambda eng=None: Session(self.test_engine)):
            message = AsyncMock()
            message.from_user = MagicMock(id=11111)
            await command_meetings_handler(message)

            message.answer.assert_called_once_with("Kelgusi uchrashuvlar mavjud emas.")

    @patch("bot.handlers.commands.engine")
    async def test_command_meetings_with_active_stage(self, mock_engine):
        with Session(self.test_engine) as session:
            user = User(telegram_id=22222, full_name="Jane Doe", phone_number="+998909876543")
            session.add(user)
            branch = Branch(name="Yunusobod", address="Amir Temur ko'chasi 5")
            session.add(branch)
            session.commit()
            session.refresh(user)
            session.refresh(branch)

            vacancy = Vacancy(
                title="Boshqaruvchi",
                department="Boshqaruv",
                description="Filial direktori",
                branch_id=branch.id,
                generated_hard_skill_q1="Q1",
                generated_hard_skill_q2="Q2",
                generated_soft_skill_q1="Q3",
                generated_soft_skill_q2="Q4",
            )
            session.add(vacancy)
            session.commit()
            session.refresh(vacancy)

            app = CandidateApplication(
                user_id=user.id,
                vacancy_id=vacancy.id,
                branch_id=branch.id,
                status=ApplicationStatus.PENDING,
                stage=InterviewStage.BRANCH_INTERVIEW,
            )
            session.add(app)
            session.commit()

        with patch("bot.handlers.commands.Session", side_effect=lambda eng=None: Session(self.test_engine)):
            message = AsyncMock()
            message.from_user = MagicMock(id=22222)
            await command_meetings_handler(message)

            message.answer.assert_called_once()
            args, _ = message.answer.call_args
            self.assertIn("Kelgusi uchrashuv:", args[0])
            self.assertIn("2-bosqich: Filial suhbati", args[0])
            self.assertIn("Yunusobod filiali", args[0])

    async def test_command_support(self):
        message = AsyncMock()
        await command_support_handler(message)

        message.answer.assert_called_once()
        args, kwargs = message.answer.call_args
        self.assertIn("+998 78 777 77 00", args[0])
        self.assertIn("Farhod ko'chasi, 21B", args[0])

    async def test_command_help(self):
        message = AsyncMock()
        await command_help_handler(message)

        message.answer.assert_called_once()
        args, kwargs = message.answer.call_args
        self.assertIn("/start", args[0])
        self.assertIn("/me", args[0])
        self.assertIn("/meetings", args[0])
        self.assertIn("/support", args[0])
        self.assertIn("/help", args[0])


class TestBotRunner(unittest.IsolatedAsyncioTestCase):
    @patch("bot.main.dp.start_polling", new_callable=AsyncMock)
    async def test_start_bot(self, mock_start_polling):
        from bot.main import start_bot, bot, dp
        self.assertIsNotNone(bot)
        self.assertIsNotNone(dp)
        await start_bot()
        mock_start_polling.assert_called_once_with(bot)


if __name__ == "__main__":
    unittest.main()
