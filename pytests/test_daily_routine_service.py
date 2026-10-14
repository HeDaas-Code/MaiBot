from datetime import datetime
from zoneinfo import ZoneInfo

from src.services.daily_routine_service import DailyRoutineService


def _at(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 10, 15, hour, minute, tzinfo=ZoneInfo("Asia/Shanghai"))


def test_daily_plan_is_deterministic_for_same_account_and_day() -> None:
    first = DailyRoutineService()
    second = DailyRoutineService()

    first_snapshot = first.get_snapshot_sync("qq", "bot-1", _at(10))
    second_snapshot = second.get_snapshot_sync("qq", "bot-1", _at(10))

    assert first_snapshot.account_key == "qq:bot-1"
    assert [item.activity_id for item in first_snapshot.activities] == [
        item.activity_id for item in second_snapshot.activities
    ]
    assert [item.scheduled_start for item in first_snapshot.activities] == [
        item.scheduled_start for item in second_snapshot.activities
    ]


def test_daily_plan_isolated_by_account() -> None:
    service = DailyRoutineService()

    first = service.get_snapshot_sync("qq", "bot-1", _at(10))
    second = service.get_snapshot_sync("qq", "bot-2", _at(10))

    assert first.account_key != second.account_key
    assert first.day_key == second.day_key


def test_routine_policy_suppresses_sleeping_group_chat_but_keeps_forced_reply() -> None:
    service = DailyRoutineService()

    planned = service.get_snapshot_sync("qq", "bot-1", _at(10))
    sleep_activity = next(item for item in planned.activities if item.activity_id == "sleep")
    sleep_time = sleep_activity.scheduled_start.replace(tzinfo=ZoneInfo("Asia/Shanghai")) + __import__(
        "datetime"
    ).timedelta(minutes=1)
    sleeping = service.get_turn_policy_sync("qq", "bot-1", is_group_chat=True, forced=False, now=sleep_time)
    forced = service.get_turn_policy_sync("qq", "bot-1", is_group_chat=True, forced=True, now=sleep_time)

    assert sleeping.status_label == "睡眠中"
    assert sleeping.multiplier <= 0.1
    assert sleeping.should_deprioritize
    assert forced.multiplier <= sleeping.multiplier
    assert not forced.should_deprioritize
    assert "强制处理" in forced.expression_hint


def test_planner_context_does_not_expose_internal_mood_numbers() -> None:
    service = DailyRoutineService()

    context = service.build_planner_context_sync("qq", "bot-1")

    assert "日程状态仅作为表达参考" in context
    assert "energy" not in context
    assert "social_desire" not in context
    assert "70" not in context
