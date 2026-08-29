import httpx
import os
import logging

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
logger = logging.getLogger(__name__)

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

async def send_tg_notification(chat_id: int, message: str):
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN is not set.")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                url,
                json={"chat_id": chat_id, "text": message, "parse_mode": "HTML"}
            )
            response.raise_for_status()
        except Exception as e:
            logger.error(f"Failed to send Telegram message to {chat_id}: {str(e)}")


async def notify_candidate_status(chat_id: int, status_type: str, meeting_link: str = None, meeting_time: str = None):
    messages = {
        "cancel_initial": (
            "👋 <b>Salom!</b>\n\n"
            "Afsuski, ushbu bosqichda sizning nomzodingizni keyingi bosqichga o'tkaza olmaymiz. "
            "Ammo ruhni tushirmang! Sizda ajoyib potensial bor va kelajakda boshqa vakansiyalarimizda "
            "sizni kutib qolamiz. Omad yor bo'lsin! 🚀"
        ),
        "accept_1st_meeting": (
            "🎉 <b>Tabriklaymiz!</b>\n\n"
            "Sizning arizangiz bizga ma'qul keldi. Biz siz bilan HR-suhbat o'tkazmoqchimiz!\n\n"
            f"🗓 <b>Vaqti:</b> {meeting_time or 'Tez orada'}\n"
            f"🔗 <b>Ulanish:</b> <a href='{meeting_link}'>Zoom / Google Meet Link</a>\n\n"
            "Suhbatda ko'rishguncha! 😊"
        ),
        "accept_2nd_meeting": (
            "🔥 <b>Zo'r yangilik!</b>\n\n"
            "Siz birinchi suhbatdan muvaffaqiyatli o'tdingiz! Endi sizni ofisimizda yuzma-yuz suhbatga taklif qilamiz.\n\n"
            f"🗓 <b>Vaqti:</b> {meeting_time or 'Tez orada'}\n"
            "🏢 <b>Manzilimizni xaritada ko'ring:</b>\n"
            "📍 <a href='https://maps.google.com/?q=Tashkent'>Google Maps</a>\n"
            "🚕 <a href='https://yandex.com/maps/'>Yandex Go</a>\n\n"
            "Kechikmasdan kelishingizni so'raymiz!"
        ),
        "cancel_after_meeting": (
            "🤝 <b>Suhbat uchun raxmat!</b>\n\n"
            "Siz bilan tanishganimizdan juda xursandmiz. Sizning tajribangiz bizda yaxshi taassurot qoldirdi. "
            "Biroq, bu safar biz boshqa nomzodni tanlashga qaror qildik. \n\n"
            "Sizdek intiluvchan insonlar doim o'z o'rnini topadi. Faqat oldinga intiling! 💪"
        ),
        "accept_boss_meeting": (
            "🌟 <b>So'nggi Bosqich!</b>\n\n"
            "Siz barcha HR bosqichlaridan o'tdingiz. Endi sizni bevosita rahbarimiz bilan suhbat kutmoqda!\n\n"
            f"🗓 <b>Vaqti:</b> {meeting_time or 'Tez orada'}\n"
            "Tayyorgarlik ko'ring va ofisimizga tashrif buyuring. Omadingizni bersin! 🎯"
        )
    }

    msg_text = messages.get(status_type)
    if chat_id and msg_text:
        await send_tg_notification(chat_id, msg_text)