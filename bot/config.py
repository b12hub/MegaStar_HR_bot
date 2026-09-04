from pydantic import Field, AliasChoices
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    PROJECT_NAME: str = "Mega Star HR Portal"
    WEBAPP_URL: str = "https://example.com"
    SECRET_KEY: str = "mega-star-hr-secret-key"

    # Database
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/megastar_hr"

    # Telegram Bot
    BOT_TOKEN: str = Field(
        default="dummy_token",
        validation_alias=AliasChoices("TELEGRAM_BOT_TOKEN", "BOT_TOKEN")
    )
    HR_NOTIFICATION_CHAT_ID: Optional[int] = None
    HR_CHAT_ID: str | int
    DIRECTOR_NOTIFICATION_CHAT_ID: Optional[int] = None
    DIRECTOR_CHAT_ID: str | int

    # AI APIs
    OPENAI_API_KEY: Optional[str] = None
    ANTHROPIC_API_KEY: Optional[str] = None

    # Google Sheets
    GOOGLE_SHEETS_CREDENTIALS_FILE: Optional[str] = None
    GOOGLE_SHEET_NAME: Optional[str] = None

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()