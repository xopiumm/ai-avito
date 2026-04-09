"""Alembic environment configuration.

This module configures Alembic for database migrations.
It handles both offline (generate SQL) and online (execute directly) modes.
"""

from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# Add src to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.weather_alerts.config import Base
from src.weather_alerts.config.settings import get_settings

# This is the Alembic Config object, which provides
# the values of the [alembic] section of the alembic.ini
# file as Python variables within the script file.
# config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Set the sqlalchemy.url from settings
settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.db.url)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL and not an Engine,
    though an Engine is acceptable here as well. By skipping the
    create_engine() call we avoid even needing a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.
    """
    configuration = config.get_section(config.config_ini_section)
    configuration["sqlalchemy.url"] = settings.db.url

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        echo=settings.db.echo,
    )

    with connectable.begin() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,  # Compare column types during autogenerate
            compare_server_default=True,  # Compare server defaults
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
