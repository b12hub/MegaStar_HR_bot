import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot.config import settings
from bot.handlers.commands import router as commands_router

logger = logging.getLogger(__name__)

# Initialize Bot with DefaultBotProperties (HTML parse mode)
bot = Bot(
    token=settings.BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)

# Initialize Dispatcher and register routers
dp = Dispatcher()
dp.include_router(commands_router)


async def start_bot() -> None:
    """
    Starts Telegram bot polling.
    Can be run as a standalone task or integrated into FastAPI lifecycle hooks.
    """
    logger.info("Starting Telegram Bot polling...")
    try:
        await dp.start_polling(bot)
    except Exception as exc:
        logger.error(f"Error during bot polling: {exc}")
        raise


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(start_bot())
