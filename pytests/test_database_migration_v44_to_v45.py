from pathlib import Path

from sqlalchemy import create_engine

from src.common.database.migrations.builtin import build_default_migration_registry
from src.common.database.migrations.manager import DatabaseMigrationManager


def test_v44_to_v45_adds_canonical_event_link_without_changing_archives(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{(tmp_path / 'maibot.db').as_posix()}")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE group_events (event_id VARCHAR(64) PRIMARY KEY, status VARCHAR(32) NOT NULL)"
        )
        connection.exec_driver_sql("INSERT INTO group_events VALUES ('event:existing', 'collecting')")
        connection.exec_driver_sql("CREATE TABLE mai_messages (id INTEGER PRIMARY KEY, content TEXT NOT NULL)")
        connection.exec_driver_sql("INSERT INTO mai_messages VALUES (1, '既有聊天消息')")
        connection.exec_driver_sql("PRAGMA user_version=44")

    manager = DatabaseMigrationManager(engine, registry=build_default_migration_registry())
    manager.migrate()

    with engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA user_version").scalar_one() == 46
        assert connection.exec_driver_sql("SELECT event_id, status, canonical_event_id FROM group_events").one() == (
            "event:existing",
            "collecting",
            None,
        )
        assert connection.exec_driver_sql("SELECT content FROM mai_messages").scalar_one() == "既有聊天消息"
        assert (
            connection.exec_driver_sql(
                "SELECT 1 FROM sqlite_master WHERE type='index' AND name='ix_group_events_canonical_event_id'"
            ).scalar_one()
            == 1
        )
        assert (
            connection.exec_driver_sql(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='daily_routine_states'"
            ).scalar_one()
            == 1
        )

    assert manager.migrate().is_empty()
    engine.dispose()
