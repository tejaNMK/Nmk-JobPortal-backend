import asyncio
import os
from logging.config import fileConfig

from dotenv import load_dotenv
from sqlalchemy import engine_from_config
from sqlalchemy import pool
from sqlalchemy import JSON
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import SQLModel

from alembic import context
from alembic.operations import ops


from app.model.authentication.mapper_bootstrap import bootstrap_mappers

bootstrap_mappers()

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

load_dotenv()
database_url = os.getenv("DATABASE_URL")
if database_url:
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))

# Interpret the config file for Python logging.
# This line sets up loggers basically.
fileConfig(config.config_file_name, disable_existing_loggers=False)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
target_metadata = SQLModel.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def compare_server_default(
    context,
    inspected_column,
    metadata_column,
    inspected_default,
    metadata_default,
    rendered_metadata_default,
):
    if isinstance(metadata_column.type, (JSON, JSONB)):
        return False

    return None


def include_object(object, name, type_, reflected, compare_to) -> bool:
    if type_ == "column" and compare_to is not None:
        return False

    if type_ in {"index", "unique_constraint"}:
        return False

    return True


def _filter_autogen_noise(container) -> None:
    filtered_ops = []
    for migration_op in container.ops:
        if isinstance(migration_op, ops.ModifyTableOps):
            _filter_autogen_noise(migration_op)
            if migration_op.ops:
                filtered_ops.append(migration_op)
            continue

        if isinstance(
            migration_op,
            (
                ops.AlterColumnOp,
                ops.CreateIndexOp,
                ops.DropIndexOp,
                ops.DropConstraintOp,
            ),
        ):
            continue

        filtered_ops.append(migration_op)

    container.ops = filtered_ops


def process_revision_directives(context, revision, directives) -> None:
    if not getattr(config.cmd_opts, "autogenerate", False):
        return

    script = directives[0]
    _filter_autogen_noise(script.upgrade_ops)
    _filter_autogen_noise(script.downgrade_ops)

    if script.upgrade_ops.is_empty():
        directives[:] = []


def _ensure_alembic_version_capacity(connection: Connection) -> None:
    if connection.dialect.name != "postgresql":
        return

    connection.exec_driver_sql(
        """
        DO $$
        DECLARE
            version_table regclass;
        BEGIN
            version_table := to_regclass('alembic_version');

            IF version_table IS NULL THEN
                RETURN;
            END IF;

            IF EXISTS (
                SELECT 1
                FROM pg_attribute attribute
                JOIN pg_type data_type
                  ON data_type.oid = attribute.atttypid
                WHERE attribute.attrelid = version_table
                  AND attribute.attname = 'version_num'
                  AND NOT attribute.attisdropped
                  AND data_type.typname = 'varchar'
                  AND attribute.atttypmod > 0
                  AND attribute.atttypmod - 4 < 255
            ) THEN
                EXECUTE format(
                    'ALTER TABLE %s ALTER COLUMN version_num TYPE varchar(255)',
                    version_table
                );
            END IF;
        END
        $$;
        """
    )
    if connection.in_transaction():
        connection.commit()


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.
    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.
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


def do_run_migrations(connection: Connection) -> None:
    _ensure_alembic_version_capacity(connection)

    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_object=include_object,
        compare_type=True,
        compare_server_default=compare_server_default,
        process_revision_directives=process_revision_directives,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations in 'online' mode.
    In this scenario we need to create an Engine
    and associate a connection with the context.
    """
    connectable = AsyncEngine(
        engine_from_config(
            config.get_section(config.config_ini_section),
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
            future=True,
            connect_args={
                "timeout": int(os.getenv("DB_CONNECT_TIMEOUT_SECONDS", "10")),
            },
        )
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
