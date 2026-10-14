"""日程运行时只读接口。"""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from src.services.daily_routine_service import RoutineSnapshot, get_daily_routine_service
from src.webui.dependencies import require_auth

router = APIRouter(prefix="/daily-routine", tags=["daily-routine"], dependencies=[Depends(require_auth)])


class RoutineActivityResponse(BaseModel):
    activity_id: str
    name: str
    activity_type: str
    scheduled_start: datetime
    scheduled_end: datetime
    status: str


class RoutineSnapshotResponse(BaseModel):
    account_key: str
    platform: str
    account_id: str
    timezone: str
    day_key: str
    current_activity: RoutineActivityResponse | None
    activities: list[RoutineActivityResponse] = Field(default_factory=list)
    status_label: str
    interaction_count: int
    last_sleep_quality: int
    updated_at: datetime


class RoutineDraftResponse(BaseModel):
    draft_id: str
    activity_id: str | None
    draft_type: str
    title: str
    body: str
    source_refs: list[Any] = Field(default_factory=list)
    status: str
    created_at: datetime
    expires_at: datetime | None


class RoutineOverviewResponse(BaseModel):
    enabled: bool
    snapshots: list[RoutineSnapshotResponse] = Field(default_factory=list)
    drafts: list[RoutineDraftResponse] = Field(default_factory=list)


def _status_label(snapshot: RoutineSnapshot) -> str:
    if snapshot.current_activity is None:
        return "空闲"
    labels = {
        "sleep": "睡眠中",
        "interest": "兴趣活动中",
        "fixed": "日常活动中",
    }
    return labels.get(snapshot.current_activity.activity_type, "活动中")


def _activity_response(activity: Any) -> RoutineActivityResponse:
    return RoutineActivityResponse(
        activity_id=activity.activity_id,
        name=activity.name,
        activity_type=activity.activity_type,
        scheduled_start=activity.scheduled_start,
        scheduled_end=activity.scheduled_end,
        status=activity.status,
    )


def _snapshot_response(snapshot: RoutineSnapshot) -> RoutineSnapshotResponse:
    activities = [_activity_response(activity) for activity in snapshot.activities]
    current = _activity_response(snapshot.current_activity) if snapshot.current_activity else None
    return RoutineSnapshotResponse(
        account_key=snapshot.account_key,
        platform=snapshot.platform,
        account_id=snapshot.account_id,
        timezone=snapshot.timezone,
        day_key=snapshot.day_key,
        current_activity=current,
        activities=activities,
        status_label=_status_label(snapshot),
        interaction_count=snapshot.interaction_count,
        last_sleep_quality=snapshot.last_sleep_quality,
        updated_at=snapshot.updated_at,
    )


def _draft_response(draft: Any) -> RoutineDraftResponse:
    import json

    try:
        source_refs = json.loads(draft.source_refs_json or "[]")
    except json.JSONDecodeError:
        source_refs = []
    return RoutineDraftResponse(
        draft_id=draft.draft_id,
        activity_id=draft.activity_id,
        draft_type=draft.draft_type,
        title=draft.title,
        body=draft.body,
        source_refs=source_refs if isinstance(source_refs, list) else [],
        status=draft.status,
        created_at=draft.created_at,
        expires_at=draft.expires_at,
    )


@router.get("/overview", response_model=RoutineOverviewResponse)
def get_overview(limit: int = Query(default=20, ge=1, le=100)) -> RoutineOverviewResponse:
    """读取已启动账号的日程状态和未过期草稿。"""

    service = get_daily_routine_service()
    snapshots = service.all_snapshots()
    drafts = []
    for snapshot in snapshots:
        drafts.extend(service.list_drafts_sync(snapshot.platform, snapshot.account_id, limit))
    drafts.sort(key=lambda item: item.created_at, reverse=True)
    return RoutineOverviewResponse(
        enabled=service.is_running,
        snapshots=[_snapshot_response(snapshot) for snapshot in snapshots],
        drafts=[_draft_response(draft) for draft in drafts[:limit]],
    )
