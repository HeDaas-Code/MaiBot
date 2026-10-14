"""群聊事件档案只读接口。"""

from datetime import datetime
from typing import Any
import json

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, func
from sqlmodel import col, select

from src.common.database.database import get_db_session
from src.common.database.database_model import GroupEvent, GroupEventGroup, GroupEventSource
from src.webui.dependencies import require_auth

router = APIRouter(prefix="/events", tags=["group-events"], dependencies=[Depends(require_auth)])


class EventListItem(BaseModel):
    event_id: str
    title: str
    status: str
    platform: str
    scope: str | None = None
    group_count: int = 0
    source_count: int = 0
    stance_type: str
    stance_summary: str
    last_activity_at: datetime
    updated_at: datetime


class EventDetail(EventListItem):
    root_cause: str
    analysis: dict[str, Any]
    groups: list[dict[str, Any]] = Field(default_factory=list)
    sources: list[dict[str, Any]] = Field(default_factory=list)


def _to_item(event: GroupEvent, *, group_count: int, source_count: int) -> EventListItem:
    return EventListItem(
        event_id=event.event_id,
        title=event.title,
        status=event.status,
        platform=event.platform,
        scope=event.scope,
        group_count=group_count,
        source_count=source_count,
        stance_type=event.stance_type,
        stance_summary=event.stance_summary,
        last_activity_at=event.last_activity_at,
        updated_at=event.updated_at,
    )


@router.get("", response_model=list[EventListItem])
def list_events(
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[EventListItem]:
    """列出事件档案摘要。"""

    with get_db_session(auto_commit=False) as session:
        statement = (
            select(GroupEvent)
            .where(GroupEvent.canonical_event_id.is_(None))
            .order_by(desc(GroupEvent.updated_at))
            .limit(limit)
        )
        if status:
            statement = statement.where(GroupEvent.status == status)
        events = session.exec(statement).all()
        if not events:
            return []
        event_ids = [event.event_id for event in events]
        group_counts = dict(
            session.exec(
                select(GroupEventGroup.event_id, func.count())
                .where(col(GroupEventGroup.event_id).in_(event_ids))
                .group_by(GroupEventGroup.event_id)
            ).all()
        )
        source_counts = dict(
            session.exec(
                select(GroupEventSource.event_id, func.count())
                .where(col(GroupEventSource.event_id).in_(event_ids))
                .group_by(GroupEventSource.event_id)
            ).all()
        )
        return [
            _to_item(
                event,
                group_count=int(group_counts.get(event.event_id, 0)),
                source_count=int(source_counts.get(event.event_id, 0)),
            )
            for event in events
        ]


@router.get("/{event_id}", response_model=EventDetail)
def get_event(event_id: str) -> EventDetail:
    """读取事件档案详情及去媒体化文本快照。"""

    with get_db_session(auto_commit=False) as session:
        event = session.get(GroupEvent, event_id)
        if event is not None and event.canonical_event_id:
            event = session.get(GroupEvent, event.canonical_event_id)
        if event is None:
            raise HTTPException(status_code=404, detail="事件不存在")
        groups = session.exec(select(GroupEventGroup).where(GroupEventGroup.event_id == event_id)).all()
        sources = session.exec(
            select(GroupEventSource)
            .where(GroupEventSource.event_id == event_id)
            .order_by(GroupEventSource.timestamp)
            .limit(500)
        ).all()
        try:
            analysis = json.loads(event.analysis_json or "{}")
        except json.JSONDecodeError:
            analysis = {}
        item = _to_item(event, group_count=len(groups), source_count=len(sources))
        return EventDetail(
            **item.model_dump(),
            root_cause=event.root_cause,
            analysis=analysis,
            groups=[
                {
                    "session_id": group.session_id,
                    "group_id": group.group_id,
                    "group_name": group.group_name,
                    "first_activity_at": group.first_activity_at,
                    "last_activity_at": group.last_activity_at,
                }
                for group in groups
            ],
            sources=[
                {
                    "session_id": source.session_id,
                    "group_id": source.group_id,
                    "message_id": source.message_id,
                    "timestamp": source.timestamp,
                    "speaker_key": source.speaker_key,
                    "text_snapshot": source.text_snapshot,
                }
                for source in sources
            ],
        )
