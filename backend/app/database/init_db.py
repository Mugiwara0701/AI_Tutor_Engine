"""
Database setup script.

Connects to the Supabase Postgres database via DATABASE_URL and creates
all required tables (and indexes) if they do not already exist.

Safe to run multiple times: SQLAlchemy's create_all only creates tables
that are missing, and never drops or truncates existing tables/data.

Usage:
    python -m app.database.init_db
"""

import sys

from sqlalchemy import inspect, text

from app.database.postgres import Base, engine, check_connection

# Import models so they're registered on Base.metadata before create_all runs.
from app.models import database_models  # noqa: F401


REQUIRED_TABLES = [
    "user_profiles",
    "dashboard_sessions",
    "dashboard_activity_logs",
    "system_settings",
]

# Extra indexes beyond what Column(index=True) already gives us.
EXTRA_INDEX_STATEMENTS = [
    "CREATE INDEX IF NOT EXISTS idx_dashboard_sessions_active "
    "ON dashboard_sessions (user_id, is_active);",
    "CREATE INDEX IF NOT EXISTS idx_activity_logs_user_created "
    "ON dashboard_activity_logs (user_id, created_at DESC);",
    "CREATE INDEX IF NOT EXISTS idx_user_profiles_email ON user_profiles (email);",
]

# Postgres has no "ADD CONSTRAINT IF NOT EXISTS", so this is wrapped in a
# guarded DO block: it's a no-op if the constraint is already there (e.g.
# on a table created after CheckConstraint was added to the ORM model),
# and adds it once for pre-existing tables that predate this change.
# NOTE: if any existing rows already have a role outside
# ('admin', 'manager', 'user'), this ALTER will fail — clean those up
# first, e.g.: UPDATE user_profiles SET role = 'user' WHERE role NOT IN
# ('admin', 'manager', 'user');
ROLE_CHECK_CONSTRAINT_STATEMENT = """
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'ck_user_profiles_role'
    ) THEN
        ALTER TABLE user_profiles
            ADD CONSTRAINT ck_user_profiles_role
            CHECK (role IN ('admin', 'manager', 'user'));
    END IF;
END $$;
"""


def create_tables() -> None:
    print("→ Checking database connection...")
    if not check_connection():
        print("✗ Could not connect to the database. Check DATABASE_URL in .env")
        sys.exit(1)
    print("✓ Database connection OK")

    print("→ Creating tables (skips ones that already exist)...")
    Base.metadata.create_all(bind=engine, checkfirst=True)

    print("→ Ensuring extra indexes exist...")
    with engine.begin() as conn:
        for stmt in EXTRA_INDEX_STATEMENTS:
            conn.execute(text(stmt))

    print("→ Ensuring role check constraint exists...")
    with engine.begin() as conn:
        conn.execute(text(ROLE_CHECK_CONSTRAINT_STATEMENT))

    verify_tables()


def verify_tables() -> None:
    inspector = inspect(engine)
    existing = set(inspector.get_table_names())
    missing = [t for t in REQUIRED_TABLES if t not in existing]

    if missing:
        print(f"✗ Missing tables after create_all: {missing}")
        sys.exit(1)

    print("✓ All required tables exist:")
    for t in REQUIRED_TABLES:
        print(f"   - {t}")


if __name__ == "__main__":
    create_tables()
    print("\nDatabase setup complete.")
