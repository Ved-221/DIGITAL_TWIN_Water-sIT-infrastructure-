from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker
import os
import sys

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
    SQLALCHEMY_DATABASE_URL = "sqlite:///./infratwin.db"
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def init_db():
    Base.metadata.create_all(bind=engine)
    with engine.connect() as conn:
        try:
            result = conn.execute(text("PRAGMA table_info(dependencies);")).fetchall()
            existing_cols = {row[1] for row in result}
            if existing_cols:
                if "source_component_id" not in existing_cols:
                    conn.execute(text("ALTER TABLE dependencies ADD COLUMN source_component_id VARCHAR;"))
                    conn.execute(text("UPDATE dependencies SET source_component_id = source_id WHERE source_component_id IS NULL;"))
                if "target_component_id" not in existing_cols:
                    conn.execute(text("ALTER TABLE dependencies ADD COLUMN target_component_id VARCHAR;"))
                    conn.execute(text("UPDATE dependencies SET target_component_id = target_id WHERE target_component_id IS NULL;"))
                if "source" not in existing_cols:
                    conn.execute(text("ALTER TABLE dependencies ADD COLUMN source VARCHAR DEFAULT 'aws_api';"))
                    conn.execute(text("UPDATE dependencies SET source = discovery_source WHERE source IS NULL;"))
                if "discovery_source" not in existing_cols:
                    conn.execute(text("ALTER TABLE dependencies ADD COLUMN discovery_source VARCHAR DEFAULT 'aws_api';"))
                    conn.execute(text("UPDATE dependencies SET discovery_source = source WHERE discovery_source IS NULL;"))
                if "metadata" not in existing_cols:
                    conn.execute(text("ALTER TABLE dependencies ADD COLUMN metadata JSON DEFAULT '{}';"))
                conn.commit()


            # Migrate components table if needed
            comp_result = conn.execute(text("PRAGMA table_info(components);")).fetchall()
            comp_cols = {row[1] for row in comp_result}
            if comp_cols:
                if "discovery_source" not in comp_cols:
                    conn.execute(text("ALTER TABLE components ADD COLUMN discovery_source VARCHAR DEFAULT 'manual';"))
                if "account_id" not in comp_cols:
                    conn.execute(text("ALTER TABLE components ADD COLUMN account_id VARCHAR;"))
                if "availability_zone" not in comp_cols:
                    conn.execute(text("ALTER TABLE components ADD COLUMN availability_zone VARCHAR;"))
                if "arn" not in comp_cols:
                    conn.execute(text("ALTER TABLE components ADD COLUMN arn VARCHAR;"))
                if "aws_region" not in comp_cols:
                    conn.execute(text("ALTER TABLE components ADD COLUMN aws_region VARCHAR;"))
                if "source_environment" not in comp_cols:
                    conn.execute(text("ALTER TABLE components ADD COLUMN source_environment VARCHAR DEFAULT 'aws';"))
                if "domain" not in comp_cols:
                    conn.execute(text("ALTER TABLE components ADD COLUMN domain VARCHAR DEFAULT 'general';"))
                if "properties" not in comp_cols:
                    conn.execute(text("ALTER TABLE components ADD COLUMN properties JSON DEFAULT '{}';"))
                conn.commit()
            # Ensure twin_state row exists
            try:
                ts_result = conn.execute(text("SELECT id FROM twin_state WHERE id = 1;")).fetchone()
                if not ts_result:
                    conn.execute(text("INSERT INTO twin_state (id, mode, discovery_status, discovery_summary) VALUES (1, 'unconnected', 'idle', '{}');"))
                    conn.commit()
            except Exception:
                pass
        except Exception:
            pass

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

