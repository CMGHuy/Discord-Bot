"""Alembic environment using the application URL and declared schema."""
from logging.config import fileConfig

from alembic import context

from swingbot import config as app_config
from swingbot.core.db.engine import get_engine
from swingbot.core.db.schema import METADATA

cfg = context.config
if cfg.config_file_name is not None:
    fileConfig(cfg.config_file_name)

target_metadata = METADATA


def run_migrations_offline() -> None:
    """Generate SQL without opening a database connection."""
    context.configure(
        url=app_config.DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations through the process-local application engine."""
    # Tests hand Alembic their rollback-isolated connection explicitly.  The
    # running application has no such attribute and retains its singleton
    # engine/pool path below.
    supplied = cfg.attributes.get("connection")
    if supplied is not None:
        context.configure(connection=supplied, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
        return
    with get_engine().connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
