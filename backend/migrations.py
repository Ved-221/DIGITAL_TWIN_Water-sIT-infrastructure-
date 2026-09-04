import logging
from sqlalchemy import inspect, text
from database import Base, engine
import models

logger = logging.getLogger("infratwin.migrations")

def run_migrations(target_engine=None):
    """
    Ensures safe schema evolution for SQLite / relational databases without data loss.
    1. Creates all missing tables defined in Base.metadata.
    2. Inspects existing tables and dynamically adds any missing columns defined on SQLAlchemy models via ALTER TABLE.
    """
    eng = target_engine or engine
    Base.metadata.create_all(bind=eng)

    inspector = inspect(eng)
    for table_name, table in Base.metadata.tables.items():
        if not inspector.has_table(table_name):
            continue

        existing_columns = {col["name"] for col in inspector.get_columns(table_name)}
        for column in table.columns:
            if column.name not in existing_columns:
                col_type = column.type.compile(eng.dialect)
                default_clause = ""
                if column.default is not None and hasattr(column.default, 'arg') and isinstance(column.default.arg, (str, int, float)):
                    val = column.default.arg
                    default_clause = f" DEFAULT '{val}'" if isinstance(val, str) else f" DEFAULT {val}"
                
                alter_sql = f"ALTER TABLE {table_name} ADD COLUMN {column.name} {col_type}{default_clause}"
                try:
                    with eng.connect() as conn:
                        conn.execute(text(alter_sql))
                        conn.commit()
                        logger.info(f"Migrated table '{table_name}': added column '{column.name}' ({col_type})")
                except Exception as e:
                    logger.warning(f"Could not add column '{column.name}' to table '{table_name}': {e}")
