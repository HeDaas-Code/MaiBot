from datetime import datetime, timedelta
import asyncio

from src.services.group_event_service import (
    EVENT_MIN_MESSAGES,
    EVENT_MIN_SPEAKERS,
    EventCluster,
    EventMessageSnapshot,
    GroupEventService,
)


def _message(index: int, speaker: int = 0, group_id: str = "group-0") -> EventMessageSnapshot:
    return EventMessageSnapshot(
        message_id=f"m-{index}",
        session_id="session-0",
        platform="test",
        account_id="bot",
        scope="default",
        group_id=group_id,
        group_name="测试群",
        user_id=f"user-{speaker}",
        timestamp=datetime.now() - timedelta(seconds=index),
        text=f"同一事件 关键事实 讨论 {index}",
    )


def test_event_cluster_floor_requires_eight_messages_and_three_speakers() -> None:
    service = GroupEventService()
    assert not service._passes_related_cluster_floor([_message(index) for index in range(EVENT_MIN_MESSAGES - 1)])
    assert not service._passes_related_cluster_floor(
        [_message(index, speaker=0) for index in range(EVENT_MIN_MESSAGES)]
    )
    assert service._passes_related_cluster_floor(
        [_message(index, speaker=index % EVENT_MIN_SPEAKERS) for index in range(EVENT_MIN_MESSAGES)]
    )


def test_speaker_alias_is_irreversibly_hashed_and_group_scoped() -> None:
    first_group = _message(0, speaker=1, group_id="group-a")
    second_group = _message(1, speaker=1, group_id="group-b")
    assert first_group.speaker_key != second_group.speaker_key
    assert "user-1" not in first_group.speaker_key


def test_ready_event_blocks_non_planner_outbound(monkeypatch) -> None:
    from src.services.group_event_service import EventContext

    service = GroupEventService()
    monkeypatch.setattr(
        service,
        "get_contexts_for_source",
        lambda *args: _resolved([EventContext("event:1", "ready_for_stance", "title", "", "", "event")]),
    )
    assert not asyncio.run(service.can_send_outbound("session-0", "event reply", "message-1"))


def test_collecting_event_replaces_obvious_partisan_reply(monkeypatch) -> None:
    from src.services.group_event_service import EventContext

    service = GroupEventService()
    monkeypatch.setattr(
        service,
        "get_contexts_for_source",
        lambda *args: _resolved([EventContext("event:1", "collecting", "title", "", "", "event")]),
    )
    guarded = asyncio.run(service.guard_neutral_reply("session-0", "我支持这一方，他们明显是对的。", "message-1"))
    assert guarded == "我先不急着下结论，想把时间线和各方说法再核对一下。"


async def _resolved(value):
    return value


def test_event_analysis_payload_readiness_requires_evidence_indices() -> None:
    from src.services.group_event_service import EventAnalysisPayload

    payload = EventAnalysisPayload.model_validate(
        {
            "title": "事件",
            "root_cause": "起因",
            "root_cause_source_indices": [1],
            "timeline": [{"summary": "节点", "source_indices": [1]}],
            "viewpoints": [{"label": "观点", "source_indices": [2]}],
            "coverage_complete": True,
        }
    )
    assert payload.coverage_complete
    assert payload.root_cause_source_indices == [1]


def _event(event_id: str, *, status: str = "collecting", account_id: str = "bot", scope: str = "default"):
    from src.common.database.database_model import GroupEvent

    now = datetime.now()
    return GroupEvent(
        event_id=event_id,
        platform="test",
        account_id=account_id,
        scope=scope,
        status=status,
        title="测试事件",
        root_cause="测试起因",
        created_at=now,
        updated_at=now,
        last_activity_at=now,
        last_material_activity_at=now,
    )


def _install_event_database(monkeypatch, tmp_path):
    from contextlib import contextmanager

    from sqlmodel import Session
    from sqlalchemy import create_engine

    from src.common.database.database_model import GroupEvent, GroupEventGroup, GroupEventSource
    import src.services.group_event_service as event_module

    engine = create_engine(f"sqlite:///{(tmp_path / 'events.db').as_posix()}")
    for model in (GroupEvent.__table__, GroupEventGroup.__table__, GroupEventSource.__table__):
        model.create(engine)

    @contextmanager
    def get_test_session(auto_commit: bool = True):
        with Session(engine) as session:
            try:
                yield session
                if auto_commit:
                    session.commit()
            except Exception:
                session.rollback()
                raise

    monkeypatch.setattr(event_module, "get_db_session", get_test_session)
    return engine


def test_canonical_candidates_include_same_group_but_never_cross_scope(monkeypatch, tmp_path) -> None:
    from sqlmodel import Session

    engine = _install_event_database(monkeypatch, tmp_path)
    with Session(engine) as session:
        session.add_all(
            [
                _event("same-group"),
                _event("other-account", account_id="another-bot"),
                _event("other-scope", scope="another-scope"),
                _event("archived", status="archived"),
            ]
        )
        session.commit()

    matches = GroupEventService()._find_canonical_candidates(_message(90))
    assert {event.event_id for event in matches} == {"same-group"}
    engine.dispose()


def test_duplicate_event_merge_moves_unique_sources_and_group_links(monkeypatch, tmp_path) -> None:
    from sqlmodel import Session, select

    from src.common.database.database_model import GroupEvent, GroupEventGroup, GroupEventSource

    engine = _install_event_database(monkeypatch, tmp_path)
    first_seen = datetime.now() - timedelta(minutes=4)
    last_seen = datetime.now() - timedelta(minutes=1)
    with Session(engine) as session:
        canonical = _event("canonical")
        canonical.last_activity_at = first_seen
        canonical.last_material_activity_at = first_seen
        duplicate = _event("duplicate")
        duplicate.last_activity_at = last_seen
        duplicate.last_material_activity_at = last_seen
        session.add_all(
            [
                canonical,
                duplicate,
                GroupEventGroup(
                    event_id="canonical",
                    session_id="session-0",
                    group_id="group-0",
                    group_name="旧群名",
                    first_activity_at=first_seen,
                    last_activity_at=first_seen,
                ),
                GroupEventGroup(
                    event_id="duplicate",
                    session_id="session-0",
                    group_id="group-0",
                    group_name="测试群",
                    first_activity_at=last_seen,
                    last_activity_at=last_seen,
                ),
                GroupEventGroup(
                    event_id="duplicate",
                    session_id="session-1",
                    group_id="group-1",
                    group_name="另一个群",
                    first_activity_at=first_seen,
                    last_activity_at=last_seen,
                ),
                GroupEventSource(
                    event_id="canonical",
                    session_id="session-0",
                    platform="test",
                    account_id="bot",
                    scope="default",
                    group_id="group-0",
                    message_id="shared-message",
                    timestamp=first_seen,
                    speaker_key="speaker-1",
                    text_snapshot="共有来源",
                ),
                GroupEventSource(
                    event_id="duplicate",
                    session_id="session-0",
                    platform="test",
                    account_id="bot",
                    scope="default",
                    group_id="group-0",
                    message_id="shared-message",
                    timestamp=last_seen,
                    speaker_key="speaker-1",
                    text_snapshot="重复来源",
                ),
                GroupEventSource(
                    event_id="duplicate",
                    session_id="session-1",
                    platform="test",
                    account_id="bot",
                    scope="default",
                    group_id="group-1",
                    message_id="new-message",
                    timestamp=last_seen,
                    speaker_key="speaker-2",
                    text_snapshot="新增证据",
                ),
            ]
        )
        session.commit()

    GroupEventService._merge_duplicate_events("canonical", ["duplicate"])

    with Session(engine) as session:
        canonical = session.get(GroupEvent, "canonical")
        duplicate = session.get(GroupEvent, "duplicate")
        groups = session.exec(select(GroupEventGroup).where(GroupEventGroup.event_id == "canonical")).all()
        sources = session.exec(select(GroupEventSource).where(GroupEventSource.event_id == "canonical")).all()
        assert duplicate.canonical_event_id == "canonical"
        assert duplicate.status == "merged"
        assert canonical.last_activity_at == last_seen
        assert {(group.session_id, group.group_name) for group in groups} == {
            ("session-0", "测试群"),
            ("session-1", "另一个群"),
        }
        assert len(groups) == 2
        assert {(source.session_id, source.message_id) for source in sources} == {
            ("session-0", "shared-message"),
            ("session-1", "new-message"),
        }
    engine.dispose()


def test_exact_event_signature_skips_llm_and_matches_same_group() -> None:
    from types import SimpleNamespace

    existing = SimpleNamespace(title="同一具体事件", root_cause="同一明确起因", event_id="event:old")
    cluster = EventCluster(title="同一具体事件", root_cause="同一明确起因")
    matches = GroupEventService._find_exact_signature_matches([existing], cluster)
    assert [(match.event_index, match.confidence) for match in matches] == [(0, 1.0)]


def test_merging_conflicting_confirmed_stances_reopens_neutral_review(monkeypatch, tmp_path) -> None:
    import json

    from sqlmodel import Session

    from src.common.database.database_model import GroupEvent

    engine = _install_event_database(monkeypatch, tmp_path)
    with Session(engine) as session:
        canonical = _event("canonical", status="stance_active")
        canonical.stance_type = "support"
        canonical.stance_summary = "维持立场甲"
        canonical.stance_reasoning = "甲依据"
        canonical.analysis_json = '{"coverage_complete": true}'
        duplicate = _event("duplicate", status="stance_active")
        duplicate.stance_type = "oppose"
        duplicate.stance_summary = "维持立场乙"
        duplicate.stance_reasoning = "乙依据"
        session.add_all([canonical, duplicate])
        session.commit()

    GroupEventService._merge_duplicate_events("canonical", ["duplicate"])

    with Session(engine) as session:
        canonical = session.get(GroupEvent, "canonical")
        analysis = json.loads(canonical.analysis_json)
        assert canonical.status == "reviewing"
        assert canonical.stance_type == ""
        assert canonical.stance_summary == ""
        assert len(analysis["deduplicated_stance_conflicts"]) == 2
        assert not analysis["coverage_complete"]
    engine.dispose()


def test_failed_canonical_match_does_not_create_parallel_event(monkeypatch) -> None:
    from types import SimpleNamespace

    service = GroupEventService()
    candidate = SimpleNamespace(
        event_id="event:existing", title="不同措辞", root_cause="已有规范起因", status="collecting"
    )
    monkeypatch.setattr(service, "_find_canonical_candidates", lambda snapshot: [candidate])

    async def fail_match(*args, **kwargs):
        raise RuntimeError("temporary model connectivity failure")

    monkeypatch.setattr(service, "_request_json", fail_match)
    created = []
    monkeypatch.setattr(service, "_create_event", lambda *args: created.append(args) or "event:new")

    result = asyncio.run(
        service._find_or_create_canonical_event(
            _message(100),
            EventCluster(title="新候选标题", root_cause="新候选起因"),
            [_message(index) for index in range(EVENT_MIN_MESSAGES)],
        )
    )

    assert result is None
    assert created == []


def test_matching_multiple_duplicate_archives_merges_to_one_canonical(monkeypatch) -> None:
    from types import SimpleNamespace

    service = GroupEventService()
    existing = [
        SimpleNamespace(event_id="event:canonical", title="标题甲", root_cause="起因甲", status="collecting"),
        SimpleNamespace(event_id="event:duplicate", title="标题乙", root_cause="起因乙", status="collecting"),
    ]
    monkeypatch.setattr(service, "_find_canonical_candidates", lambda snapshot: existing)

    async def match_candidates(*args, **kwargs):
        return {"matches": [{"event_index": 0, "confidence": 0.96}, {"event_index": 1, "confidence": 0.91}]}

    monkeypatch.setattr(service, "_request_json", match_candidates)
    monkeypatch.setattr(service, "_select_canonical_event", lambda events: events[0])
    merged = []
    refreshed = []
    monkeypatch.setattr(
        service, "_merge_duplicate_events", lambda canonical_id, ids: merged.append((canonical_id, ids))
    )
    monkeypatch.setattr(service, "_refresh_canonical_event", lambda event_id, cluster: refreshed.append(event_id))

    result = asyncio.run(
        service._find_or_create_canonical_event(
            _message(100),
            EventCluster(title="统一后的标题", root_cause="统一后的起因"),
            [_message(index) for index in range(EVENT_MIN_MESSAGES)],
        )
    )

    assert result == "event:canonical"
    assert merged == [("event:canonical", ["event:duplicate"])]
    assert refreshed == ["event:canonical"]


def test_startup_reconciliation_merges_only_matching_scope(monkeypatch) -> None:
    from types import SimpleNamespace

    service = GroupEventService()
    first = SimpleNamespace(
        event_id="event:first",
        platform="test",
        account_id="bot",
        scope="route-a",
        title="规范事件",
        root_cause="规范起因",
        analysis_json="{}",
    )
    duplicate = SimpleNamespace(
        event_id="event:duplicate",
        platform="test",
        account_id="bot",
        scope="route-a",
        title="规范事件",
        root_cause="规范起因",
        analysis_json="{}",
    )
    unrelated_scope = SimpleNamespace(
        event_id="event:other-scope",
        platform="test",
        account_id="bot",
        scope="route-b",
        title="规范事件",
        root_cause="规范起因",
        analysis_json="{}",
    )
    monkeypatch.setattr(service, "_load_active_canonical_events", lambda: [first, duplicate, unrelated_scope])
    monkeypatch.setattr(service, "_load_sources", lambda event_id: [])
    monkeypatch.setattr(
        service, "_match_existing_events", lambda cluster, sources, candidates: _resolved(candidates[:1])
    )
    monkeypatch.setattr(service, "_select_canonical_event", lambda events: events[0])
    merges = []
    monkeypatch.setattr(
        service, "_merge_duplicate_events", lambda canonical_id, ids: merges.append((canonical_id, ids))
    )
    monkeypatch.setattr(service, "_schedule_analysis", lambda event_id: _resolved(None))

    asyncio.run(service._reconcile_existing_duplicates())

    assert merges == [("event:first", ["event:duplicate"])]


def test_startup_reconciliation_prefilter_skips_unrelated_events() -> None:
    from types import SimpleNamespace

    from src.services.group_event_service import GroupEventService

    seed = SimpleNamespace(
        title="军事新闻三要素与三位人物",
        root_cause="围绕疑似、或将、不排除的军事新闻说法及相关人物展开调侃。",
        analysis_json="{}",
    )
    duplicates = [
        SimpleNamespace(
            event_id="similar-1",
            title="军事新闻‘三要素’与相关人物梗",
            root_cause="群成员围绕军事新闻常用表述三要素及相关人物展开同一话题讨论。",
            analysis_json="{}",
        ),
        SimpleNamespace(
            event_id="similar-2",
            title="调侃军事新闻的要素",
            root_cause="围绕军事新闻常见表述展开玩笑，并提到疑似、或将、不排除等说法。",
            analysis_json="{}",
        ),
    ]
    unrelated = SimpleNamespace(
        event_id="unrelated",
        title="绝地潜兵载具与机甲玩法",
        root_cause="玩家讨论坦克跳跃和机甲技能。",
        analysis_json="{}",
    )

    candidates = GroupEventService._rank_reconciliation_candidates(seed, [*duplicates, unrelated])

    assert {event.event_id for event in candidates} == {"similar-1", "similar-2"}


def test_event_analysis_accepts_nested_root_and_cited_fact_shapes(monkeypatch, tmp_path) -> None:
    import json

    from sqlmodel import Session

    from src.common.database.database_model import GroupEvent
    from src.services.group_event_service import EventAnalysisPayload

    payload = EventAnalysisPayload.model_validate(
        {
            "title": "规范后的事件标题",
            "root_cause": {"description": "有证据支持的事件起因", "source_indices": [1]},
            "timeline": [{"time": "17:00", "event": "发生关键节点", "source_indices": [2]}],
            "viewpoints": [{"viewpoint": "一方说法", "source_indices": [1, 2]}],
            "key_facts": [{"fact": "可验证的事实", "source_indices": [2]}],
            "uncertainties": [],
            "coverage_complete": True,
            "related": [],
            "material_evidence": False,
            "major_counter_evidence": False,
        }
    )
    assert payload.root_cause == "有证据支持的事件起因"
    assert payload.root_cause_source_indices == [1]
    assert payload.key_facts == ["可验证的事实"]
    assert payload.key_fact_source_indices == [[2]]
    assert payload.viewpoints[0]["label"] == "一方说法"
    assert payload.related

    engine = _install_event_database(monkeypatch, tmp_path)
    with Session(engine) as session:
        session.add(_event("event:analysis"))
        session.commit()
    GroupEventService()._save_analysis("event:analysis", payload, {1: 101, 2: 102})
    with Session(engine) as session:
        stored = session.get(GroupEvent, "event:analysis")
        analysis = json.loads(stored.analysis_json)
        assert stored.root_cause == "有证据支持的事件起因"
        assert analysis["coverage_complete"]
        assert analysis["timeline"][0]["summary"] == "发生关键节点"
        assert analysis["timeline"][0]["source_ids"] == [102]
        assert analysis["key_facts"] == ["可验证的事实"]
        assert analysis["key_fact_source_ids"] == [[102]]
    engine.dispose()
