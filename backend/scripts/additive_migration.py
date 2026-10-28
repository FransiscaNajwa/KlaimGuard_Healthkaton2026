"""Small, additive SQLite schema changes for local demo upgrades."""

from sqlalchemy import Engine, inspect, text


def migrate_additive_schema(engine: Engine) -> None:
    inspector = inspect(engine)
    if "claims" in inspector.get_table_names():
        claim_columns = {column["name"] for column in inspector.get_columns("claims")}
        if "facility_id" not in claim_columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE claims ADD COLUMN facility_id INTEGER"))
            with engine.begin() as connection:
                connection.execute(text("CREATE INDEX IF NOT EXISTS ix_claims_facility_id ON claims (facility_id)"))

    if "dispute_cases" in inspector.get_table_names():
        dispute_columns = {column["name"] for column in inspector.get_columns("dispute_cases")}
        if "template_code" not in dispute_columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE dispute_cases ADD COLUMN template_code VARCHAR(30) NOT NULL DEFAULT 'formal'"))
        if "deadline_at" not in dispute_columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE dispute_cases ADD COLUMN deadline_at DATETIME"))
            with engine.begin() as connection:
                connection.execute(text("CREATE INDEX IF NOT EXISTS ix_dispute_cases_deadline_at ON dispute_cases (deadline_at)"))
        if "received_at" not in dispute_columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE dispute_cases ADD COLUMN received_at DATETIME"))
