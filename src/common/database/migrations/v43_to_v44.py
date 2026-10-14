"""v43 到 v44：新增群聊事件跟踪档案表。"""

from src.common.logger import get_logger

from .models import MigrationExecutionContext

logger = get_logger("database_migration")


def migrate_v43_to_v44(context: MigrationExecutionContext) -> None:
    """创建事件主档、群聊关联和消息快照表。"""

    statements = (
        """CREATE TABLE IF NOT EXISTS group_events (
            event_id VARCHAR(64) PRIMARY KEY,
            recurrence_of_event_id VARCHAR(64),
            platform VARCHAR(100) NOT NULL,
            account_id VARCHAR(255),
            scope VARCHAR(255),
            status VARCHAR(32) NOT NULL DEFAULT 'collecting',
            title VARCHAR(500) NOT NULL DEFAULT '',
            root_cause TEXT NOT NULL DEFAULT '',
            analysis_json TEXT NOT NULL DEFAULT '{}',
            stance_type VARCHAR(32) NOT NULL DEFAULT '',
            stance_summary TEXT NOT NULL DEFAULT '',
            stance_reasoning TEXT NOT NULL DEFAULT '',
            stance_confidence FLOAT NOT NULL DEFAULT 0,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL,
            last_activity_at DATETIME NOT NULL,
            last_material_activity_at DATETIME NOT NULL,
            ready_at DATETIME,
            closed_at DATETIME
        )""",
        "CREATE INDEX IF NOT EXISTS ix_group_events_scope_status ON group_events (platform, account_id, scope, status)",
        "CREATE INDEX IF NOT EXISTS ix_group_events_recurrence_of_event_id ON group_events (recurrence_of_event_id)",
        "CREATE INDEX IF NOT EXISTS ix_group_events_updated_at ON group_events (updated_at)",
        "CREATE INDEX IF NOT EXISTS ix_group_events_last_activity_at ON group_events (last_activity_at)",
        "CREATE INDEX IF NOT EXISTS ix_group_events_last_material_activity_at ON group_events (last_material_activity_at)",
        """CREATE TABLE IF NOT EXISTS group_event_groups (
            id INTEGER PRIMARY KEY,
            event_id VARCHAR(64) NOT NULL,
            session_id VARCHAR(255) NOT NULL,
            group_id VARCHAR(255) NOT NULL,
            group_name VARCHAR(255) NOT NULL DEFAULT '',
            first_activity_at DATETIME NOT NULL,
            last_activity_at DATETIME NOT NULL,
            CONSTRAINT uq_group_event_groups_event_session UNIQUE (event_id, session_id)
        )""",
        "CREATE INDEX IF NOT EXISTS ix_group_event_groups_event_id ON group_event_groups (event_id)",
        "CREATE INDEX IF NOT EXISTS ix_group_event_groups_session_id ON group_event_groups (session_id)",
        "CREATE INDEX IF NOT EXISTS ix_group_event_groups_group_id ON group_event_groups (group_id)",
        "CREATE INDEX IF NOT EXISTS ix_group_event_groups_last_activity_at ON group_event_groups (last_activity_at)",
        """CREATE TABLE IF NOT EXISTS group_event_sources (
            id INTEGER PRIMARY KEY,
            event_id VARCHAR(64) NOT NULL,
            session_id VARCHAR(255) NOT NULL,
            platform VARCHAR(100) NOT NULL,
            account_id VARCHAR(255),
            scope VARCHAR(255),
            group_id VARCHAR(255) NOT NULL,
            message_id VARCHAR(255) NOT NULL,
            timestamp DATETIME NOT NULL,
            speaker_key VARCHAR(64) NOT NULL,
            text_snapshot TEXT NOT NULL,
            CONSTRAINT uq_group_event_sources_message UNIQUE (event_id, session_id, message_id)
        )""",
        "CREATE INDEX IF NOT EXISTS ix_group_event_sources_event_id ON group_event_sources (event_id)",
        "CREATE INDEX IF NOT EXISTS ix_group_event_sources_session_id ON group_event_sources (session_id)",
        "CREATE INDEX IF NOT EXISTS ix_group_event_sources_group_id ON group_event_sources (group_id)",
        "CREATE INDEX IF NOT EXISTS ix_group_event_sources_message_id ON group_event_sources (message_id)",
        "CREATE INDEX IF NOT EXISTS ix_group_event_sources_timestamp ON group_event_sources (timestamp)",
        "CREATE INDEX IF NOT EXISTS ix_group_event_sources_event_time ON group_event_sources (event_id, timestamp)",
    )
    context.start_progress(
        total_tables=3,
        total_records=0,
        description="v43 -> v44 新增群聊事件档案",
        table_unit_name="表",
        record_unit_name="记录",
    )
    for statement in statements:
        context.connection.exec_driver_sql(statement)
    for table_name in ("group_events", "group_event_groups", "group_event_sources"):
        context.advance_progress(completed_tables=1, item_name=table_name)
    logger.info("v43 -> v44 数据库迁移完成：已创建群聊事件档案表")
