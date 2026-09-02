import asyncio
import logging
import os
from pathlib import Path
from typing import Optional

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import inspect
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.ext.asyncio import AsyncConnection
from sqlalchemy.engine import Connection
from sqlalchemy.engine.url import make_url
from sqlmodel import SQLModel

from alembic.runtime.migration import MigrationContext

from app.config import DATABASE_URL, engine
from app.model.authentication.mapper_bootstrap import bootstrap_mappers


logger = logging.getLogger(__name__)
MIGRATION_LOCK_ID = 718_420_001_337
LEGACY_BASELINE_REVISION = "95e547b4302d"
MIGRATION_CONNECT_TIMEOUT_SECONDS = int(
    os.getenv("MIGRATION_CONNECT_TIMEOUT_SECONDS", "15")
)
MIGRATION_LOCK_TIMEOUT_SECONDS = int(
    os.getenv("MIGRATION_LOCK_TIMEOUT_SECONDS", "30")
)
MIGRATION_LOCK_POLL_SECONDS = float(
    os.getenv("MIGRATION_LOCK_POLL_SECONDS", "1")
)


def _print_migration_step(message: str) -> None:
    logger.info(
        "Migration step",
        extra={"event": "migration_step", "migration_step": message},
    )


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _escaped_config_url(database_url: str) -> str:
    return database_url.replace("%", "%%")


def _safe_database_url(database_url: str) -> str:
    try:
        return make_url(database_url).render_as_string(hide_password=True)
    except Exception:
        return "<unparseable database url>"


def _build_alembic_config() -> Config:
    project_root = _project_root()
    alembic_ini = project_root / "alembic.ini"
    migrations_dir = project_root / "migrations"

    alembic_cfg = Config(str(alembic_ini))
    alembic_cfg.set_main_option("script_location", str(migrations_dir))
    alembic_cfg.set_main_option("sqlalchemy.url", _escaped_config_url(DATABASE_URL))
    return alembic_cfg


def _get_current_revision(connection: Connection) -> Optional[str]:
    context = MigrationContext.configure(connection)
    return context.get_current_revision()


def _get_public_table_names(connection: Connection) -> set[str]:
    return set(inspect(connection).get_table_names(schema="public"))


def _get_public_columns(connection: Connection, table_name: str) -> set[str]:
    inspector = inspect(connection)
    return {
        column["name"]
        for column in inspector.get_columns(table_name, schema="public")
    }


def _schema_matches_metadata(connection: Connection) -> bool:
    bootstrap_mappers()

    db_tables = _get_public_table_names(connection)
    model_tables = set(SQLModel.metadata.tables)

    if (db_tables - {"alembic_version"}) != model_tables:
        return False

    for table_name, table in SQLModel.metadata.tables.items():
        db_columns = _get_public_columns(connection, table_name)
        model_columns = {column.name for column in table.columns}
        if db_columns != model_columns:
            return False

    return True


def _schema_matches_legacy_baseline(connection: Connection) -> bool:
    db_tables = _get_public_table_names(connection)
    required_tables = {
        "users",
        "roles",
        "user_roles",
        "user_sessions",
        "password_reset_tokens",
        "password_history",
        "candidate_profiles",
        "candidate_resume_details",
        "candidate_resumes",
        "candidate_saved_jobs",
        "company_profiles",
        "contact_us_inquiries",
        "email_verification_tokens",
        "employer_profiles",
        "job_alerts",
        "job_applications",
        "jobs",
        "mobile_verifications",
    }

    if required_tables - db_tables:
        return False

    required_columns = {
        "jobs": {
            "job_id",
            "employer_id",
            "title",
            "description",
            "employment_type",
            "is_deleted",
            "idempotency_key",
        },
        "job_alerts": {
            "alert_id",
            "candidate_id",
            "created_at",
        },
        "candidate_resume_details": {
            "resume_detail_id",
            "candidate_id",
            "education_json",
            "experience_json",
            "skills_json",
            "certifications_json",
        },
    }

    for table_name, columns in required_columns.items():
        if columns - _get_public_columns(connection, table_name):
            return False

    return True


def _infer_unversioned_revision(connection: Connection) -> Optional[str]:
    db_tables = _get_public_table_names(connection)
    app_tables = db_tables - {"alembic_version"}

    if not app_tables:
        return None

    if _schema_matches_metadata(connection):
        return "head"

    if _schema_matches_legacy_baseline(connection):
        return LEGACY_BASELINE_REVISION

    raise RuntimeError(
        "Database has application tables but no alembic_version row, and its "
        "schema does not match a known safe baseline. Refusing to guess a "
        "revision because that could corrupt migration history."
    )


async def _read_current_revision(db_engine: AsyncEngine) -> Optional[str]:
    async with db_engine.connect() as connection:
        return await connection.run_sync(_get_current_revision)


async def _read_current_revision_from_connection(
    connection: AsyncConnection,
) -> Optional[str]:
    return await connection.run_sync(_get_current_revision)


async def _infer_unversioned_revision_from_connection(
    connection: AsyncConnection,
) -> Optional[str]:
    return await connection.run_sync(_infer_unversioned_revision)


async def _release_transaction_locks(connection: AsyncConnection) -> None:
    if connection.in_transaction():
        await connection.commit()


def _pending_revisions(
    script: ScriptDirectory,
    current_revision: Optional[str],
    head_revision: str,
) -> list[str]:
    lower = current_revision or "base"
    revisions = list(script.iterate_revisions(head_revision, lower))
    revisions.reverse()
    return [revision.revision for revision in revisions]


async def _connect_for_migrations():
    try:
        _print_migration_step("connecting to PostgreSQL for migration check")
        connection = await asyncio.wait_for(
            engine.connect(),
            timeout=MIGRATION_CONNECT_TIMEOUT_SECONDS,
        )
        _print_migration_step("connected to PostgreSQL for migration check")
        return connection
    except asyncio.TimeoutError as exc:
        _print_migration_step(
            "timed out connecting to PostgreSQL for migration check"
        )
        raise RuntimeError(
            "Timed out connecting to PostgreSQL while checking Alembic "
            f"migrations after {MIGRATION_CONNECT_TIMEOUT_SECONDS} seconds. "
            "Verify DATABASE_URL and that PostgreSQL is reachable."
        ) from exc


async def _try_acquire_migration_lock(
    connection: AsyncConnection,
    head_revision: str,
) -> bool:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + MIGRATION_LOCK_TIMEOUT_SECONDS

    while True:
        _print_migration_step("trying to acquire Alembic advisory lock")
        result = await connection.execute(
            text("SELECT pg_try_advisory_lock(:lock_id)"),
            {"lock_id": MIGRATION_LOCK_ID},
        )
        if result.scalar_one():
            _print_migration_step("acquired Alembic advisory lock")
            return True

        _print_migration_step("Alembic advisory lock is held by another process")
        current_revision = await _read_current_revision_from_connection(connection)
        if current_revision == head_revision:
            logger.info(
                "Another process held the Alembic migration lock, but the "
                "database is already at head revision %s. Continuing startup.",
                head_revision,
            )
            return False

        if loop.time() >= deadline:
            raise RuntimeError(
                "Timed out waiting for the Alembic migration advisory lock "
                f"after {MIGRATION_LOCK_TIMEOUT_SECONDS} seconds. Another "
                "backend process may be stuck applying migrations. Stop the "
                "old backend process or finish migrations manually with "
                "`alembic upgrade head`."
            )

        logger.warning(
            "Alembic migration lock is held by another process; waiting %.1f "
            "seconds before retrying.",
            MIGRATION_LOCK_POLL_SECONDS,
        )
        await asyncio.sleep(MIGRATION_LOCK_POLL_SECONDS)


async def run_pending_migrations() -> None:
    alembic_cfg = _build_alembic_config()
    script = ScriptDirectory.from_config(alembic_cfg)
    heads = script.get_heads()

    if len(heads) != 1:
        raise RuntimeError(
            "Expected exactly one Alembic head, found "
            f"{len(heads)}: {', '.join(heads)}"
        )

    head_revision = heads[0]
    safe_url = _safe_database_url(DATABASE_URL)

    _print_migration_step(f"checking Alembic migrations for {safe_url}")
    logger.info("Checking Alembic migrations for database %s", safe_url)

    lock_connection = await _connect_for_migrations()
    try:
        logger.info(
            "Trying to acquire PostgreSQL advisory lock for Alembic "
            "migrations: %s",
            MIGRATION_LOCK_ID,
        )
        lock_acquired = await _try_acquire_migration_lock(
            lock_connection,
            head_revision,
        )
        if not lock_acquired:
            return

        try:
            _print_migration_step("reading current Alembic revision")
            current_revision = await _read_current_revision_from_connection(
                lock_connection
            )

            if current_revision is None:
                _print_migration_step(
                    "database has no Alembic revision; inferring safe baseline"
                )
                inferred_revision = await _infer_unversioned_revision_from_connection(
                    lock_connection
                )
                if inferred_revision is not None:
                    _print_migration_step(
                        f"stamping inferred Alembic revision {inferred_revision}"
                    )
                    logger.warning(
                        "Database has schema objects but no Alembic revision; "
                        "stamping revision %s before upgrade.",
                        inferred_revision,
                    )
                    await _release_transaction_locks(lock_connection)
                    await asyncio.to_thread(
                        command.stamp,
                        alembic_cfg,
                        inferred_revision,
                    )
                    current_revision = await _read_current_revision(engine)

            pending = _pending_revisions(script, current_revision, head_revision)
            _print_migration_step(
                "revision state "
                f"current={current_revision or '<base>'} "
                f"head={head_revision} pending_count={len(pending)}"
            )

            logger.info(
                "Alembic revision state: current=%s head=%s pending_count=%d",
                current_revision or "<base>",
                head_revision,
                len(pending),
            )

            if not pending:
                _print_migration_step("database schema is already at latest revision")
                logger.info("Database schema is already at the latest revision.")
                return

            _print_migration_step(
                "running Alembic upgrade head for pending revisions"
            )
            await _release_transaction_locks(lock_connection)
            logger.info("Pending Alembic revisions: %s", " -> ".join(pending))

            try:
                await asyncio.to_thread(command.upgrade, alembic_cfg, "head")
            except Exception:
                _print_migration_step("Alembic upgrade failed")
                logger.exception("Failed to apply Alembic migrations.")
                raise

            _print_migration_step("reading Alembic revision after upgrade")
            new_revision = await _read_current_revision(engine)
            logger.info(
                "Alembic migrations applied successfully: "
                "previous=%s current=%s head=%s",
                current_revision or "<base>",
                new_revision or "<base>",
                head_revision,
            )

            if new_revision != head_revision:
                raise RuntimeError(
                    "Alembic upgrade completed but database revision is "
                    f"{new_revision!r}; expected {head_revision!r}"
                )
        finally:
            _print_migration_step("releasing Alembic advisory lock")
            await lock_connection.execute(
                text("SELECT pg_advisory_unlock(:lock_id)"),
                {"lock_id": MIGRATION_LOCK_ID},
            )
            await _release_transaction_locks(lock_connection)
            logger.info(
                "Released PostgreSQL advisory lock for Alembic migrations: %s",
                MIGRATION_LOCK_ID,
            )
    finally:
        await lock_connection.close()
