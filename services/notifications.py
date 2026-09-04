import logging
from typing import Optional
from datetime import datetime, timedelta, timezone
from sqlmodel import Session, select
from db.database import engine
from db.models import Meeting, CandidateApplication, User, Vacancy
from bot.main import bot
import os
from pathlib import Path
from aiogram import Bot
from aiogram.types import FSInputFile
import httpx
from fastapi import BackgroundTasks

from bot.config import settings

logger = logging.getLogger(__name__)

BRANCH_MAPS = {
    "Office Energy": "https://yandex.uz/maps/-/CTXjF4pS",
    "Izza - Showroom": "https://yandex.uz/maps/?ll=69.146093%2C41.271384&pt=69.146093%2C41.271384&z=17",
    "Malika bozori, A3-do'kon": "https://yandex.uz/maps/10335/tashkent/?ll=69.270693%2C41.339429&pt=69.270693%2C41.339429&z=17",
    "O'rikzor bozori, 5-blok C15-do'kon": "https://yandex.uz/maps/10335/tashkent/?ll=69.150056%2C41.285935&pt=69.150056%2C41.285935&z=17",
    "O'rikzor bozori, 5-blok 60-do'kon": "https://yandex.uz/maps/10335/tashkent/?ll=69.150225%2C41.285909&pt=69.150225%2C41.285909&z=17",
    "Abusaxiy bozori, E111-do'kon": "https://yandex.uz/maps/10335/tashkent/?ll=69.166319%2C41.247642&pt=69.166319%2C41.247642&z=17",
    "Shaxrisabz filiali": "https://yandex.uz/maps/101761/shahrisabz/?ll=66.834662%2C39.067837&pt=66.834662%2C39.067837&z=17",
    "Namangan filiali": "https://yandex.uz/maps/21314/namangan/?ll=71.648411%2C40.993736&pt=71.648411%2C40.993736&z=17",
    "Buxoro filiali": "https://yandex.uz/maps/10330/bukhara/?ll=64.427441%2C39.765744&pt=64.427441%2C39.765744&z=17",
    "Qarshi filiali": "https://yandex.uz/maps/10331/karshi/?ll=65.794666%2C38.836639&pt=65.794666%2C38.836639&z=17",
    "Outlet": "https://yandex.uz/maps/?ll=69.146093%2C41.271384&pt=69.146093%2C41.271384&z=17",
}

# Map normalized filial keys to PM Chat IDs from environment variables
FILIAL_PM_MAP = {
    "orikzor_15": os.getenv("Orikzor_15_PM_CHAT_ID"),
    "orikzor_60": os.getenv("Orikzor_60_PM_CHAT_ID"),
    "abusahiy": os.getenv("Abusahiy_PM_CHAT_ID"),
    "issa_showroom": os.getenv("Issa_showroom_PM_CHAT_ID"),
    "malika": os.getenv("Malika_PM_CHAT_ID"),
    "oybek": os.getenv("Oybek_PM_CHAT_ID"),
    "outlet": os.getenv("Outlet_PM_CHAT_ID"),
}


def get_pm_chat_id(filial_name: str) -> str | None:
    """Normalizes filial name (strips apostrophes, spaces, casing) to fetch the PM Chat ID."""
    if not filial_name:
        return None
    normalized_key = (
        filial_name.lower()
        .replace("'", "")
        .replace("`", "")
        .replace(" ", "_")
        .strip()
    )
    return FILIAL_PM_MAP.get(normalized_key)

def get_branch_map_url(branch_name: Optional[str]) -> str:
    default_branch = "Office Energy"
    if not branch_name:
        return BRANCH_MAPS[default_branch]

    cleaned = branch_name.strip()
    if cleaned in BRANCH_MAPS:
        return BRANCH_MAPS[cleaned]

    for key in BRANCH_MAPS:
        if key.lower() == cleaned.lower():
            return BRANCH_MAPS[key]

    for key in BRANCH_MAPS:
        if cleaned.lower() in key.lower() or key.lower() in cleaned.lower():
            return BRANCH_MAPS[key]

    return BRANCH_MAPS[default_branch]


async def send_tg_notification(
    chat_id: int,
    message: str,
    background_tasks: Optional[BackgroundTasks] = None,
    timeout: float = 10.0,
):
    """Send a Telegram message with explicit error logging and safe fallback."""
    if background_tasks is not None:
        background_tasks.add_task(send_tg_notification, chat_id, message, timeout=timeout)
        return

    if not settings.BOT_TOKEN or settings.BOT_TOKEN == "dummy_token":
        logger.error("BOT_TOKEN is missing or invalid in environment variables.")
        return

    if chat_id in (None, ""):
        logger.warning("Skipping Telegram notification because chat_id is empty.")
        return

    url = f"https://api.telegram.org/bot{settings.BOT_TOKEN}/sendMessage"
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            response = await client.post(
                url,
                json={"chat_id": chat_id, "text": message, "parse_mode": "HTML"},
            )
            response.raise_for_status()
        except httpx.TimeoutException:
            logger.exception("Telegram notification timed out for user %s", chat_id)
        except httpx.HTTPStatusError as exc:
            logger.exception(
                "Telegram API HTTP error %s for user %s: %s",
                exc.response.status_code,
                chat_id,
                exc.response.text,
            )
        except Exception:  # noqa: BLE001
            logger.exception("Failed to send Telegram message to %s", chat_id)


async def send_meeting_reminders():
    """
    Background task triggered by apscheduler.
    Scans for meetings happening in the next 24 hours that haven't had a reminder sent.
    """
    now = datetime.now(timezone.utc)
    twenty_four_hours_from_now = now + timedelta(hours=24)

    hr_chat_id = os.getenv("HR_CHAT_ID")
    director_chat_id = os.getenv("DIRECTOR_CHAT_ID")

    with Session(engine) as db:
        upcoming_meetings = db.exec(
            select(Meeting)
            .where(Meeting.meeting_time > now)
            .where(Meeting.meeting_time <= twenty_four_hours_from_now)
            .where(Meeting.reminders_sent == 0)
        ).all()

        for meeting in upcoming_meetings:
            candidate = db.get(CandidateApplication, meeting.candidate_id)
            if not candidate: continue

            user = db.get(User, candidate.user_id)
            vacancy = db.get(Vacancy, candidate.vacancy_id)

            if not user or not vacancy: continue

            candidate_name = user.full_name or "Noma'lum nomzod"
            time_str = meeting.meeting_time.strftime("%Y-%m-%d %H:%M")
            zoom_link = meeting.meeting_link or "Oflayn uchrashuv"

            message_text = (
                f"🔔 *Uchrashuv Eslatmasi*\n\n"
                f"👤 *Nomzod:* {candidate_name}\n"
                f"💼 *Vakansiya:* {vacancy.title}\n"
                f"📅 *Vaqt:* {time_str}\n"
                f"🔗 *Havola/Manzil:* {zoom_link}"
            )

            # 1. Notify Candidate
            if user.telegram_id:
                try:
                    await bot.send_message(chat_id=user.telegram_id, text=message_text, parse_mode="Markdown")
                except Exception as e:
                    print(f"Failed to send reminder to candidate {user.telegram_id}: {e}")

            # 2. Notify HR
            if hr_chat_id:
                try:
                    await bot.send_message(chat_id=hr_chat_id, text=message_text, parse_mode="Markdown")
                except Exception as e:
                    print(f"Failed to send reminder to HR: {e}")

            # 3. Notify Director
            if director_chat_id:
                try:
                    await bot.send_message(chat_id=director_chat_id, text=message_text, parse_mode="Markdown")
                except Exception as e:
                    print(f"Failed to send reminder to Director: {e}")

            # Lock the row from future alerts
            meeting.reminders_sent = 1
            db.add(meeting)

        db.commit()


async def notify_hr_new_application(full_name: str, vacancy_title: str, phone_number: str) -> None:
    """Notify the HR admin chat that a new candidate application has arrived."""
    from bot.main import bot  # adjust to wherever your aiogram Bot instance actually lives
    from config import settings  # adjust if HR_CHAT_ID lives elsewhere (e.g. bot/config.py)

    message_text = (
        "🔔 *Yangi Ariza Tushdi!*\n\n"
        f"👤 Nomzod: {full_name}\n"
        f"💼 Vakansiya: {vacancy_title}\n"
        f"📞 Telefon: {phone_number}\n\n"
        "HR Dashboard orqali kirib ko'rishingiz mumkin."
    )
    try:
        await bot.send_message(
            chat_id=settings.HR_CHAT_ID,
            text=message_text,
            parse_mode="Markdown",
        )
    except Exception:
        logger.exception("Failed to send HR new-application notification")


async def notify_candidate_status(
    telegram_id: int,
    msg_type: str,
    meeting_link_or_loc: Optional[str] = None,
    meeting_time: Optional[str] = None,
    branch_name: Optional[str] = None,
    background_tasks: Optional[BackgroundTasks] = None,
):
    safe_time = meeting_time or "Tez orada ma'lum qilinadi"
    is_http_link = bool(meeting_link_or_loc and meeting_link_or_loc.startswith("http"))

    if branch_name and branch_name.strip():
        display_branch = branch_name.strip()
    elif meeting_link_or_loc and not is_http_link:
        display_branch = meeting_link_or_loc.strip()
    else:
        display_branch = "Izza - Showroom"

    map_url = meeting_link_or_loc if is_http_link else get_branch_map_url(display_branch)
    work_hours = "09:00 - 18:00"

    messages = {
        "accept_1st_meeting": (
            "🎉 <b>Tabriklaymiz!</b>\n\n"
            "Sizning arizangiz bizga ma'qul keldi. Biz siz bilan HR-suhbat o'tkazmoqchimiz!\n\n"
            f"🗓 <b>Vaqti:</b> {safe_time}\n"
            f"🔗 <b>Ulanish uchun havola:</b> <a href='{meeting_link_or_loc}'>Online Suhbat (Zoom/Meet)</a>\n\n"
            "Suhbatda ko'rishguncha! 😊"
        ),
        "accept_2nd_meeting": (
            "🔥 <b>Zo'r yangilik!</b>\n\n"
            "Siz birinchi suhbatdan muvaffaqiyatli o'tdingiz! Endi sizni ofisimizda yuzma-yuz HR suhbatiga taklif qilamiz.\n\n"
            f"🗓 <b>Vaqti:</b> {safe_time}\n"
            f"🏢 <b>Manzil:</b> {display_branch}\n"
            f"⏰ <b>Ish vaqti:</b> {work_hours}\n"
            f"📍 <b>Xarita:</b> <a href='{map_url}'>Lokatsiya (Yandex Maps)</a>\n\n"
            "Kechikmasdan kelishingizni so'raymiz!"
        ),
        "accept_boss_meeting": (
            "🌟 <b>So'nggi Bosqich!</b>\n\n"
            "Siz barcha bosqichlaridan muvaffaqiyatli o'tmoqdasiz. Endi sizni bevosita rahbarimiz bilan yuzma-yuz suhbat kutmoqda!\n\n"
            f"🗓 <b>Vaqti:</b> {safe_time}\n"
            f"🏢 <b>Manzil:</b> {display_branch}\n"
            f"⏰ <b>Ish vaqti:</b> {work_hours}\n"
            f"📍 <b>Xarita:</b> <a href='{map_url}'>Lokatsiya (Yandex Maps)</a>\n\n"
            "Tayyorgarlik ko'ring va ofisimizga tashrif buyuring. Omadingizni bersin! 🎯"
        ),
        "cancel_initial": (
            "👋 <b>Salom!</b>\n\n"
            "Afsuski, ushbu bosqichda sizning nomzodingizni keyingi bosqichga o'tkaza olmaymiz. "
            "Ammo ruhni tushirmang! Sizda ajoyib potensial bor va kelajakda boshqa vakansiyalarimizda "
            "sizni kutib qolamiz. Omad yor bo'lsin! 🚀"
        ),
        "cancel_after_meeting": (
            "🤝 <b>Suhbat uchun raxmat!</b>\n\n"
            "Siz bilan tanishganimizdan juda xursandmiz. Sizning tajribangiz bizda yaxshi taassurot qoldirdi. "
            "Biroq, bu safar biz boshqa nomzodni tanlashga qaror qildik. \n\n"
            "Sizdek intiluvchan insonlar doim o'z o'rnini topadi. Faqat oldinga intiling! 💪"
        ),
    }

    msg_text = messages.get(msg_type)
    if telegram_id and msg_text:
        await send_tg_notification(telegram_id, msg_text, background_tasks=background_tasks)
    else:
        logger.warning("Failed to generate notification: Invalid msg_type '%s' or missing telegram_id.", msg_type)


async def notify_candidate_job_offer(
        telegram_id: int,
        candidate_name: str,
        vacancy_title: str,
        starting_salary: str,
        work_days: str,
        work_hours: str,
        start_datetime_str: str,
        location: str,
) -> None:
    """Formal job-offer message to the candidate. Uses the same HTML-formatted
    send_tg_notification path as notify_candidate_status, since this is the
    same class of candidate-facing pipeline update."""

    # 1. Fetch the map URL using your existing function
    map_url = get_branch_map_url(location)

    # 2. Format the message with the HTML link
    message_text = (
        "🎉 <b>Tabriklaymiz, sizga ish taklif qilinmoqda!</b>\n\n"
        f"Hurmatli {candidate_name}, siz barcha suhbat bosqichlaridan muvaffaqiyatli o'tdingiz. "
        "Quyidagi shartlar asosida sizni jamoamizga taklif qilamiz:\n\n"
        f"💼 <b>Lavozim:</b> {vacancy_title}\n"
        f"💵 <b>Boshlang'ich oylik maosh:</b> {starting_salary}\n"
        f"📅 <b>Ish kunlari:</b> {work_days}\n"
        f"⏰ <b>Ish soatlari:</b> {work_hours}\n"
        f"🗓 <b>Birinchi ish kuningiz:</b> {start_datetime_str}\n"
        f"🏢 <b>Manzil:</b> {location}\n"
        f"📍 <b>Xarita:</b> <a href='{map_url}'>Lokatsiya (Yandex Maps)</a>\n\n"
        "Tabriklaymiz va jamoamizga xush kelibsiz! Savollaringiz bo'lsa, HR bilan bog'laning."
    )

    # No background_tasks here — this function is itself already dispatched as
    # a background task from dashboard.py, so it just sends directly.
    await send_tg_notification(telegram_id, message_text)

async def send_candidate_offered_notification(bot: Bot, candidate, filial_name: str):
    """Sends candidate offer notification along with CV document to the filial's PM."""
    pm_chat_id = get_pm_chat_id(filial_name)

    if not pm_chat_id:
        logger.error(f"No PM Chat ID configured for filial: '{filial_name}'")
        return False

    message_text = (
        f"🎉 <b>Yangi Nomzod Taklifi (Offer)!</b>\n\n"
        f"👤 <b>F.I.SH:</b> {candidate.full_name}\n"
        f"📞 <b>Telefon:</b> {candidate.phone_number}\n"
        f"💼 <b>Lavozim:</b> {getattr(candidate, 'position', 'Ko\'rsatilmagan')}\n"
        f"📍 <b>Filial:</b> {filial_name}\n\n"
        f"📄 Nomzodning rezyumesi (CV) ilova qilindi."
    )

    cv_sent = False
    cv_path = getattr(candidate, "cv_path", None) or getattr(candidate, "cv_file", None)
    cv_file_id = getattr(candidate, "cv_file_id", None)

    # 1. Send CV via server local file path
    if cv_path and os.path.exists(cv_path):
        try:
            document = FSInputFile(cv_path, filename=f"CV_{candidate.full_name}.pdf")
            await bot.send_document(
                chat_id=int(pm_chat_id),
                document=document,
                caption=message_text,
                parse_mode="HTML"
            )
            cv_sent = True
        except Exception as e:
            logger.error(f"Failed to send CV document from path: {e}")

    # 2. Send CV via stored Telegram file_id
    elif cv_file_id:
        try:
            await bot.send_document(
                chat_id=int(pm_chat_id),
                document=cv_file_id,
                caption=message_text,
                parse_mode="HTML"
            )
            cv_sent = True
        except Exception as e:
            logger.error(f"Failed to send CV file_id: {e}")

    # 3. Fallback: Send text notification if CV file is missing
    if not cv_sent:
        await bot.send_message(
            chat_id=int(pm_chat_id),
            text=message_text + "\n\n⚠️ <i>Nomzodning CV fayli tizimda topilmadi.</i>",
            parse_mode="HTML"
        )

    return True

async def notify_director_new_hire(bot: Bot, candidate, filial_name: str):
    """Sends candidate offer notification along with CV document to the filial's PM."""
    pm_chat_id = get_pm_chat_id(filial_name)

    if not pm_chat_id:
        logger.error(f"No PM Chat ID configured for filial: '{filial_name}'")
        return False

    message_text = (
        f"🎉 <b>Yangi Nomzod Taklifi (Offer)!</b>\n\n"
        f"👤 <b>F.I.SH:</b> {candidate.full_name}\n"
        f"📞 <b>Telefon:</b> {candidate.phone_number}\n"
        f"💼 <b>Lavozim:</b> {getattr(candidate, 'position', 'Ko\'rsatilmagan')}\n"
        f"📍 <b>Filial:</b> {filial_name}\n\n"
        f"📄 Nomzodning rezyumesi (CV) ilova qilindi."
    )

    cv_sent = False
    cv_path = getattr(candidate, "cv_path", None) or getattr(candidate, "cv_file", None)
    cv_file_id = getattr(candidate, "cv_file_id", None)

    # 1. Send CV via server local file path
    if cv_path and os.path.exists(cv_path):
        try:
            document = FSInputFile(cv_path, filename=f"CV_{candidate.full_name}.pdf")
            await bot.send_document(
                chat_id=int(pm_chat_id),
                document=document,
                caption=message_text,
                parse_mode="HTML"
            )
            cv_sent = True
        except Exception as e:
            logger.error(f"Failed to send CV document from path: {e}")

    # 2. Send CV via stored Telegram file_id
    elif cv_file_id:
        try:
            await bot.send_document(
                chat_id=int(pm_chat_id),
                document=cv_file_id,
                caption=message_text,
                parse_mode="HTML"
            )
            cv_sent = True
        except Exception as e:
            logger.error(f"Failed to send CV file_id: {e}")

    # 3. Fallback: Send text notification if CV file is missing
    if not cv_sent:
        await bot.send_message(
            chat_id=int(pm_chat_id),
            text=message_text + "\n\n⚠️ <i>Nomzodning CV fayli tizimda topilmadi.</i>",
            parse_mode="HTML"
        )

    return True