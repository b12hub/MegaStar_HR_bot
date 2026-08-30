import os
import logging
import httpx
from typing import Optional

# Setup logger and Telegram Token
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
logger = logging.getLogger(__name__)

# Branch location registry with Yandex Maps URLs[cite: 25]
BRANCH_MAPS = {
    "Izza - Showroom": "https://yandex.uz/maps/?pt=69.146093,41.271384&z=17&l=map",
    "Malika bozori, A3-do'kon": "https://yandex.uz/maps/?pt=69.270693,41.339429&z=17&l=map",
    "O'rikzor bozori, 5-blok C15-do'kon": "https://yandex.uz/maps/?pt=69.150056,41.285935&z=17&l=map",
    "O'rikzor bozori, 5-blok 60-do'kon": "https://yandex.uz/maps/?pt=69.150225,41.285909&z=17&l=map",
    "Abusaxiy bozori, E111-do'kon": "https://yandex.uz/maps/?pt=69.166319,41.247642&z=17&l=map",
    "Shaxrisabz filiali": "https://yandex.uz/maps/?pt=66.834662,39.067837&z=17&l=map",
    "Namangan filiali": "https://yandex.uz/maps/?pt=71.648411,40.993736&z=17&l=map",
    "Buxoro filiali": "https://yandex.uz/maps/?pt=64.427441,39.765744&z=17&l=map",
    "Qarshi filiali": "https://yandex.uz/maps/?pt=65.794666,38.836639&z=17&l=map",
    "Outlet": "https://yandex.uz/maps/?pt=69.146093,41.271384&z=17&l=map"
}


def get_branch_map_url(branch_name: Optional[str]) -> str:
    """
    Safely resolves a branch name to its Yandex Maps URL.
    Falls back to the main 'Izza - Showroom' if not found.
    """
    default_branch = "Izza - Showroom"
    if branch_name and branch_name in BRANCH_MAPS:
        return BRANCH_MAPS[branch_name]
    return BRANCH_MAPS[default_branch]


async def send_tg_notification(chat_id: int, message: str):
    """
    Sends a formatted HTML message directly to a user via the Telegram Bot API[cite: 25].
    """
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN is not set in environment variables.")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    async with httpx.AsyncClient() as client:
        try:
            # Enforce parse_mode="HTML" so clickable hyperlinks render correctly[cite: 25]
            response = await client.post(
                url,
                json={"chat_id": chat_id, "text": message, "parse_mode": "HTML"}
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            logger.error(f"Telegram API HTTP error {e.response.status_code} for user {chat_id}: {e.response.text}")
        except Exception as e:
            logger.error(f"Failed to send Telegram message to {chat_id}: {str(e)}")


async def notify_candidate_status(
        telegram_id: int,
        msg_type: str,
        meeting_link_or_loc: Optional[str] = None,
        meeting_time: Optional[str] = None,
        branch_name: Optional[str] = None
):
    """
    Generates and dispatches dynamic notification templates based on candidate stage.
    """
    # Safe defaults for dynamic variables
    safe_time = meeting_time or "Tez orada ma'lum qilinadi"

    # Check if HR manually supplied a location in the link field, otherwise default to branch map resolution
    display_branch = branch_name or "Izza - Showroom"
    map_url = meeting_link_or_loc if (
                meeting_link_or_loc and meeting_link_or_loc.startswith("http")) else get_branch_map_url(display_branch)
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
            "Afsuski, ushbu bosqichda sizning nomzodingizni keyingi bosqichga o'tkaza olmaymiz[cite: 25]. "
            "Ammo ruhni tushirmang! Sizda ajoyib potensial bor va kelajakda boshqa vakansiyalarimizda "
            "sizni kutib qolamiz. Omad yor bo'lsin! 🚀[cite: 25]"
        ),
        "cancel_after_meeting": (
            "🤝 <b>Suhbat uchun raxmat!</b>\n\n"
            "Siz bilan tanishganimizdan juda xursandmiz. Sizning tajribangiz bizda yaxshi taassurot qoldirdi[cite: 25]. "
            "Biroq, bu safar biz boshqa nomzodni tanlashga qaror qildik[cite: 25]. \n\n"
            "Sizdek intiluvchan insonlar doim o'z o'rnini topadi. Faqat oldinga intiling! 💪[cite: 25]"
        )
    }

    msg_text = messages.get(msg_type)
    if telegram_id and msg_text:
        await send_tg_notification(telegram_id, msg_text)
    else:
        logger.warning(f"Failed to generate notification: Invalid msg_type '{msg_type}' or missing telegram_id.")