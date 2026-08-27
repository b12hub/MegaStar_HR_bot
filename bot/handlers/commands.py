from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo
from sqlmodel import Session, select

from bot.config import settings
from db.database import engine
from db.models import ApplicationStatus, Branch, CandidateApplication, InterviewStage, User

router = Router(name="commands")


@router.message(CommandStart())
async def command_start_handler(message: Message) -> None:
    """
    /start command handler:
    Sends welcome message and InlineKeyboardMarkup with WebApp button.
    """
    welcome_text = (
        "Mega Star HR tizimiga xush kelibsiz! 🌟\n\n"
        "Jamoamizga qo'shilish uchun ajoyib imkoniyat. "
        "Ochiq vakansiyalarga ariza topshirish uchun quyidagi tugmani bosing:"
    )

    # Point to central portal page
    webapp_url = f"{settings.WEBAPP_URL.rstrip('/')}/apply/portal"

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🚀 Vakansiyaga Topshirish",
                    web_app=WebAppInfo(url=webapp_url),
                )
            ]
        ]
    )
    await message.answer(welcome_text, reply_markup=keyboard)


@router.message(Command("me"))
async def command_me_handler(message: Message) -> None:
    """
    /me command handler:
    Queries PostgreSQL for current user's CandidateApplication by telegram_id.
    """
    telegram_id = message.from_user.id if message.from_user else None
    if not telegram_id:
        await message.answer(
            "Siz hali ariza topshirmagansiz. Ariza topshirish uchun /start tugmasini bosing."
        )
        return

    with Session(engine) as session:
        # Find user by telegram_id
        user = session.exec(
            select(User).where(User.telegram_id == telegram_id)
        ).first()

        if not user:
            await message.answer(
                "Siz hali ariza topshirmagansiz. Ariza topshirish uchun /start tugmasini bosing."
            )
            return

        # Query latest CandidateApplication for the user
        application = session.exec(
            select(CandidateApplication)
            .where(CandidateApplication.user_id == user.id)
            .order_by(CandidateApplication.created_at.desc())
        ).first()

        if not application:
            await message.answer(
                "Siz hali ariza topshirmagansiz. Ariza topshirish uchun /start tugmasini bosing."
            )
            return

        # Fetch branch name
        branch = session.get(Branch, application.branch_id)
        branch_name = branch.name if branch else "Noma'lum"

        # Format status and stage display
        status_val = (
            application.status.value
            if hasattr(application.status, "value")
            else str(application.status)
        )
        stage_val = (
            application.stage.value
            if hasattr(application.stage, "value")
            else str(application.stage)
        )

        profile_text = (
            "👤 **Sizning profilingiz:**\n"
            f"Holat: {status_val}\n"
            f"Filial: {branch_name}\n"
            f"Bosqich: {stage_val}"
        )
        await message.answer(profile_text, parse_mode="Markdown")


@router.message(Command("meetings"))
async def command_meetings_handler(message: Message) -> None:
    """
    /meetings command handler:
    Queries CandidateApplication for active interview slots.
    If approved for Stage 1/2/3, displays date, time, and address/Zoom link.
    Otherwise: "Kelgusi uchrashuvlar mavjud emas."
    """
    telegram_id = message.from_user.id if message.from_user else None
    if not telegram_id:
        await message.answer("Kelgusi uchrashuvlar mavjud emas.")
        return

    with Session(engine) as session:
        user = session.exec(
            select(User).where(User.telegram_id == telegram_id)
        ).first()

        if not user:
            await message.answer("Kelgusi uchrashuvlar mavjud emas.")
            return

        application = session.exec(
            select(CandidateApplication)
            .where(CandidateApplication.user_id == user.id)
            .order_by(CandidateApplication.created_at.desc())
        ).first()

        if not application or application.status == ApplicationStatus.REJECTED:
            await message.answer("Kelgusi uchrashuvlar mavjud emas.")
            return

        branch = session.get(Branch, application.branch_id)
        branch_name = branch.name if branch else "Bosh ofis"
        branch_address = (
            branch.address
            if branch and branch.address
            else "Toshkent sh., Farhod ko'chasi, 21B"
        )

        # Check interview stages
        # Stage 1: HR_VERIFICATION
        # Stage 2: BRANCH_INTERVIEW
        # Stage 3: DIRECTOR_INTERVIEW
        if application.stage in [
            InterviewStage.HR_VERIFICATION,
            InterviewStage.BRANCH_INTERVIEW,
            InterviewStage.DIRECTOR_INTERVIEW,
        ]:
            if application.stage == InterviewStage.HR_VERIFICATION:
                stage_name = "1-bosqich: HR suhbati"
                location_info = f"Online / Zoom havolasi: https://zoom.us/j/megastar-hr"
            elif application.stage == InterviewStage.BRANCH_INTERVIEW:
                stage_name = "2-bosqich: Filial suhbati"
                location_info = f"Manzil: {branch_name} filiali ({branch_address})"
            elif application.stage == InterviewStage.DIRECTOR_INTERVIEW:
                stage_name = "3-bosqich: Rahbariyat suhbati"
                location_info = f"Manzil: Bosh ofis ({branch_address})"
            else:
                stage_name = str(application.stage.value if hasattr(application.stage, "value") else application.stage)
                location_info = f"Manzil: {branch_address}"

            meeting_text = (
                f"📅 **Kelgusi uchrashuv:**\n"
                f"Bosqich: {stage_name}\n"
                f"Holat: Tasdiqlangan / Jarayonda\n"
                f"Joylashuv: {location_info}"
            )
            await message.answer(meeting_text, parse_mode="Markdown")
        else:
            await message.answer("Kelgusi uchrashuvlar mavjud emas.")


@router.message(Command("support"))
async def command_support_handler(message: Message) -> None:
    """
    /support command handler:
    Returns office support contact info.
    """
    support_text = (
        "☎️ **Aloqa markazi:** +998 78 777 77 00\n"
        "📍 **Bosh office:** Toshkent sh., Farhod ko'chasi, 21B"
    )
    await message.answer(support_text, parse_mode="Markdown")


@router.message(Command("help"))
async def command_help_handler(message: Message) -> None:
    """
    /help command handler:
    Returns list of available commands.
    """
    help_text = (
        "📋 **Mavjud buyruqlar:**\n"
        "/start - Botni ishga tushirish va portal havolasi\n"
        "/me - Shaxsiy profil va ariza holati\n"
        "/meetings - Rejalashtirilgan suhbatlar va uchrashuvlar\n"
        "/support - Qo'llab-quvvatlash va aloqa markazi\n"
        "/help - Mavjud buyruqlar ro'yxati"
    )
    await message.answer(help_text, parse_mode="Markdown")
