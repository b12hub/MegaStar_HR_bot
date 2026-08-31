import asyncio
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI , Request
from fastapi.staticfiles import StaticFiles
from api import dashboard, webapp
from api.portal import router as hr_router
from bot.main import bot, dp
from db.database import init_db
from seed import seed_vacancies_if_needed

import os
from dotenv import load_dotenv
load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    seed_vacancies_if_needed()
    yield

app = FastAPI(title="Mega Star HR Portal", lifespan=lifespan)

# Register API endpoints
app.include_router(hr_router)
app.include_router(webapp.router)
app.include_router(dashboard.router)

# Serve static files and uploaded CVs
app.mount('/static', StaticFiles(directory='static'), name='static')
app.mount('/uploads', StaticFiles(directory='uploads'), name='uploads')


# Combined Middleware for all custom headers
@app.middleware("http")
async def add_custom_security_headers(request: Request, call_next):
    response = await call_next(request)

    # 1. Ngrok warning bypass
    response.headers["ngrok-skip-browser-warning"] = "true"

    # 2. CSP Fix for Tailwind and unsafe-eval
    response.headers[
        "Content-Security-Policy"] = "script-src 'self' 'unsafe-eval' 'unsafe-inline' https://cdn.tailwindcss.com; object-src 'none';"

    return response


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