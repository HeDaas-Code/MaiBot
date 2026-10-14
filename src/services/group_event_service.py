"""群聊事件跟踪、分析与临时立场服务。

消息接入只向有界队列提交轻量快照。后台任务负责活跃度门槛、LLM 语义聚类、
跨群事件匹配和证据分析；事件状态与 Maisaka 短期聊天历史分开持久化。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
import math
from typing import Any, Optional

from pydantic import BaseModel, Field, model_validator
from sqlalchemy import Integer, cast, desc, func
from sqlmodel import select

from src.chat.message_receive.message import SessionMessage
from src.chat.utils.utils import is_bot_self
from src.common.database.database import get_db_session
from src.common.database.database_model import GroupEvent, GroupEventGroup, GroupEventSource, Messages
from src.common.logger import get_logger
from src.services.llm_service import LLMGenerationOptions, LLMServiceClient
from src.llm_models.payload_content.resp_format import RespFormat, RespFormatType

logger = get_logger("group_event_service")

EVENT_WINDOW_SECONDS = 10 * 60
EVENT_BASELINE_DAYS = 30
EVENT_MIN_MESSAGES = 8
EVENT_MIN_SPEAKERS = 3
EVENT_ACTIVE_BASELINE_MULTIPLIER = 3.0
EVENT_CANONICAL_MATCH_THRESHOLD = 0.85
EVENT_ARCHIVED_RECURRENCE_MATCH_THRESHOLD = 0.85
EVENT_ANALYSIS_STABILITY_SECONDS = 30 * 60
EVENT_ARCHIVE_AFTER_SECONDS = 24 * 60 * 60
EVENT_RECONCILE_SIMILARITY_THRESHOLD = 0.08
EVENT_RECONCILE_MAX_CANDIDATES = 12
EVENT_MAX_WINDOW_MESSAGES = 100
EVENT_MAX_CONTEXT_SOURCES = 80
EVENT_MAX_SNAPSHOT_CHARS = 1200
EVENT_TICK_SECONDS = 30

_STANCE_WORDS = re.compile(
    r"(?:我支持|我反对|我赞成|我不赞成|明显是|肯定是|绝对是|活该|可耻|垃圾|正确的|错误的|应该惩罚|必须封|支持这一方|站在.{0,8}一边)",
    re.IGNORECASE,
)
_TOKEN_RE = re.compile(r"[\w\u4e00-\u9fff]{2,}", re.UNICODE)
_NEUTRAL_FALLBACK = "我先不急着下结论，想把时间线和各方说法再核对一下。"


class EventCluster(BaseModel):
    title: str = ""
    root_cause: str = ""
    source_indices: list[int] = Field(default_factory=list)
    confidence: float = 0.0


class EventClusterPayload(BaseModel):
    clusters: list[EventCluster] = Field(default_factory=list)


class EventAnalysisPayload(BaseModel):
    """模型输出的结构化事件分析结果。"""

    title: str = ""
    root_cause: str = ""
    root_cause_source_indices: list[int] = Field(default_factory=list)
    key_fact_source_indices: list[list[int]] = Field(default_factory=list)
    timeline: list[dict[str, Any]] = Field(default_factory=list)
    viewpoints: list[dict[str, Any]] = Field(default_factory=list)
    key_facts: list[str] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)
    coverage_complete: bool = False
    related: bool = True
    material_evidence: bool = False
    major_counter_evidence: bool = False

    @model_validator(mode="before")
    @classmethod
    def normalize_model_output(cls, value: Any) -> Any:
        """兼容模型常见的富对象格式，确保结构差异不会丢掉整条时间线。"""
        if not isinstance(value, dict):
            return value
        normalized = dict(value)
        root_cause = normalized.get("root_cause")
        if isinstance(root_cause, dict):
            normalized["root_cause_source_indices"] = (
                normalized.get("root_cause_source_indices")
                or root_cause.get("source_indices")
                or root_cause.get("source_ids")
                or []
            )
            normalized["root_cause"] = str(
                root_cause.get("description")
                or root_cause.get("statement")
                or root_cause.get("summary")
                or root_cause.get("text")
                or ""
            )

        raw_key_facts = normalized.get("key_facts") or []
        key_facts: list[str] = []
        key_fact_source_indices: list[list[int]] = []
        for fact in raw_key_facts if isinstance(raw_key_facts, list) else []:
            if isinstance(fact, dict):
                key_facts.append(str(fact.get("fact") or fact.get("text") or fact.get("summary") or ""))
                indices = fact.get("source_indices") or fact.get("source_ids") or []
                key_fact_source_indices.append(indices if isinstance(indices, list) else [])
            else:
                key_facts.append(str(fact))
                key_fact_source_indices.append([])
        normalized["key_facts"] = key_facts
        normalized["key_fact_source_indices"] = key_fact_source_indices

        raw_viewpoints = normalized.get("viewpoints") or []
        if isinstance(raw_viewpoints, list):
            normalized["viewpoints"] = [
                {
                    **item,
                    "label": item.get("label") or item.get("name") or item.get("viewpoint") or "观点",
                }
                if isinstance(item, dict)
                else item
                for item in raw_viewpoints
            ]

        # 事件分析本身针对已收录事件的证据；空数组是模型常见的“未提供”，不是“不相关”。
        if not isinstance(normalized.get("related"), bool):
            normalized["related"] = str(normalized.get("related", "")).strip().lower() not in {
                "false", "no", "0", "unrelated"
            }
        return normalized


class EventCanonicalMatch(BaseModel):
    """单个候选事件与已有规范事件的模型匹配判断。"""

    event_index: int
    confidence: float = Field(ge=0.0, le=1.0)


class EventCanonicalMatchPayload(BaseModel):
    """允许一次识别出多个历史重复档案，并全部并入同一规范事件。"""

    matches: list[EventCanonicalMatch] = Field(default_factory=list)


@dataclass(frozen=True)
class EventMessageSnapshot:
    message_id: str
    session_id: str
    platform: str
    account_id: str
    scope: str
    group_id: str
    group_name: str
    user_id: str
    timestamp: datetime
    text: str

    @property
    def speaker_key(self) -> str:
        payload = f"{self.platform}|{self.account_id}|{self.scope}|{self.group_id}|{self.user_id}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


@dataclass(frozen=True)
class EventContext:
    event_id: str
    status: str
    title: str
    stance_type: str
    stance_summary: str
    text: str


class GroupEventService:
    """异步接收入站消息并维护事件档案。"""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[EventMessageSnapshot] = asyncio.Queue(maxsize=2000)
        self._worker_task: Optional[asyncio.Task[None]] = None
        self._reconcile_task: Optional[asyncio.Task[None]] = None
        self._analysis_tasks: set[asyncio.Task[None]] = set()
        self._analysis_dirty_event_ids: set[str] = set()
        self._canonicalization_lock = asyncio.Lock()
        self._stopping = False
        self._last_cluster_attempt_by_session: dict[str, float] = {}
        self._analysis_client = LLMServiceClient(task_name="event_analysis", request_type="group_event_analysis")

    def start(self) -> None:
        """启动后台消费者；重复调用是安全的。"""
        self._stopping = False
        if self._worker_task is None or self._worker_task.done():
            self._worker_task = asyncio.create_task(self._worker_loop(), name="group_event_tracker")
        if self._reconcile_task is None or self._reconcile_task.done():
            self._reconcile_task = asyncio.create_task(
                self._reconcile_existing_duplicates(), name="group_event_reconcile"
            )
        logger.info("群聊事件跟踪服务已启动: queue_capacity=%s history_reconciliation=background", self._queue.maxsize)

    async def stop(self) -> None:
        """停止事件后台任务。"""
        self._stopping = True
        if self._worker_task is not None:
            self._worker_task.cancel()
            await asyncio.gather(self._worker_task, return_exceptions=True)
            self._worker_task = None
        if self._reconcile_task is not None:
            if not self._reconcile_task.done():
                logger.warning("群聊事件历史归一正在关机时中断；已提交的合并保留，下次启动会从未合并档案继续")
            self._reconcile_task.cancel()
            await asyncio.gather(self._reconcile_task, return_exceptions=True)
            self._reconcile_task = None
        for task in list(self._analysis_tasks):
            task.cancel()
        if self._analysis_tasks:
            await asyncio.gather(*self._analysis_tasks, return_exceptions=True)
        self._analysis_tasks.clear()

    async def observe_message(self, message: SessionMessage) -> None:
        """非阻塞地提交一条已通过主消息过滤链的群聊消息。"""
        group_info = message.message_info.group_info
        user_info = message.message_info.user_info
        if (
            group_info is None
            or message.is_notify
            or message.is_command
            or is_bot_self(message.platform, user_info.user_id)
        ):
            return
        text = " ".join(str(message.processed_plain_text or "").split()).strip()
        if not text or not message.message_id or not message.session_id:
            return
        self.start()
        snapshot = EventMessageSnapshot(
            message_id=str(message.message_id),
            session_id=str(message.session_id),
            platform=str(message.platform or ""),
            account_id=str(message.account_id or ""),
            scope=str(message.scope or ""),
            group_id=str(group_info.group_id or ""),
            group_name=str(group_info.group_name or ""),
            user_id=str(user_info.user_id or ""),
            timestamp=message.timestamp,
            text=text,
        )
        try:
            self._queue.put_nowait(snapshot)
        except asyncio.QueueFull:
            logger.warning("群聊事件跟踪队列已满，当前消息已留在聊天数据库，等待后续窗口重新扫描")

    async def _worker_loop(self) -> None:
        while True:
            try:
                snapshot = await asyncio.wait_for(self._queue.get(), timeout=EVENT_TICK_SECONDS)
            except asyncio.TimeoutError:
                await asyncio.to_thread(self._advance_lifecycle)
                continue
            try:
                await self._process_snapshot(snapshot)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("处理群聊事件消息失败")
            finally:
                self._queue.task_done()

    async def _process_snapshot(self, snapshot: EventMessageSnapshot) -> None:
        window = await asyncio.to_thread(self._find_window_messages, snapshot)
        linked_events = await asyncio.to_thread(self._find_events_for_session, snapshot.session_id)
        related_active: list[GroupEvent] = []
        for event in linked_events:
            if await self._is_message_related_to_event(event, snapshot):
                related_active.append(event)

        if related_active:
            for event in related_active:
                await asyncio.to_thread(self._save_source, event.event_id, snapshot)
                await asyncio.to_thread(self._touch_event, event.event_id, snapshot)
                if event.status == "ready_for_stance":
                    await self._wake_runtime_for_stance(snapshot, event.event_id)
                await self._schedule_analysis(event.event_id)
            await asyncio.to_thread(self._advance_lifecycle)
            return

        if len(window) < EVENT_MIN_MESSAGES or len({message.speaker_key for message in window}) < EVENT_MIN_SPEAKERS:
            await asyncio.to_thread(self._advance_lifecycle)
            return
        now_monotonic = asyncio.get_running_loop().time()
        last_cluster_attempt = self._last_cluster_attempt_by_session.get(snapshot.session_id, 0.0)
        if now_monotonic - last_cluster_attempt < 30:
            await asyncio.to_thread(self._advance_lifecycle)
            return
        self._last_cluster_attempt_by_session[snapshot.session_id] = now_monotonic
        if not await asyncio.to_thread(self._passes_activity_threshold, window, snapshot):
            await asyncio.to_thread(self._advance_lifecycle)
            return
        clusters = await self._cluster_window(snapshot, window)
        for cluster in clusters:
            cluster_messages = [window[index] for index in cluster.source_indices if 0 <= index < len(window)]
            if not self._passes_related_cluster_floor(cluster_messages):
                continue
            async with self._canonicalization_lock:
                event_id = await self._find_or_create_canonical_event(snapshot, cluster, cluster_messages)
            if event_id is None:
                # 匹配服务异常时不创建可能重复的并行档案；数据库中的聊天记录留给后续聚类重试。
                continue
            for source in cluster_messages:
                await asyncio.to_thread(self._save_source, event_id, source)
            await asyncio.to_thread(self._touch_event, event_id, snapshot)
            event = await asyncio.to_thread(self._get_event, event_id)
            if event is not None and event.status == "ready_for_stance":
                await self._wake_runtime_for_stance(snapshot, event_id)
            await self._schedule_analysis(event_id)
        await asyncio.to_thread(self._advance_lifecycle)

    def _find_window_messages(self, snapshot: EventMessageSnapshot) -> list[EventMessageSnapshot]:
        cutoff = snapshot.timestamp - timedelta(seconds=EVENT_WINDOW_SECONDS)
        with get_db_session(auto_commit=False) as session:
            rows = session.exec(
                select(
                    Messages.message_id,
                    Messages.session_id,
                    Messages.platform,
                    Messages.account_id,
                    Messages.scope,
                    Messages.group_id,
                    Messages.group_name,
                    Messages.user_id,
                    Messages.timestamp,
                    Messages.processed_plain_text,
                )
                .where(Messages.session_id == snapshot.session_id)
                .where(Messages.timestamp >= cutoff)
                .where(Messages.timestamp <= snapshot.timestamp)
                .where(Messages.is_notify.is_(False))
                .where(Messages.is_command.is_(False))
                .order_by(Messages.timestamp)
                .limit(EVENT_MAX_WINDOW_MESSAGES)
            ).all()
        result: list[EventMessageSnapshot] = []
        for row in rows:
            message_id, session_id, platform, account_id, scope, group_id, group_name, user_id, timestamp, plain_text = row
            if is_bot_self(platform, user_id):
                continue
            text = " ".join(str(plain_text or "").split()).strip()
            if not text or not message_id:
                continue
            result.append(
                EventMessageSnapshot(
                    message_id=message_id,
                    session_id=session_id,
                    platform=platform,
                    account_id=str(account_id or ""),
                    scope=str(scope or ""),
                    group_id=str(group_id or snapshot.group_id),
                    group_name=str(group_name or snapshot.group_name),
                    user_id=str(user_id or ""),
                    timestamp=timestamp,
                    text=text,
                )
            )
        if all(item.message_id != snapshot.message_id for item in result):
            result.append(snapshot)
        return result

    def _passes_activity_threshold(
        self,
        messages: list[EventMessageSnapshot],
        snapshot: EventMessageSnapshot,
    ) -> bool:
        if len(messages) < EVENT_MIN_MESSAGES:
            return False
        if len({message.speaker_key for message in messages}) < EVENT_MIN_SPEAKERS:
            return False
        return self._passes_activity_baseline(snapshot, len(messages))

    def _passes_activity_baseline(self, snapshot: EventMessageSnapshot, current_count: int) -> bool:
        """按群聊同一十分钟时段的近 30 天活跃基线抑制高活跃群误报。"""
        history_start = snapshot.timestamp - timedelta(days=EVENT_BASELINE_DAYS)
        minute_bucket = snapshot.timestamp.minute // 10
        with get_db_session(auto_commit=False) as session:
            rows = session.exec(
                select(func.date(Messages.timestamp), func.count())
                .where(Messages.platform == snapshot.platform)
                .where(Messages.account_id == (snapshot.account_id or None))
                .where(Messages.scope == (snapshot.scope or None))
                .where(Messages.group_id == snapshot.group_id)
                .where(Messages.timestamp >= history_start)
                .where(Messages.timestamp < snapshot.timestamp - timedelta(seconds=EVENT_WINDOW_SECONDS))
                .where(Messages.is_notify.is_(False))
                .where(Messages.is_command.is_(False))
                .where(cast(func.strftime("%H", Messages.timestamp), Integer) == snapshot.timestamp.hour)
                .where(cast(func.strftime("%M", Messages.timestamp), Integer) // 10 == minute_bucket)
                .group_by(func.date(Messages.timestamp))
            ).all()
        if len(rows) < 14:
            return True
        baseline_mean = sum(int(count) for _, count in rows) / len(rows)
        return current_count >= max(EVENT_MIN_MESSAGES, baseline_mean * EVENT_ACTIVE_BASELINE_MULTIPLIER)

    @staticmethod
    def _passes_related_cluster_floor(messages: list[EventMessageSnapshot]) -> bool:
        return (
            len(messages) >= EVENT_MIN_MESSAGES
            and len({message.speaker_key for message in messages}) >= EVENT_MIN_SPEAKERS
        )

    async def _request_json(self, prompt: str, *, max_tokens: int = 8192) -> dict[str, Any]:
        result = await self._analysis_client.generate_response(
            prompt,
            LLMGenerationOptions(
                temperature=0.1,
                max_tokens=max_tokens,
                response_format=RespFormat(format_type=RespFormatType.JSON_OBJ),
            ),
        )
        payload = json.loads(result.response or "{}")
        if not isinstance(payload, dict):
            raise ValueError("event_analysis 必须返回 JSON 对象")
        return payload

    async def _cluster_window(
        self,
        snapshot: EventMessageSnapshot,
        messages: list[EventMessageSnapshot],
    ) -> list[EventCluster]:
        speaker_aliases: dict[str, str] = {}
        source_lines: list[str] = []
        for index, message in enumerate(messages):
            alias = speaker_aliases.setdefault(message.speaker_key, f"发言者{len(speaker_aliases) + 1}")
            source_lines.append(f"[{index}] {message.timestamp.isoformat()} {alias}: {message.text[:EVENT_MAX_SNAPSHOT_CHARS]}")
        prompt = (
            "你是群聊事件候选聚类器。仅将明确讨论同一现实事件/议题的消息放入同一簇；"
            "不要把一般闲聊、同类但不同的事件合并。只输出 JSON：clusters=[{title,root_cause,source_indices,confidence}]。"
            "source_indices 必须引用输入编号，confidence 为 0 到 1。"
            f"\n群聊时间窗 {snapshot.timestamp.isoformat()}：\n" + "\n".join(source_lines)
        )
        try:
            payload = await self._request_json(prompt, max_tokens=4096)
            parsed = EventClusterPayload.model_validate(payload)
        except Exception as exc:
            logger.debug("事件候选聚类失败: session_id=%s error=%s", snapshot.session_id, exc)
            return []
        clusters: list[EventCluster] = []
        for cluster in parsed.clusters:
            indices = sorted({i for i in cluster.source_indices if 0 <= i < len(messages)})
            candidate = cluster.model_copy(update={"source_indices": indices})
            candidate_messages = [messages[i] for i in indices]
            if candidate.confidence >= 0.55 and self._passes_related_cluster_floor(candidate_messages):
                clusters.append(candidate)
        clusters.sort(key=lambda item: item.confidence, reverse=True)
        non_overlapping: list[EventCluster] = []
        claimed_indices: set[int] = set()
        for cluster in clusters:
            unique_indices = [index for index in cluster.source_indices if index not in claimed_indices]
            if not self._passes_related_cluster_floor([messages[index] for index in unique_indices]):
                continue
            claimed_indices.update(unique_indices)
            non_overlapping.append(cluster.model_copy(update={"source_indices": unique_indices}))
        clusters = non_overlapping
        return clusters

    async def _find_or_create_canonical_event(
        self,
        snapshot: EventMessageSnapshot,
        cluster: EventCluster,
        cluster_messages: list[EventMessageSnapshot],
    ) -> Optional[str]:
        events = await asyncio.to_thread(self._find_canonical_candidates, snapshot)
        if events:
            matches = await self._match_existing_events(cluster, cluster_messages, events)
            if matches is None:
                return None
            matched_events = matches
            if matched_events:
                canonical = await asyncio.to_thread(self._select_canonical_event, matched_events)
                duplicate_ids = [event.event_id for event in matched_events if event.event_id != canonical.event_id]
                if duplicate_ids:
                    await asyncio.to_thread(self._merge_duplicate_events, canonical.event_id, duplicate_ids)
                await asyncio.to_thread(self._refresh_canonical_event, canonical.event_id, cluster)
                if len(matched_events) > 1:
                    logger.info(
                        "已归一重复群聊事件: canonical=%s merged=%s title=%s",
                        canonical.event_id,
                        ",".join(duplicate_ids),
                        cluster.title,
                    )
                return canonical.event_id
        return await asyncio.to_thread(self._create_event, snapshot, cluster)

    async def _match_existing_events(
        self,
        cluster: EventCluster,
        cluster_messages: list[EventMessageSnapshot],
        events: list[GroupEvent],
    ) -> Optional[list[GroupEvent]]:
        """将候选与活跃档案归一比对；None 表示模型调用失败，调用者不得另建档案。"""
        if not events:
            return []
        exact_matches = self._find_exact_signature_matches(events, cluster)
        try:
            if exact_matches:
                matches = exact_matches
            else:
                comparisons = "\n".join(
                    f"[{index}] event_id={event.event_id}; title={event.title}; root={event.root_cause}; "
                    f"status={event.status}"
                    for index, event in enumerate(events)
                )
                evidence = "\n".join(
                    f"- {message.timestamp.isoformat()}: {message.text[:240]}"
                    for message in cluster_messages[:12]
                )
                prompt = (
                    "将新候选事件与给定的活跃档案逐一比对。一个具体现实事件即使标题措辞不同、在同一群或不同群讨论，"
                    "也必须归到同一规范事件；同类但不同时间/对象/起因的事件不可合并。"
                    "只输出 JSON：matches=[{event_index(integer),confidence(0到1)}]，可返回多个重复档案；"
                    "没有匹配则 matches 为空。只有确认是同一具体事件才给出高置信度。"
                    f"\n新候选：标题={cluster.title}\n起因={cluster.root_cause}\n候选证据：\n{evidence}"
                    f"\n已有档案：\n{comparisons}"
                )
                raw_match = await self._request_json(prompt, max_tokens=1024)
                if "matches" in raw_match:
                    parsed = EventCanonicalMatchPayload.model_validate(raw_match)
                    matches = [
                        match for match in parsed.matches
                        if 0 <= match.event_index < len(events)
                        and math.isfinite(match.confidence)
                        and match.confidence >= EVENT_CANONICAL_MATCH_THRESHOLD
                    ]
                else:
                    # 兼容升级期间正在进行的旧版 event_analysis 返回结构。
                    index = int(raw_match.get("event_index", -1))
                    confidence = float(raw_match.get("confidence", 0.0))
                    matches = (
                        [EventCanonicalMatch(event_index=index, confidence=confidence)]
                        if 0 <= index < len(events)
                        and math.isfinite(confidence)
                        and EVENT_CANONICAL_MATCH_THRESHOLD <= confidence <= 1.0
                        else []
                    )
            matched_ids = {match.event_index for match in matches}
            return list({events[index].event_id: events[index] for index in sorted(matched_ids)}.values())
        except Exception as exc:
            logger.warning("规范事件匹配失败，本轮不创建新档案以避免重复: %s", exc)
            return None

    async def _reconcile_existing_duplicates(self) -> None:
        """后台归一历史活跃档案；按账号路由作用域分组，绝不跨作用域合并。"""
        try:
            events = await asyncio.to_thread(self._load_active_canonical_events)
            logger.info("群聊事件历史归一开始: active_event_count=%s", len(events))
            for event in events:
                sources = await asyncio.to_thread(self._load_sources, event.event_id)
                try:
                    analysis = json.loads(event.analysis_json or "{}")
                except json.JSONDecodeError:
                    analysis = {}
                analyzed_source_ids = set(analysis.get("analyzed_source_ids") or [])
                current_source_ids = {source.id for source in sources if source.id is not None}
                if len(sources) >= EVENT_MIN_MESSAGES and (
                    not analysis.get("timeline") or not current_source_ids.issubset(analyzed_source_ids)
                ):
                    logger.info(
                        "群聊事件分析补跑: event_id=%s source_count=%s has_timeline=%s",
                        event.event_id,
                        len(sources),
                        bool(analysis.get("timeline")),
                    )
                    await self._schedule_analysis(event.event_id)
            grouped_events: dict[tuple[str, str, str], list[GroupEvent]] = {}
            for event in events:
                scope_key = (event.platform, str(event.account_id or ""), str(event.scope or ""))
                grouped_events.setdefault(scope_key, []).append(event)

            reconciled_count = 0
            for scope_key, scoped_events in grouped_events.items():
                processed_event_ids: set[str] = set()
                for initial_seed in scoped_events:
                    if self._stopping:
                        return
                    async with self._canonicalization_lock:
                        current_events = await asyncio.to_thread(self._load_active_canonical_events)
                        active_scope_events = [
                            event for event in current_events
                            if (event.platform, str(event.account_id or ""), str(event.scope or "")) == scope_key
                        ]
                        seed_event = next(
                            (event for event in active_scope_events if event.event_id == initial_seed.event_id),
                            None,
                        )
                        if seed_event is None or seed_event.event_id in processed_event_ids:
                            continue
                        candidates = [
                            event for event in active_scope_events
                            if event.event_id != seed_event.event_id and event.event_id not in processed_event_ids
                        ]
                        processed_event_ids.add(seed_event.event_id)
                        if not candidates:
                            continue

                        candidates = self._rank_reconciliation_candidates(seed_event, candidates)
                        if not candidates:
                            continue
                        logger.info(
                            "群聊事件历史归一正在比对: event_id=%s candidate_count=%s",
                            seed_event.event_id,
                            len(candidates),
                        )

                        source_rows = await asyncio.to_thread(self._load_sources, seed_event.event_id)
                        source_snapshots = [
                            EventMessageSnapshot(
                                message_id=row.message_id,
                                session_id=row.session_id,
                                platform=row.platform,
                                account_id=str(row.account_id or ""),
                                scope=str(row.scope or ""),
                                group_id=row.group_id,
                                group_name="",
                                user_id=row.speaker_key,
                                timestamp=row.timestamp,
                                text=row.text_snapshot,
                            )
                            for row in source_rows
                        ]
                        matched_events = await self._match_existing_events(
                            EventCluster(title=seed_event.title, root_cause=seed_event.root_cause),
                            source_snapshots,
                            candidates,
                        )
                        if matched_events is None or not matched_events:
                            continue
                        merged_set = [seed_event, *matched_events]
                        canonical = await asyncio.to_thread(self._select_canonical_event, merged_set)
                        duplicate_ids = [
                            event.event_id for event in merged_set if event.event_id != canonical.event_id
                        ]
                        await asyncio.to_thread(self._merge_duplicate_events, canonical.event_id, duplicate_ids)
                        await self._schedule_analysis(canonical.event_id)
                        processed_event_ids.update(event.event_id for event in matched_events)
                        reconciled_count += len(duplicate_ids)

            logger.info("群聊事件历史归一完成: active_event_count=%s merged_event_count=%s", len(events), reconciled_count)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("群聊事件历史归一任务失败")

    @staticmethod
    def _load_active_canonical_events() -> list[GroupEvent]:
        with get_db_session(auto_commit=False) as session:
            return list(
                session.exec(
                    select(GroupEvent)
                    .where(GroupEvent.canonical_event_id.is_(None))
                    .where(GroupEvent.status.in_(["collecting", "reviewing", "ready_for_stance", "stance_active"]))
                    .where(GroupEvent.last_activity_at >= datetime.now() - timedelta(seconds=EVENT_ARCHIVE_AFTER_SECONDS))
                    .order_by(GroupEvent.created_at)
                ).all()
            )

    @staticmethod
    def _find_exact_signature_matches(
        events: list[GroupEvent], cluster: EventCluster
    ) -> list[EventCanonicalMatch]:
        """在 LLM 判断前识别标题和根因均完全一致的重复候选。"""

        def normalize(value: str) -> str:
            return re.sub(r"[\W_]+", "", value.casefold(), flags=re.UNICODE)

        title = normalize(cluster.title)
        root_cause = normalize(cluster.root_cause)
        if not title or not root_cause:
            return []
        return [
            EventCanonicalMatch(event_index=index, confidence=1.0)
            for index, event in enumerate(events)
            if normalize(event.title) == title and normalize(event.root_cause) == root_cause
        ]

    def _find_canonical_candidates(self, snapshot: EventMessageSnapshot) -> list[GroupEvent]:
        """查找相同平台、账号和路由作用域中的活跃规范事件，包括当前群事件。"""
        with get_db_session(auto_commit=False) as session:
            events = session.exec(
                select(GroupEvent)
                .where(GroupEvent.platform == snapshot.platform)
                .where(GroupEvent.account_id == (snapshot.account_id or None))
                .where(GroupEvent.scope == (snapshot.scope or None))
                .where(GroupEvent.canonical_event_id.is_(None))
                .where(GroupEvent.status.in_(["collecting", "reviewing", "ready_for_stance", "stance_active"]))
                .order_by(desc(GroupEvent.updated_at))
                .limit(50)
            ).all()
            return list(events)

    @staticmethod
    def _rank_reconciliation_candidates(seed_event: GroupEvent, candidates: list[GroupEvent]) -> list[GroupEvent]:
        """仅让明显共享实体/短语的历史记录进入昂贵的 LLM 归一比对。"""

        def corpus(event: GroupEvent) -> str:
            parts = [event.title, event.root_cause]
            try:
                analysis = json.loads(event.analysis_json or "{}")
            except json.JSONDecodeError:
                analysis = {}
            parts.extend(str(item) for item in analysis.get("key_facts", []) if item)
            parts.extend(
                str(item.get("summary") or item.get("event") or "")
                for item in analysis.get("timeline", [])
                if isinstance(item, dict)
            )
            parts.extend(
                str(item.get("label") or item.get("name") or "")
                for item in analysis.get("viewpoints", [])
                if isinstance(item, dict)
            )
            return re.sub(r"\s+", "", " ".join(parts)).casefold()

        def character_ngrams(text: str) -> set[str]:
            normalized = "".join(character for character in text if character.isalnum())
            return {normalized[index : index + 2] for index in range(len(normalized) - 1)}

        seed_grams = character_ngrams(corpus(seed_event))
        ranked: list[tuple[float, GroupEvent]] = []
        for candidate in candidates:
            candidate_grams = character_ngrams(corpus(candidate))
            union = seed_grams | candidate_grams
            similarity = len(seed_grams & candidate_grams) / len(union) if union else 0.0
            if similarity >= EVENT_RECONCILE_SIMILARITY_THRESHOLD:
                ranked.append((similarity, candidate))
        ranked.sort(key=lambda item: item[0], reverse=True)
        return [event for _, event in ranked[:EVENT_RECONCILE_MAX_CANDIDATES]]

    @staticmethod
    def _select_canonical_event(events: list[GroupEvent]) -> GroupEvent:
        """保留已确认立场优先，其次保留证据最多的档案作为唯一规范项。"""
        with get_db_session(auto_commit=False) as session:
            counts = {
                event.event_id: int(
                    session.exec(
                        select(func.count()).select_from(GroupEventSource).where(
                            GroupEventSource.event_id == event.event_id
                        )
                    ).one()
                )
                for event in events
            }
        return max(
            events,
            key=lambda event: (
                event.status == "stance_active",
                bool(event.stance_summary.strip()),
                counts[event.event_id],
                -event.created_at.timestamp(),
            ),
        )

    @staticmethod
    def _merge_duplicate_events(canonical_event_id: str, duplicate_event_ids: list[str]) -> None:
        """将重复档案的消息与群关联无损并入规范项，重复档案保留为可追溯别名。"""
        now = datetime.now()
        with get_db_session() as session:
            canonical = session.get(GroupEvent, canonical_event_id)
            if canonical is None:
                raise ValueError(f"规范事件不存在: {canonical_event_id}")

            stance_records = {
                (canonical.stance_type, canonical.stance_summary.strip())
            } if canonical.stance_summary.strip() else set()
            for duplicate_event_id in duplicate_event_ids:
                duplicate = session.get(GroupEvent, duplicate_event_id)
                if duplicate is None or duplicate.canonical_event_id is not None:
                    continue
                if duplicate.stance_summary.strip():
                    stance_records.add((duplicate.stance_type, duplicate.stance_summary.strip()))

                canonical_sources = {
                    (source.session_id, source.message_id)
                    for source in session.exec(
                        select(GroupEventSource).where(GroupEventSource.event_id == canonical_event_id)
                    ).all()
                }
                for source in session.exec(
                    select(GroupEventSource).where(GroupEventSource.event_id == duplicate_event_id)
                ).all():
                    source_key = (source.session_id, source.message_id)
                    if source_key in canonical_sources:
                        session.delete(source)
                    else:
                        source.event_id = canonical_event_id
                        session.add(source)
                        canonical_sources.add(source_key)

                canonical_groups = {
                    group.session_id: group
                    for group in session.exec(
                        select(GroupEventGroup).where(GroupEventGroup.event_id == canonical_event_id)
                    ).all()
                }
                for group in session.exec(
                    select(GroupEventGroup).where(GroupEventGroup.event_id == duplicate_event_id)
                ).all():
                    existing_group = canonical_groups.get(group.session_id)
                    if existing_group is None:
                        group.event_id = canonical_event_id
                        session.add(group)
                        canonical_groups[group.session_id] = group
                    else:
                        existing_group.first_activity_at = min(existing_group.first_activity_at, group.first_activity_at)
                        existing_group.last_activity_at = max(existing_group.last_activity_at, group.last_activity_at)
                        if group.group_name:
                            existing_group.group_name = group.group_name
                        session.add(existing_group)
                        session.delete(group)

                canonical.last_activity_at = max(canonical.last_activity_at, duplicate.last_activity_at)
                canonical.last_material_activity_at = max(
                    canonical.last_material_activity_at, duplicate.last_material_activity_at
                )
                duplicate.status = "merged"
                duplicate.canonical_event_id = canonical_event_id
                duplicate.updated_at = now
                session.add(duplicate)

            if len(stance_records) > 1:
                try:
                    analysis = json.loads(canonical.analysis_json or "{}")
                except json.JSONDecodeError:
                    analysis = {}
                analysis["deduplicated_stance_conflicts"] = [
                    {"type": kind, "summary": summary} for kind, summary in sorted(stance_records)
                ]
                analysis["coverage_complete"] = False
                canonical.analysis_json = json.dumps(analysis, ensure_ascii=False)
                canonical.status = "reviewing"
                canonical.stance_type = ""
                canonical.stance_summary = ""
                canonical.stance_reasoning = ""
                canonical.stance_confidence = 0.0
            else:
                try:
                    analysis = json.loads(canonical.analysis_json or "{}")
                except json.JSONDecodeError:
                    analysis = {}
                analysis["coverage_complete"] = False
                canonical.analysis_json = json.dumps(analysis, ensure_ascii=False)
                if canonical.status != "stance_active":
                    canonical.status = "collecting"
                    canonical.ready_at = None
            canonical.updated_at = now
            session.add(canonical)

    @staticmethod
    def _refresh_canonical_event(event_id: str, cluster: EventCluster) -> None:
        """刷新规范项标题与根因；档案自有结论优先，避免低质量候选覆盖好摘要。"""
        with get_db_session() as session:
            event = session.get(GroupEvent, event_id)
            if event is None:
                raise ValueError(f"规范事件不存在: {event_id}")
            if not event.title.strip() and cluster.title.strip():
                event.title = cluster.title[:500]
            if not event.root_cause.strip() and cluster.root_cause.strip():
                event.root_cause = cluster.root_cause
            event.updated_at = datetime.now()
            session.add(event)

    @staticmethod
    def _get_event(event_id: str) -> Optional[GroupEvent]:
        with get_db_session(auto_commit=False) as session:
            return session.get(GroupEvent, event_id)

    async def _wake_runtime_for_stance(self, snapshot: EventMessageSnapshot, event_id: str) -> None:
        """唤醒当前消息所属 Runtime，让待确认事件跳过普通发言频率门槛。"""
        from src.chat.heart_flow.heartflow_manager import heartflow_manager

        runtime = await heartflow_manager.get_or_create_heartflow_chat(snapshot.session_id)
        await runtime.schedule_event_stance_confirmation(snapshot.message_id, event_id)

    def _find_events_for_session(self, session_id: str) -> list[GroupEvent]:
        with get_db_session(auto_commit=False) as session:
            relations = session.exec(select(GroupEventGroup).where(GroupEventGroup.session_id == session_id)).all()
            result: list[GroupEvent] = []
            for relation in relations:
                event = session.get(GroupEvent, relation.event_id)
                if event is not None and event.status not in {"archived", "archived_incomplete", "merged"}:
                    result.append(event)
            return result

    async def _is_message_related_to_event(self, event: GroupEvent, snapshot: EventMessageSnapshot) -> bool:
        event_tokens = set(_TOKEN_RE.findall(f"{event.title} {event.root_cause}".lower()))
        message_tokens = set(_TOKEN_RE.findall(snapshot.text.lower()))
        overlap = len(event_tokens & message_tokens) / max(1, len(event_tokens | message_tokens))
        if overlap <= 0:
            return False
        prompt = (
            "判断新消息是否与当前群聊事件直接相关。只输出 JSON：related(boolean)、material_evidence(boolean)。"
            "同一大主题但不同具体事件应标为 false。"
            f"\n事件标题：{event.title}\n事件起因：{event.root_cause}\n新消息：{snapshot.text}"
        )
        try:
            payload = await self._request_json(prompt, max_tokens=384)
            return bool(payload.get("related"))
        except Exception as exc:
            logger.debug("事件关联判定失败，按来源词项保持保护: %s", exc)
            return overlap >= 0.08

    def _create_event(self, snapshot: EventMessageSnapshot, cluster: EventCluster) -> str:
        now = snapshot.timestamp
        recurrence = self._find_archived_recurrence(snapshot, cluster)
        event_id = f"event:{uuid.uuid4().hex}"
        with get_db_session() as session:
            session.add(
                GroupEvent(
                    event_id=event_id,
                    recurrence_of_event_id=recurrence,
                    platform=snapshot.platform,
                    account_id=snapshot.account_id or None,
                    scope=snapshot.scope or None,
                    status="collecting",
                    title=cluster.title[:500],
                    root_cause=cluster.root_cause,
                    created_at=now,
                    updated_at=now,
                    last_activity_at=now,
                    last_material_activity_at=now,
                )
            )
        return event_id

    def _find_archived_recurrence(self, snapshot: EventMessageSnapshot, cluster: EventCluster) -> Optional[str]:
        with get_db_session(auto_commit=False) as session:
            events = session.exec(
                select(GroupEvent)
                .where(GroupEvent.platform == snapshot.platform)
                .where(GroupEvent.account_id == (snapshot.account_id or None))
                .where(GroupEvent.scope == (snapshot.scope or None))
                .where(GroupEvent.status.in_(["archived", "archived_incomplete"]))
                .order_by(desc(GroupEvent.updated_at))
                .limit(50)
            ).all()
        candidate_tokens = set(_TOKEN_RE.findall(f"{cluster.title} {cluster.root_cause}".lower()))
        for event in events:
            archived_tokens = set(_TOKEN_RE.findall(f"{event.title} {event.root_cause}".lower()))
            overlap = len(candidate_tokens & archived_tokens) / max(1, len(candidate_tokens | archived_tokens))
            if overlap >= EVENT_ARCHIVED_RECURRENCE_MATCH_THRESHOLD:
                return event.event_id
        return None

    def _save_source(self, event_id: str, snapshot: EventMessageSnapshot) -> None:
        with get_db_session() as session:
            exists = session.exec(
                select(GroupEventSource)
                .where(GroupEventSource.event_id == event_id)
                .where(GroupEventSource.session_id == snapshot.session_id)
                .where(GroupEventSource.message_id == snapshot.message_id)
            ).first()
            if exists is None:
                session.add(
                    GroupEventSource(
                        event_id=event_id,
                        session_id=snapshot.session_id,
                        platform=snapshot.platform,
                        account_id=snapshot.account_id or None,
                        scope=snapshot.scope or None,
                        group_id=snapshot.group_id,
                        message_id=snapshot.message_id,
                        timestamp=snapshot.timestamp,
                        speaker_key=snapshot.speaker_key,
                        text_snapshot=snapshot.text[:EVENT_MAX_SNAPSHOT_CHARS],
                    )
                )
            relation = session.exec(
                select(GroupEventGroup)
                .where(GroupEventGroup.event_id == event_id)
                .where(GroupEventGroup.session_id == snapshot.session_id)
            ).first()
            if relation is None:
                session.add(
                    GroupEventGroup(
                        event_id=event_id,
                        session_id=snapshot.session_id,
                        group_id=snapshot.group_id,
                        group_name=snapshot.group_name,
                        first_activity_at=snapshot.timestamp,
                        last_activity_at=snapshot.timestamp,
                    )
                )
            else:
                relation.last_activity_at = snapshot.timestamp
                if snapshot.group_name:
                    relation.group_name = snapshot.group_name
                session.add(relation)

    def _touch_event(self, event_id: str, snapshot: EventMessageSnapshot) -> None:
        with get_db_session() as session:
            event = session.get(GroupEvent, event_id)
            if event is None:
                return
            event.updated_at = snapshot.timestamp
            event.last_activity_at = snapshot.timestamp
            session.add(event)

    async def _schedule_analysis(self, event_id: str) -> None:
        if any(task.get_name() == f"group_event_analysis:{event_id}" for task in self._analysis_tasks):
            self._analysis_dirty_event_ids.add(event_id)
            return
        task = asyncio.create_task(self._analyze_event(event_id), name=f"group_event_analysis:{event_id}")
        self._analysis_tasks.add(task)
        task.add_done_callback(lambda completed, active_event_id=event_id: self._analysis_finished(active_event_id, completed))

    def _analysis_finished(self, event_id: str, task: asyncio.Task[None]) -> None:
        self._analysis_tasks.discard(task)
        if self._stopping:
            self._analysis_dirty_event_ids.discard(event_id)
            return
        if event_id in self._analysis_dirty_event_ids:
            self._analysis_dirty_event_ids.discard(event_id)
            next_task = asyncio.create_task(self._analyze_event(event_id), name=f"group_event_analysis:{event_id}")
            self._analysis_tasks.add(next_task)
            next_task.add_done_callback(
                lambda completed, active_event_id=event_id: self._analysis_finished(active_event_id, completed)
            )

    async def _analyze_event(self, event_id: str) -> None:
        while True:
            await asyncio.sleep(20)
            self._analysis_dirty_event_ids.discard(event_id)
            sources = await asyncio.to_thread(self._load_sources, event_id)
            if len(sources) < EVENT_MIN_MESSAGES:
                return
            speaker_aliases: dict[tuple[str, str], str] = {}
            group_aliases: dict[str, str] = {}
            source_lines: list[str] = []
            latest_sources = sources[-EVENT_MAX_CONTEXT_SOURCES:]
            source_id_map: dict[int, int] = {}
            for index, row in enumerate(latest_sources, start=1):
                group_alias = group_aliases.setdefault(row.group_id, f"讨论群{len(group_aliases) + 1}")
                speaker_key = (row.group_id, row.speaker_key)
                alias = speaker_aliases.setdefault(
                    speaker_key,
                    f"该群发言者{1 + sum(key[0] == row.group_id for key in speaker_aliases)}",
                )
                source_id_map[index] = row.id or 0
                source_lines.append(f"[{index}] {row.timestamp.isoformat()} {group_alias}/{alias}: {row.text_snapshot}")
            current_event = await asyncio.to_thread(self._get_event, event_id)
            current_stance = current_event.stance_summary if current_event is not None and current_event.stance_summary else "尚未确认"
            prompt = (
                "你是群聊事件档案分析器。请只依据证据整理同一事件，区分事实、各方说法和未知信息。"
                "不应输出成员身份或来源群原文给 Planner。只输出 JSON 对象，字段类型必须严格为：title(string)、"
                "root_cause(string)、root_cause_source_indices(integer[])、timeline(object[])、viewpoints(object[])、"
                "key_facts(string[])、uncertainties(string[])、coverage_complete(boolean)、related(boolean)、"
                "material_evidence(boolean)、major_counter_evidence(boolean)。"
                "不要把 root_cause 包成对象，也不要把 key_facts 写成对象数组。"
                "起因、每个时间线节点和每个观点都必须提供有效source_indices。"
                "timeline 和 viewpoints 每项都要用 source_indices 引用输入编号。coverage_complete 表示事件起因、"
                "关键时间线以及已发现的各主要观点都有证据支撑；若没有对立观点，应如实记录单一观点。"
                "material_evidence 仅当新消息带来此前分析中没有的关键事实/论据时为 true；"
                "major_counter_evidence 仅在既有立场受到有来源的重大反证时为 true。"
                + f"\n事件现有立场：{current_stance}"
                + "\n消息证据：\n" + "\n".join(source_lines)
            )
            try:
                raw = await self._request_json(prompt, max_tokens=8192)
                payload = EventAnalysisPayload.model_validate(raw)
            except Exception as exc:
                logger.warning("事件分析结果结构校验失败: event_id=%s error=%s", event_id, exc)
                return
            if payload.related:
                await asyncio.to_thread(self._save_analysis, event_id, payload, source_id_map)
            if event_id not in self._analysis_dirty_event_ids:
                return

    def _load_sources(self, event_id: str) -> list[GroupEventSource]:
        with get_db_session(auto_commit=False) as session:
            rows = session.exec(
                select(GroupEventSource)
                .where(GroupEventSource.event_id == event_id)
                .order_by(desc(GroupEventSource.timestamp))
                .limit(EVENT_MAX_CONTEXT_SOURCES)
            ).all()
        return list(reversed(rows))

    def _save_analysis(self, event_id: str, payload: EventAnalysisPayload, source_id_map: dict[int, int]) -> None:
        now = datetime.now()
        def normalize(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
            normalized: list[dict[str, Any]] = []
            for item in items:
                clean = dict(item)
                source_indices = item.get("source_indices")
                if isinstance(source_indices, list):
                    clean["source_ids"] = [
                        source_id_map[index]
                        for index in source_indices
                        if isinstance(index, int) and index in source_id_map and source_id_map[index]
                    ]
                    clean.pop("source_indices", None)
                normalized.append(clean)
            return normalized

        with get_db_session() as session:
            event = session.get(GroupEvent, event_id)
            if event is None or event.status in {"archived", "archived_incomplete", "merged"}:
                return
            root_source_ids = [
                source_id_map[index]
                for index in payload.root_cause_source_indices
                if isinstance(index, int) and index in source_id_map and source_id_map[index]
            ]
            key_fact_source_ids = [
                [source_id_map[index] for index in indices if index in source_id_map and source_id_map[index]]
                for indices in payload.key_fact_source_indices
            ]
            normalized_timeline = normalize(payload.timeline)
            normalized_viewpoints = normalize(payload.viewpoints)
            normalized_timeline = [
                {
                    **item,
                    "summary": str(item.get("summary") or item.get("event") or item.get("description") or ""),
                }
                for item in normalized_timeline
            ]
            evidence_complete = bool(
                payload.coverage_complete
                and payload.root_cause.strip()
                and root_source_ids
                and normalized_timeline
                and all(item.get("source_ids") for item in normalized_timeline)
                and all(item.get("source_ids") for item in normalized_viewpoints)
            )
            event.title = payload.title[:500] or event.title
            event.root_cause = payload.root_cause
            try:
                previous_analysis = json.loads(event.analysis_json or "{}")
            except json.JSONDecodeError:
                previous_analysis = {}
            previous_source_ids = set(previous_analysis.get("analyzed_source_ids") or [])
            current_source_ids = set(source_id_map.values()) - {0}
            has_new_sources = bool(current_source_ids - previous_source_ids)
            previous_analysis.update(
                {
                    "root_cause_source_ids": root_source_ids,
                    "timeline": normalized_timeline,
                    "viewpoints": normalized_viewpoints,
                    "key_facts": payload.key_facts,
                    "key_fact_source_ids": key_fact_source_ids,
                    "uncertainties": payload.uncertainties,
                    "coverage_complete": evidence_complete,
                    "analyzed_source_ids": sorted(previous_source_ids | current_source_ids),
                }
            )
            event.analysis_json = json.dumps(previous_analysis, ensure_ascii=False)
            event.updated_at = now
            if payload.material_evidence and has_new_sources:
                event.last_material_activity_at = now
                if event.status == "ready_for_stance":
                    event.status = "collecting"
                    event.ready_at = None
            if event.status == "stance_active" and payload.major_counter_evidence:
                event.status = "reviewing"
                event.ready_at = None
                event.last_material_activity_at = now
            session.add(event)

    @staticmethod
    def _stable_since(event: GroupEvent) -> bool:
        return (datetime.now() - event.last_material_activity_at).total_seconds() >= EVENT_ANALYSIS_STABILITY_SECONDS

    def _advance_lifecycle(self) -> None:
        """按稳定窗口和24小时冷却推进 ready/archive 状态。"""
        now = datetime.now()
        with get_db_session() as session:
            events = session.exec(
                select(GroupEvent).where(
                    GroupEvent.status.notin_(["archived", "archived_incomplete", "merged"])
                )
            ).all()
            for event in events:
                if (now - event.last_activity_at).total_seconds() >= EVENT_ARCHIVE_AFTER_SECONDS:
                    event.status = "archived" if event.status == "stance_active" else "archived_incomplete"
                    event.closed_at = now
                    event.updated_at = now
                    session.add(event)
                    continue
                if event.status in {"collecting", "reviewing"} and self._stable_since(event):
                    try:
                        analysis = json.loads(event.analysis_json or "{}")
                    except json.JSONDecodeError:
                        analysis = {}
                    if bool(analysis.get("coverage_complete")):
                        event.status = "ready_for_stance"
                        event.ready_at = now
                        event.updated_at = now
                        session.add(event)

    @staticmethod
    def _get_events_for_context(session_id: str) -> list[GroupEvent]:
        with get_db_session(auto_commit=False) as session:
            relations = session.exec(select(GroupEventGroup).where(GroupEventGroup.session_id == session_id)).all()
            events: list[GroupEvent] = []
            seen: set[str] = set()
            for relation in relations:
                if relation.event_id in seen:
                    continue
                event = session.get(GroupEvent, relation.event_id)
                if event is not None and event.status not in {"archived", "archived_incomplete", "merged"}:
                    events.append(event)
                    seen.add(event.event_id)
            return events

    async def get_contexts_for_source(self, session_id: str, message_id: str) -> list[EventContext]:
        """读取与实际引用源消息关联的事件，避免仅用生成文本猜测话题归属。"""
        event_ids = await asyncio.to_thread(self._find_event_ids_for_source, session_id, message_id)
        if not event_ids:
            active_events = await asyncio.to_thread(self._get_events_for_context, session_id)
            event_ids = [event.event_id for event in active_events if event.status == "ready_for_stance"]
        contexts: list[EventContext] = []
        for event_id in event_ids:
            event = await asyncio.to_thread(self._get_event, event_id)
            if event is not None and event.status not in {"archived", "archived_incomplete", "merged"}:
                contexts.append(self._build_event_context(event))
        return contexts

    @staticmethod
    def _find_event_ids_for_source(session_id: str, message_id: str) -> list[str]:
        with get_db_session(auto_commit=False) as session:
            rows = session.exec(
                select(GroupEventSource.event_id)
                .where(GroupEventSource.session_id == session_id)
                .where(GroupEventSource.message_id == message_id)
            ).all()
        return list(dict.fromkeys(rows))

    async def get_contexts_for_message(
        self,
        session_id: str,
        message_id: str,
        text: str = "",
    ) -> list[EventContext]:
        """优先按已归档的来源消息匹配事件，无法精确命中时再由模型做语义关联。"""
        if message_id:
            contexts = await self.get_contexts_for_source(session_id, message_id)
            if contexts:
                return contexts
        return await self.get_planner_contexts(session_id, relevant_text=text)

    async def get_planner_contexts(
        self,
        session_id: str,
        relevant_text: str = "",
    ) -> list[EventContext]:
        """返回当前会话中与最近消息相关的活跃事件摘要。"""
        events = await asyncio.to_thread(self._get_events_for_context, session_id)
        if not relevant_text.strip():
            return [self._build_event_context(event) for event in events]
        contexts: list[EventContext] = []
        for event in events:
            if await self._is_message_related_to_event(
                event,
                EventMessageSnapshot(
                    message_id="planner-context",
                    session_id=session_id,
                    platform=event.platform,
                    account_id=str(event.account_id or ""),
                    scope=str(event.scope or ""),
                    group_id="",
                    group_name="",
                    user_id="",
                    timestamp=datetime.now(),
                    text=relevant_text,
                ),
            ):
                contexts.append(self._build_event_context(event))
        return contexts

    @staticmethod
    def _build_event_context(event: GroupEvent) -> EventContext:
        analysis = json.loads(event.analysis_json or "{}")
        timeline = analysis.get("timeline") or []
        viewpoints = analysis.get("viewpoints") or []
        state_hint = "当前仍在积累证据，只能中立了解和归纳，不要赞同或反对任何一方。"
        if event.status == "ready_for_stance":
            state_hint = "分析达到可确认条件；相关发言前必须先调用 confirm_event_stance 确认立场，并使用 neutral 作为证据不足时的回退。"
        elif event.status == "reviewing":
            state_hint = "发现可能的重大反证，正在复核；复核完成前只能中立了解和归纳。"
        elif event.status == "stance_active":
            state_hint = f"事件当前立场：{event.stance_summary}。理由：{event.stance_reasoning}。除非状态重开为 reviewing，不要改变立场。"
        safe_timeline = [
            str(item.get("summary") or item.get("event") or "").strip()
            for item in timeline
            if isinstance(item, dict)
        ]
        safe_viewpoints = [
            {
                "label": str(item.get("label") or item.get("name") or "观点").strip(),
                "claims": item.get("claims") or [],
                "arguments": item.get("arguments") or [],
                "counterarguments": item.get("counterarguments") or [],
            }
            for item in viewpoints
            if isinstance(item, dict)
        ]
        sections = [
            f"【群聊事件内部参考 event_id={event.event_id}】",
            f"事件：{event.title}",
            f"起因：{event.root_cause or '仍在整理'}",
        ]
        if safe_timeline:
            sections.append("时间线摘要：" + "；".join(item for item in safe_timeline if item)[:1800])
        if safe_viewpoints:
            sections.append("观点流派摘要：" + json.dumps(safe_viewpoints, ensure_ascii=False)[:2600])
        if analysis.get("key_facts"):
            sections.append("已归纳事实：" + "；".join(str(item) for item in analysis["key_facts"][:12])[:1200])
        if analysis.get("uncertainties"):
            sections.append("仍待核实：" + "；".join(str(item) for item in analysis["uncertainties"][:8])[:800])
        sections.extend([state_hint, "该摘要不包含其他群原文、群名或成员身份。"])
        return EventContext(event.event_id, event.status, event.title, event.stance_type, event.stance_summary, "\n".join(sections))

    async def confirm_stance(
        self,
        *,
        event_id: str,
        stance_type: str,
        summary: str,
        reasoning: str,
        confidence: float,
    ) -> bool:
        return await asyncio.to_thread(
            self._confirm_stance_sync,
            event_id,
            stance_type,
            summary,
            reasoning,
            confidence,
        )

    @staticmethod
    def _confirm_stance_sync(event_id: str, stance_type: str, summary: str, reasoning: str, confidence: float) -> bool:
        if stance_type not in {"neutral", "support", "oppose", "mixed"}:
            return False
        with get_db_session() as session:
            event = session.get(GroupEvent, event_id)
            if event is not None and event.canonical_event_id:
                event = session.get(GroupEvent, event.canonical_event_id)
            if event is None or event.status != "ready_for_stance":
                return False
            event.status = "stance_active"
            event.stance_type = stance_type
            event.stance_summary = summary.strip()
            event.stance_reasoning = reasoning.strip()
            event.stance_confidence = max(0.0, min(1.0, float(confidence)))
            event.updated_at = datetime.now()
            session.add(event)
            return True

    async def _review_related_text(self, contexts: list[EventContext], text: str) -> str:
        collecting = [context for context in contexts if context.status in {"collecting", "ready_for_stance", "reviewing"}]
        active = [context for context in contexts if context.status == "stance_active"]
        if collecting and _STANCE_WORDS.search(text):
            return _NEUTRAL_FALLBACK
        if not collecting and not active:
            return text
        active_context = "\n".join(context.text for context in active)
        neutral_context = "\n".join(context.text for context in collecting)
        if collecting:
            instructions = (
                "积累阶段禁止赞同、反对、贬低或暗示支持任何一方；允许中立追问、核实和归纳。"
                "若原文带立场，请改写为中立核实或澄清问题。"
            )
        else:
            instructions = (
                "事件已有 Planner 确认的立场。判断回复是否违背该立场；若违背，改写成符合已确认立场的表达，"
                "不得添加未记录的新事实。若无法安全改写，使用中性核实句。"
            )
        prompt = (
            "你是群聊事件回复政策审核器。只输出 JSON：allowed(boolean)、rewritten_text(string)。"
            f"{instructions}\n积累中事件摘要：{neutral_context}\n活跃立场摘要：{active_context}\n待审核回复：{text}"
        )
        try:
            payload = await self._request_json(prompt, max_tokens=512)
            if bool(payload.get("allowed")):
                return text
            rewritten = str(payload.get("rewritten_text") or "").strip()
            if not rewritten:
                return _NEUTRAL_FALLBACK
            verify_prompt = (
                "审核改写结果是否满足规则，只输出 JSON：allowed(boolean)。不得输出解释。\n"
                f"规则：{instructions}\n事件摘要：{neutral_context}\n活跃立场：{active_context}\n改写：{rewritten}"
            )
            verify = await self._request_json(verify_prompt, max_tokens=128)
            return rewritten if bool(verify.get("allowed")) else _NEUTRAL_FALLBACK
        except Exception as exc:
            logger.warning("群聊事件回复审核失败，使用安全兜底: %s", exc)
            if collecting:
                return _NEUTRAL_FALLBACK
            return active[0].stance_summary if active and active[0].stance_summary else _NEUTRAL_FALLBACK

    async def guard_neutral_reply(self, session_id: str, text: str, source_message_id: str = "") -> str:
        contexts = await self.get_contexts_for_source(session_id, source_message_id) if source_message_id else []
        if not contexts:
            contexts = await self.get_planner_contexts(session_id, relevant_text=text)
        return await self._review_related_text(contexts, text) if contexts else text

    async def can_send_outbound(
        self,
        session_id: str,
        text: str,
        source_message_id: str = "",
    ) -> bool:
        """在统一发送边界阻止其他工具绕过待确认事件的 Planner gate。"""
        contexts = await self.get_contexts_for_source(session_id, source_message_id) if source_message_id else []
        if not contexts:
            contexts = await self.get_planner_contexts(session_id, relevant_text=text)
        return not any(context.status == "ready_for_stance" for context in contexts)

    async def guard_outbound_text(
        self,
        session_id: str,
        text: str,
        source_message_id: str = "",
    ) -> str:
        contexts = await self.get_contexts_for_source(session_id, source_message_id) if source_message_id else []
        if not contexts:
            contexts = await self.get_planner_contexts(session_id, relevant_text=text)
        return await self._review_related_text(contexts, text) if contexts else text


_group_event_service = GroupEventService()


def get_group_event_service() -> GroupEventService:
    """返回群聊事件跟踪服务单例。"""

    return _group_event_service
