from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker
import os
import sys

# Load environment variables from .env if present
try:
    from dotenv import load_dotenv
    backend_dir = os.path.dirname(os.path.abspath(__file__))
    load_dotenv(os.path.join(backend_dir, ".env"))
    load_dotenv(os.path.join(os.path.dirname(backend_dir), ".env"))
except ImportError:
    pass

_is_test = "pytest" in sys.modules or bool(os.environ.get("PYTEST_CURRENT_TEST")) or bool(os.environ.get("TESTING"))
if _is_test:
    from sqlalchemy.pool import StaticPool
    SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool
    )
else:
    DB_PATH = os.environ.get("DATABASE_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "infratwin.db"))
    SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_PATH}"
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def init_db():
    Base.metadata.create_all(bind=engine)
    with engine.connect() as conn:
        # Migrate dependencies table if needed
        try:
            result = conn.execute(text("PRAGMA table_info(dependencies);")).fetchall()
            existing_cols = {row[1] for row in result}
            if existing_cols:
                dep_cols_to_add = [
                    ("source_component_id", "VARCHAR"),
                    ("target_component_id", "VARCHAR"),
                    ("source", "VARCHAR DEFAULT 'aws_api'"),
                    ("discovery_source", "VARCHAR DEFAULT 'aws_api'"),
                    ("metadata", "JSON DEFAULT '{}'")
                ]
                for col_name, col_type in dep_cols_to_add:
                    if col_name not in existing_cols:
                        try:
                            conn.execute(text(f"ALTER TABLE dependencies ADD COLUMN {col_name} {col_type};"))
                            conn.commit()
                        except Exception:
                            pass

                # Backfill source_component_id and target_component_id
                try:
                    conn.execute(text("UPDATE dependencies SET source_component_id = source_id WHERE source_component_id IS NULL AND source_id IS NOT NULL;"))
                    conn.execute(text("UPDATE dependencies SET target_component_id = target_id WHERE target_component_id IS NULL AND target_id IS NOT NULL;"))
                    conn.commit()
                except Exception:
                    pass
        except Exception:
            pass

        # Migrate components table if needed
        try:
            comp_result = conn.execute(text("PRAGMA table_info(components);")).fetchall()
            comp_cols = {row[1] for row in comp_result}
            if comp_cols:
                comp_cols_to_add = [
                    ("discovery_source", "VARCHAR DEFAULT 'manual'"),
                    ("account_id", "VARCHAR"),
                    ("availability_zone", "VARCHAR"),
                    ("arn", "VARCHAR"),
                    ("aws_region", "VARCHAR"),
                    ("source_environment", "VARCHAR DEFAULT 'aws'"),
                    ("domain", "VARCHAR DEFAULT 'general'"),
                    ("properties", "JSON DEFAULT '{}'")
                ]
                for col_name, col_type in comp_cols_to_add:
                    if col_name not in comp_cols:
                        try:
                            conn.execute(text(f"ALTER TABLE components ADD COLUMN {col_name} {col_type};"))
                            conn.commit()
                        except Exception:
                            pass
        except Exception:
            pass

        # Ensure twin_state row exists
        try:
            ts_result = conn.execute(text("SELECT id FROM twin_state WHERE id = 1;")).fetchone()
            if not ts_result:
                conn.execute(text("INSERT INTO twin_state (id, mode, discovery_status, discovery_summary) VALUES (1, 'unconnected', 'idle', '{}');"))
                conn.commit()
        except Exception:
            pass

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

