import logging
from typing import Optional

import httpx
from fastapi import BackgroundTasks

from bot.config import settings

logger = logging.getLogger(__name__)

BRANCH_MAPS = {
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


def get_branch_map_url(branch_name: Optional[str]) -> str:
    default_branch = "Izza - Showroom"
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
            "Siz barcha HR bosqichlaridan muvaffaqiyatli o'tdingiz. Endi sizni bevosita rahbarimiz bilan yuzma-yuz suhbat kutmoqda!\n\n"
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
