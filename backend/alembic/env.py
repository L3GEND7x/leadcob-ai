"""Migration context uses the same database configuration as the application."""
from alembic import context
from app.db import models  # noqa: F401: register all tables
from app.db.database import Base, engine

target_metadata = Base.metadata


def run_migrations_online():
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata,
                          compare_type=True, render_as_batch=connection.dialect.name == 'sqlite')
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    raise RuntimeError('Use migrações online para verificar o banco de destino.')
run_migrations_online()
