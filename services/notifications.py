import logging
import httpx
from typing import Optional
from bot.config import settings

# Setup logger
logger = logging.getLogger(__name__)

# Branch location registry with Yandex Maps URLs[cite: 25]
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
    "Outlet": "https://yandex.uz/maps/?ll=69.146093%2C41.271384&pt=69.146093%2C41.271384&z=17"
}


def get_branch_map_url(branch_name: Optional[str]) -> str:
    """
    Safely resolves a branch name to its Yandex Maps URL.
    Supports case-insensitive and partial string matching.
    """
    default_branch = "Izza - Showroom"
    if not branch_name:
        return BRANCH_MAPS[default_branch]

    cleaned = branch_name.strip()

    # 1. Exact match
    if cleaned in BRANCH_MAPS:
        return BRANCH_MAPS[cleaned]

    # 2. Case-insensitive exact match
    for key in BRANCH_MAPS:
        if key.lower() == cleaned.lower():
            return BRANCH_MAPS[key]

    # 3. Substring / partial match
    for key in BRANCH_MAPS:
        if cleaned.lower() in key.lower() or key.lower() in cleaned.lower():
            return BRANCH_MAPS[key]

    return BRANCH_MAPS[default_branch]


async def send_tg_notification(chat_id: int, message: str):
    """
    Sends a formatted HTML message directly to a user via the Telegram Bot API.
    """
    if not settings.BOT_TOKEN or settings.BOT_TOKEN == "dummy_token":
        logger.error("BOT_TOKEN is missing or invalid in environment variables.")
        return

    url = f"https://api.telegram.org/bot{settings.BOT_TOKEN}/sendMessage"

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

    # Determine if meeting_link_or_loc contains a web link (Zoom/Meet/Custom map)
    is_http_link = bool(meeting_link_or_loc and meeting_link_or_loc.startswith("http"))

    # Resolve display branch: check branch_name first, then non-HTTP location input, then fallback
    if branch_name and branch_name.strip():
        display_branch = branch_name.strip()
    elif meeting_link_or_loc and not is_http_link:
        display_branch = meeting_link_or_loc.strip()
    else:
        display_branch = "Izza - Showroom"

    # Resolve map URL: use custom HTTP link if provided, otherwise resolve branch map
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
        )
    }

    msg_text = messages.get(msg_type)
    if telegram_id and msg_text:
        await send_tg_notification(telegram_id, msg_text)
    else:
        logger.warning(f"Failed to generate notification: Invalid msg_type '{msg_type}' or missing telegram_id.")