"""v45 到 v46：新增机器人账号级日程状态、活动和草稿表。"""

from src.common.logger import get_logger

from .models import MigrationExecutionContext

logger = get_logger("database_migration")


_TABLE_STATEMENTS = (
    (
        "daily_routine_states",
        """
        CREATE TABLE IF NOT EXISTS daily_routine_states (
            account_key VARCHAR(512) NOT NULL PRIMARY KEY,
            platform VARCHAR(100) NOT NULL,
            account_id VARCHAR(255),
            timezone VARCHAR(64) NOT NULL DEFAULT 'Asia/Shanghai',
            day_key VARCHAR(32) NOT NULL,
            state_json TEXT NOT NULL DEFAULT '{}',
            plan_json TEXT NOT NULL DEFAULT '[]',
            last_updated_at DATETIME NOT NULL,
            last_interaction_at DATETIME,
            today_interaction_count INTEGER NOT NULL DEFAULT 0,
            today_positive_interactions INTEGER NOT NULL DEFAULT 0,
            last_sleep_quality INTEGER NOT NULL DEFAULT 70
        )
        """,
    ),
    (
        "daily_routine_activities",
        """
        CREATE TABLE IF NOT EXISTS daily_routine_activities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_key VARCHAR(512) NOT NULL,
            day_key VARCHAR(32) NOT NULL,
            activity_id VARCHAR(128) NOT NULL,
            name VARCHAR(255) NOT NULL,
            activity_type VARCHAR(32) NOT NULL,
            scheduled_start DATETIME NOT NULL,
            scheduled_end DATETIME NOT NULL,
            actual_started_at DATETIME,
            actual_ended_at DATETIME,
            status VARCHAR(32) NOT NULL DEFAULT 'planned',
            metadata_json TEXT NOT NULL DEFAULT '{}',
            CONSTRAINT uq_daily_routine_activity_day UNIQUE (account_key, day_key, activity_id)
        )
        """,
    ),
    (
        "daily_routine_drafts",
        """
        CREATE TABLE IF NOT EXISTS daily_routine_drafts (
            draft_id VARCHAR(64) NOT NULL PRIMARY KEY,
            account_key VARCHAR(512) NOT NULL,
            activity_id VARCHAR(128),
            draft_type VARCHAR(32) NOT NULL DEFAULT 'draft',
            title VARCHAR(500) NOT NULL DEFAULT '',
            body TEXT NOT NULL,
            source_refs_json TEXT NOT NULL DEFAULT '[]',
            dedupe_key VARCHAR(512) NOT NULL,
            status VARCHAR(32) NOT NULL DEFAULT 'draft',
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL,
            expires_at DATETIME,
            consumed_at DATETIME,
            CONSTRAINT uq_daily_routine_draft_dedupe UNIQUE (account_key, dedupe_key)
        )
        """,
    ),
)

_INDEX_STATEMENTS = (
    "CREATE INDEX IF NOT EXISTS ix_daily_routine_states_platform_account ON daily_routine_states (platform, account_id)",
    "CREATE INDEX IF NOT EXISTS ix_daily_routine_activities_account_day ON daily_routine_activities (account_key, day_key)",
    "CREATE INDEX IF NOT EXISTS ix_daily_routine_activities_status_end ON daily_routine_activities (status, scheduled_end)",
    "CREATE INDEX IF NOT EXISTS ix_daily_routine_drafts_account_status ON daily_routine_drafts (account_key, status)",
    "CREATE INDEX IF NOT EXISTS ix_daily_routine_drafts_expires_at ON daily_routine_drafts (expires_at)",
)


def migrate_v45_to_v46(context: MigrationExecutionContext) -> None:
    """创建日程运行时所需的持久化表，重复执行安全。"""

    context.start_progress(
        total_tables=len(_TABLE_STATEMENTS),
        total_records=0,
        description="v45 -> v46 日程系统数据表",
        table_unit_name="表",
        record_unit_name="记录",
    )
    for table_name, statement in _TABLE_STATEMENTS:
        context.connection.exec_driver_sql(statement)
        context.advance_progress(completed_tables=1, item_name=table_name)
    for statement in _INDEX_STATEMENTS:
        context.connection.exec_driver_sql(statement)
    logger.info("v45 -> v46 数据库迁移完成：已创建日程状态、活动和草稿表")
