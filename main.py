import asyncio
import os
from contextlib import asynccontextmanager

import uvicorn
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles

from api import dashboard, webapp
from api.meetings import router as meetings_router
from api.portal import router as hr_router
from bot.main import bot, dp
from db.database import init_db
from seed import seed_vacancies_if_needed
from services.notifications import send_meeting_reminders  # <-- Added Import

load_dotenv()

scheduler = AsyncIOScheduler()


def register_scheduler_jobs(scheduler_instance: AsyncIOScheduler) -> None:
    """Register periodic jobs, including reminder checks for upcoming meetings."""
    # Runs every 5 hours to scan for meetings and dispatch alerts
    scheduler_instance.add_job(
        send_meeting_reminders,
        "interval",
        hours=5,
        id="meeting-reminders",
        replace_existing=True,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    seed_vacancies_if_needed()
    register_scheduler_jobs(scheduler)
    scheduler.start()
    try:
        yield
    finally:
        scheduler.shutdown(wait=False)


app = FastAPI(title="Mega Star HR Portal", lifespan=lifespan)

# Register API endpoints
app.include_router(hr_router)
app.include_router(webapp.router)
app.include_router(dashboard.router)
app.include_router(meetings_router)

# Serve static files and uploaded CVs
app.mount('/static', StaticFiles(directory='static'), name='static')
app.mount('/uploads', StaticFiles(directory='uploads'), name='uploads')


@app.middleware("http")
async def add_custom_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["ngrok-skip-browser-warning"] = "true"
    response.headers[
        "Content-Security-Policy"
    ] = "script-src 'self' 'unsafe-eval' 'unsafe-inline' https://cdn.tailwindcss.com https://telegram.org; object-src 'none';"
    return response


async def main():
    config = uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="info")
    server = uvicorn.Server(config)

    await asyncio.gather(
        server.serve(),
        dp.start_polling(bot),
    )


if __name__ == "__main__":
    asyncio.run(main())