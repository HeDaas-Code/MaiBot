"""v44 到 v45：为群聊事件档案增加规范事件归属。"""

from src.common.logger import get_logger

from .models import MigrationExecutionContext

logger = get_logger("database_migration")


def migrate_v44_to_v45(context: MigrationExecutionContext) -> None:
    """增加重复事件的规范目标列，既有事件默认仍是规范事件。"""

    columns = {
        str(row["name"])
        for row in context.connection.exec_driver_sql("PRAGMA table_info(group_events)").mappings().all()
    }
    if "canonical_event_id" not in columns:
        context.connection.exec_driver_sql("ALTER TABLE group_events ADD COLUMN canonical_event_id VARCHAR(64)")
    context.connection.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_group_events_canonical_event_id ON group_events (canonical_event_id)"
    )
    context.start_progress(
        total_tables=1,
        total_records=0,
        description="v44 -> v45 群聊事件归一去重",
        table_unit_name="表",
        record_unit_name="记录",
    )
    context.advance_progress(completed_tables=1, item_name="group_events")
    logger.info("v44 -> v45 数据库迁移完成：已添加群聊事件规范归属")
