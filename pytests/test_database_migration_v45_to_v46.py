from pathlib import Path

from sqlalchemy import create_engine

from src.common.database.migrations.builtin import build_default_migration_registry
from src.common.database.migrations.manager import DatabaseMigrationManager


def test_v45_to_v46_adds_daily_routine_tables_and_preserves_messages(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{(tmp_path / 'maibot.db').as_posix()}")
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE mai_messages (id INTEGER PRIMARY KEY, content TEXT NOT NULL)")
        connection.exec_driver_sql("INSERT INTO mai_messages VALUES (1, '既有聊天消息')")
        connection.exec_driver_sql("PRAGMA user_version=45")

    manager = DatabaseMigrationManager(engine, registry=build_default_migration_registry())
    manager.migrate()

    with engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA user_version").scalar_one() == 46
        assert connection.exec_driver_sql("SELECT content FROM mai_messages").scalar_one() == "既有聊天消息"
        for table_name in ("daily_routine_states", "daily_routine_activities", "daily_routine_drafts"):
            assert (
                connection.exec_driver_sql(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table_name,)
                ).scalar_one()
                == 1
            )

    assert manager.migrate().is_empty()
    engine.dispose()
