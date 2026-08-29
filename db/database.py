import os
from typing import Generator
from dotenv import load_dotenv
from sqlalchemy import text
from sqlmodel import create_engine, Session, SQLModel
import db.models  # noqa: F401

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/megastar_hr")

engine = create_engine(DATABASE_URL, echo=False)


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session


def init_db() -> None:
    SQLModel.metadata.create_all(engine)
    with engine.begin() as conn:
        try:
            if conn.dialect.name == "postgresql":
                conn.execute(
                    text(
                        "ALTER TABLE vacancy ADD COLUMN IF NOT EXISTS llm_cost_usd DOUBLE PRECISION DEFAULT 0.0;"
                    )
                )
                conn.execute(
                    text(
                        "ALTER TABLE candidate_application ADD COLUMN IF NOT EXISTS objective_score INTEGER DEFAULT 0;"
                    )
                )
                conn.execute(
                    text(
                        "ALTER TABLE candidate_application ADD COLUMN IF NOT EXISTS total_score INTEGER DEFAULT 0;"
                    )
                )
                conn.execute(
                    text(
                        "ALTER TABLE candidate_application ADD COLUMN IF NOT EXISTS ai_reasoning TEXT;"
                    )
                )
                conn.execute(
                    text(
                        "ALTER TABLE candidate_application ADD COLUMN IF NOT EXISTS pipeline_stage VARCHAR(50) DEFAULT 'yangi';"
                    )
                )
        except Exception as e:
            print(f"Migration error: {e}")
            pass

