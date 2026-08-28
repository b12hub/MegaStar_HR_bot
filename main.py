import asyncio
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from api import dashboard, webapp
from api.portal import router as hr_router
from bot.main import bot, dp
from db.database import init_db
from seed import seed_vacancies_if_needed


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    seed_vacancies_if_needed()
    yield

# def close_terminal():
#     """Close the terminal gracefully."""
#     print("Shutting down the application...")
#     # Add any cleanup logic here if needed
#     # For example, closing database connections, stopping background tasks, etc.
#     asyncio.get_event_loop().stop()
app = FastAPI(title="Mega Star HR Portal", lifespan=lifespan)

# Register API endpoints
app.include_router(hr_router)
app.include_router(webapp.router)
app.include_router(dashboard.router)

# Serve static files and uploaded CVs
app.mount('/static', StaticFiles(directory='static'), name='static')
app.mount('/uploads', StaticFiles(directory='uploads'), name='uploads')



async def main():
    # Setup Uvicorn server configuration
    config = uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="info")
    server = uvicorn.Server(config)

    # Run FastAPI and Telegram Bot polling concurrently
    await asyncio.gather(
        server.serve(),
        dp.start_polling(bot),
    )


if __name__ == "__main__":
    asyncio.run(main())