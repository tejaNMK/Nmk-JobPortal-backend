import pytest

from app import config


DB_POOL_ENV_VARS = [
    "DB_POOL_SIZE",
    "DB_MAX_OVERFLOW",
    "DB_POOL_TIMEOUT_SECONDS",
    "DB_POOL_RECYCLE_SECONDS",
    "DB_POOL_PRE_PING",
    "DB_CONNECT_TIMEOUT_SECONDS",
    "DB_COMMAND_TIMEOUT_SECONDS",
]


def test_database_pool_settings_defaults(monkeypatch):
    for name in DB_POOL_ENV_VARS:
        monkeypatch.delenv(name, raising=False)

    settings = config.get_database_pool_settings()

    assert settings.pool_size == 10
    assert settings.max_overflow == 5
    assert settings.pool_timeout_seconds == 10
    assert settings.pool_recycle_seconds == 1800
    assert settings.pool_pre_ping is True
    assert settings.connect_timeout_seconds == 10
    assert settings.command_timeout_seconds == 30
    assert settings.max_connections_per_process == 15


def test_database_pool_settings_env_overrides(monkeypatch):
    monkeypatch.setenv("DB_POOL_SIZE", "7")
    monkeypatch.setenv("DB_MAX_OVERFLOW", "3")
    monkeypatch.setenv("DB_POOL_TIMEOUT_SECONDS", "4")
    monkeypatch.setenv("DB_POOL_RECYCLE_SECONDS", "900")
    monkeypatch.setenv("DB_POOL_PRE_PING", "false")
    monkeypatch.setenv("DB_CONNECT_TIMEOUT_SECONDS", "6")
    monkeypatch.setenv("DB_COMMAND_TIMEOUT_SECONDS", "11")

    settings = config.get_database_pool_settings()

    assert settings == config.DatabasePoolSettings(
        pool_size=7,
        max_overflow=3,
        pool_timeout_seconds=4,
        pool_recycle_seconds=900,
        pool_pre_ping=False,
        connect_timeout_seconds=6,
        command_timeout_seconds=11,
    )


@pytest.mark.parametrize(
    ("name", "value", "message"),
    [
        ("DB_POOL_SIZE", "abc", "DB_POOL_SIZE must be an integer value"),
        ("DB_POOL_SIZE", "0", "DB_POOL_SIZE must be greater than or equal to 1"),
        ("DB_MAX_OVERFLOW", "-1", "DB_MAX_OVERFLOW must be greater than or equal to 0"),
        (
            "DB_POOL_TIMEOUT_SECONDS",
            "0",
            "DB_POOL_TIMEOUT_SECONDS must be greater than or equal to 1",
        ),
        (
            "DB_POOL_RECYCLE_SECONDS",
            "0",
            "DB_POOL_RECYCLE_SECONDS must be greater than or equal to 1",
        ),
        (
            "DB_CONNECT_TIMEOUT_SECONDS",
            "0",
            "DB_CONNECT_TIMEOUT_SECONDS must be greater than or equal to 1",
        ),
        (
            "DB_COMMAND_TIMEOUT_SECONDS",
            "0",
            "DB_COMMAND_TIMEOUT_SECONDS must be greater than or equal to 1",
        ),
        ("DB_POOL_PRE_PING", "sometimes", "DB_POOL_PRE_PING must be a boolean value"),
    ],
)
def test_database_pool_settings_invalid_values_fail_clearly(
    monkeypatch,
    name,
    value,
    message,
):
    for env_name in DB_POOL_ENV_VARS:
        monkeypatch.delenv(env_name, raising=False)
    monkeypatch.setenv(name, value)

    with pytest.raises(RuntimeError, match=message):
        config.get_database_pool_settings()


def test_create_database_engine_uses_pool_settings(monkeypatch):
    captured = {}

    def fake_create_async_engine(database_url, **kwargs):
        captured["database_url"] = database_url
        captured["kwargs"] = kwargs
        return object()

    monkeypatch.setattr(config, "create_async_engine", fake_create_async_engine)
    settings = config.DatabasePoolSettings(
        pool_size=12,
        max_overflow=4,
        pool_timeout_seconds=8,
        pool_recycle_seconds=1200,
        pool_pre_ping=True,
        connect_timeout_seconds=5,
        command_timeout_seconds=25,
    )

    engine = config.create_database_engine(
        "postgresql+asyncpg://user:pass@localhost:5432/app",
        settings,
    )

    assert engine is not None
    assert captured == {
        "database_url": "postgresql+asyncpg://user:pass@localhost:5432/app",
        "kwargs": {
            "future": True,
            "echo": False,
            "pool_size": 12,
            "max_overflow": 4,
            "pool_timeout": 8,
            "pool_recycle": 1200,
            "pool_pre_ping": True,
            "connect_args": {
                "timeout": 5,
                "command_timeout": 25,
            },
        },
    }


def test_imported_engine_pool_matches_configured_settings():
    pool = config.engine.sync_engine.pool
    settings = config.DB_POOL_SETTINGS

    assert pool.size() == settings.pool_size
    assert pool._max_overflow == settings.max_overflow
    assert pool._timeout == settings.pool_timeout_seconds
    assert pool._recycle == settings.pool_recycle_seconds
    assert pool._pre_ping is settings.pool_pre_ping


@pytest.mark.asyncio
async def test_get_db_closes_session_after_yield(monkeypatch):
    events = []

    class FakeSession:
        pass

    class FakeSessionContext:
        async def __aenter__(self):
            events.append("enter")
            self.session = FakeSession()
            return self.session

        async def __aexit__(self, exc_type, exc, tb):
            events.append("exit")

    monkeypatch.setattr(config, "AsyncSessionLocal", lambda: FakeSessionContext())

    db_generator = config.get_db()
    session = await db_generator.__anext__()

    assert isinstance(session, FakeSession)
    with pytest.raises(StopAsyncIteration):
        await db_generator.__anext__()
    assert events == ["enter", "exit"]
