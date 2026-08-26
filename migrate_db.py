import sys
from sqlalchemy import text
from sqlmodel import SQLModel
from db.database import engine, init_db
import db.models  # noqa: F401


def run_migration():
    print("Executing SQLModel metadata create_all...")
    init_db()
    
    with engine.begin() as conn:
        print(f"Connected to database engine: {conn.dialect.name}")
        if conn.dialect.name == "postgresql":
            print("Applying ALTER TABLE vacancy ADD COLUMN IF NOT EXISTS llm_cost_usd DOUBLE PRECISION DEFAULT 0.0;")
            conn.execute(
                text("ALTER TABLE vacancy ADD COLUMN IF NOT EXISTS llm_cost_usd DOUBLE PRECISION DEFAULT 0.0;")
            )
        else:
            print(f"Skipping Postgres-specific ALTER on {conn.dialect.name} dialect.")
            
    print("Migration finished successfully.")


if __name__ == "__main__":
    run_migration()
