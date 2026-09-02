import os
from typing import Generator

from dotenv import load_dotenv
from sqlalchemy import text
from sqlmodel import Session, SQLModel, create_engine

import db.models  # noqa: F401

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/megastar_hr")
engine = create_engine(DATABASE_URL, echo=False)


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session


def init_db() -> None:
    # Prefer Alembic migrations in production; this keeps local bootstrap easy while we phase out raw create_all().
    SQLModel.metadata.create_all(engine)
    with engine.begin() as conn:
        try:
            if conn.dialect.name == "postgresql":
                conn.execute(
                    text(
                        "ALTER TABLE IF EXISTS vacancies ADD COLUMN IF NOT EXISTS llm_cost_usd DOUBLE PRECISION DEFAULT 0.0;"
                    )
                )
                conn.execute(
                    text(
                        "ALTER TABLE IF EXISTS candidate_applications ADD COLUMN IF NOT EXISTS objective_score INTEGER DEFAULT 0;"
                    )
                )
                conn.execute(
                    text(
                        "ALTER TABLE IF EXISTS candidate_applications ADD COLUMN IF NOT EXISTS total_score INTEGER DEFAULT 0;"
                    )
                )
                conn.execute(
                    text(
                        "ALTER TABLE IF EXISTS candidate_applications ADD COLUMN IF NOT EXISTS ai_reasoning TEXT;"
                    )
                )
                conn.execute(
                    text(
                        "ALTER TABLE IF EXISTS candidate_applications ADD COLUMN IF NOT EXISTS pipeline_stage VARCHAR(50) DEFAULT 'YANGI';"
                    )
                )
        except Exception as exc:  # pragma: no cover - defensive fallback during migration bootstrap
            print(f"Migration error: {exc}")
