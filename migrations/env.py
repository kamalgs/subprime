"""Alembic migration environment."""
import os
import sys
from pathlib import Path
from alembic import context

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

config = context.config
database_url = os.environ.get("DATABASE_URL", config.get_main_option("sqlalchemy.url"))


def run_migrations_offline():
    context.configure(url=database_url, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    from sqlalchemy import create_engine, pool
    engine = create_engine(database_url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
