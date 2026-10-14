"""机器人账号级日程状态、活动计划和内部草稿服务。"""

from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time, timedelta
from hashlib import sha256
from typing import Any
from zoneinfo import ZoneInfo

import asyncio
import json
import random

from sqlalchemy import desc, func
from sqlmodel import select

from src.common.database.database import get_db_session
from src.common.database.database_model import DailyRoutineActivity, DailyRoutineDraft, DailyRoutineState
from src.common.logger import get_logger
from src.config.config import global_config

logger = get_logger("daily_routine")


@dataclass(frozen=True)
class RoutineActivitySpec:
    """用于生成一天计划的活动模板。"""

    activity_id: str
    name: str
    activity_type: str
    start_hour: int
    start_minute: int
    duration_minutes: int
    probability: float = 1.0
    variance_minutes: int = 20


@dataclass
class RoutineMood:
    """不直接暴露给模型的日程内部状态。"""

    energy: int = 70
    mood: int = 60
    social_desire: int = 55
    focus: int = 60

    def clamp(self) -> None:
        self.energy = max(0, min(100, int(self.energy)))
        self.mood = max(0, min(100, int(self.mood)))
        self.social_desire = max(0, min(100, int(self.social_desire)))
        self.focus = max(0, min(100, int(self.focus)))


@dataclass(frozen=True)
class RoutineActivity:
    """对外提供的单项日程活动快照。"""

    activity_id: str
    name: str
    activity_type: str
    scheduled_start: datetime
    scheduled_end: datetime
    status: str


@dataclass(frozen=True)
class RoutineSnapshot:
    """日程运行时当前快照。"""

    account_key: str
    platform: str
    account_id: str
    timezone: str
    day_key: str
    current_activity: RoutineActivity | None
    activities: tuple[RoutineActivity, ...]
    mood: RoutineMood
    interaction_count: int
    last_sleep_quality: int
    updated_at: datetime


@dataclass(frozen=True)
class RoutineTurnPolicy:
    """日程对消息回复门控和 Planner 表达的影响。"""

    multiplier: float
    status_label: str
    expression_hint: str
    should_deprioritize: bool


@dataclass
class _AccountState:
    platform: str
    account_id: str
    timezone: str
    day_key: str
    mood: RoutineMood = field(default_factory=RoutineMood)
    activities: list[RoutineActivity] = field(default_factory=list)
    last_updated_at: datetime = field(default_factory=datetime.now)
    last_interaction_at: datetime | None = None
    interaction_count: int = 0
    positive_interaction_count: int = 0
    last_sleep_quality: int = 70
    plan_generated: bool = False

    @property
    def account_key(self) -> str:
        return DailyRoutineService.build_account_key(self.platform, self.account_id)


_ACTIVITY_SPECS: tuple[RoutineActivitySpec, ...] = (
    RoutineActivitySpec("wake", "起床和清醒", "fixed", 7, 30, 35, variance_minutes=30),
    RoutineActivitySpec("breakfast", "吃早餐", "fixed", 8, 20, 35, variance_minutes=15),
    RoutineActivitySpec("lunch", "吃午饭", "fixed", 12, 30, 45, variance_minutes=15),
    RoutineActivitySpec("nap", "午休", "fixed", 13, 30, 45, probability=0.5, variance_minutes=20),
    RoutineActivitySpec("dinner", "吃晚饭", "fixed", 18, 45, 45, variance_minutes=20),
    RoutineActivitySpec("interest", "兴趣活动", "interest", 20, 30, 45, probability=0.45, variance_minutes=45),
    RoutineActivitySpec("wind_down", "睡前放松", "fixed", 22, 30, 50, variance_minutes=20),
    RoutineActivitySpec("sleep", "睡觉", "fixed", 23, 30, 30, variance_minutes=20),
)


class DailyRoutineService:
    """维护机器人账号级日程状态，并提供同步的快速查询接口。"""

    def __init__(self) -> None:
        self._accounts: dict[str, _AccountState] = {}
        self._loaded = False
        self._lock = asyncio.Lock()

    @staticmethod
    def build_account_key(platform: str, account_id: str | None) -> str:
        """基于适配器真实上报的身份构造账号级归属键，不使用 session hash。"""

        normalized_platform = str(platform or "").strip()
        normalized_account_id = str(account_id or "").strip()
        return f"{normalized_platform}:{normalized_account_id}"

    @property
    def is_running(self) -> bool:
        """返回日程状态服务是否已加载。"""

        return self._loaded

    async def start(self) -> None:
        """加载已持久化状态；短查询只读取内存，避免阻塞消息循环。"""

        if not global_config.daily_routine.enabled:
            logger.info("日程运行时未启用")
            return
        async with self._lock:
            if self._loaded:
                return
            records = await asyncio.to_thread(self._load_states_sync)
            for record in records:
                state = self._state_from_record(record)
                self._accounts[state.account_key] = state
            self._loaded = True
        logger.info(f"日程运行时已启动: accounts={len(self._accounts)}")

    async def stop(self) -> None:
        """保存当前内存状态并释放运行时状态。"""

        if not self._loaded:
            return
        await self.persist()
        self._loaded = False
        logger.info("日程运行时已停止")

    async def persist(self) -> None:
        """异步持久化所有账号状态和当日活动。"""

        records = [self._record_from_state(state) for state in self._accounts.values()]
        activities = [
            (state.account_key, state.day_key, activity)
            for state in self._accounts.values()
            for activity in state.activities
        ]
        if records:
            await asyncio.to_thread(self._persist_sync, records, activities)

    def ensure_account(self, platform: str, account_id: str | None) -> _AccountState:
        """在第一次收到该账号消息时创建内存状态。"""

        normalized_platform = str(platform or "").strip()
        normalized_account_id = str(account_id or "").strip()
        account_key = self.build_account_key(normalized_platform, normalized_account_id)
        state = self._accounts.get(account_key)
        if state is None:
            state = _AccountState(
                platform=normalized_platform,
                account_id=normalized_account_id,
                timezone=global_config.daily_routine.timezone,
                day_key=self._local_now(global_config.daily_routine.timezone).date().isoformat(),
            )
            self._accounts[account_key] = state
        return state

    def get_snapshot_sync(
        self,
        platform: str,
        account_id: str | None,
        now: datetime | None = None,
    ) -> RoutineSnapshot:
        """同步返回短耗时快照，供消息门控和 Planner 注入使用。"""

        state = self.ensure_account(platform, account_id)
        current_time = now or self._local_now(state.timezone)
        self._advance_state(state, current_time)
        return self._snapshot_from_state(state, current_time)

    def get_turn_policy_sync(
        self,
        platform: str,
        account_id: str | None,
        *,
        is_group_chat: bool,
        forced: bool,
        now: datetime | None = None,
    ) -> RoutineTurnPolicy:
        """返回日程对当前聊天轮次的影响，不执行等待和发送。"""

        snapshot = self.get_snapshot_sync(platform, account_id, now)
        current = snapshot.current_activity
        label = "空闲"
        multiplier = 0.8
        hint = "状态正常，可以按当前聊天自然回复。"
        if current is not None:
            activity_policy = {
                "sleep": (0.05, "睡眠中", "回复尽量简短，可以表现出刚醒或准备休息。"),
                "meal": (0.3, "用餐中", "回复简短自然，不要展开过多。"),
                "fixed": (0.2, "忙碌中", "优先简洁回应，不承诺固定时间后再回复。"),
                "interest": (0.6, "兴趣活动中", "可以自然提到正在做的事，但不要强行引导话题。"),
            }
            activity_key = current.activity_type
            if current.activity_id == "sleep":
                activity_key = "sleep"
            elif current.activity_id in {"breakfast", "lunch", "dinner"}:
                activity_key = "meal"
            multiplier, label, hint = activity_policy.get(activity_key, (0.8, "活动中", "保持自然交流。"))
        if snapshot.mood.mood >= 80 and label not in {"睡眠中", "用餐中"}:
            multiplier = max(multiplier, 0.95)
            label = "心情不错"
            hint = "可以比平时稍微展开，但不要主动制造话题。"
        elif snapshot.mood.mood <= 35 and label not in {"睡眠中", "用餐中"}:
            multiplier = min(multiplier, 0.4)
            label = "状态偏安静"
            hint = "语气平静、内容收束，避免夸张表达。"
        if not is_group_chat:
            multiplier = max(multiplier, 0.8)
        if forced:
            hint = f"{hint} 当前消息属于强制处理场景，必须先正常处理。"
        multiplier = max(
            global_config.daily_routine.min_reply_multiplier,
            min(global_config.daily_routine.max_reply_multiplier, multiplier),
        )
        return RoutineTurnPolicy(
            multiplier=multiplier,
            status_label=label,
            expression_hint=hint,
            should_deprioritize=not forced and multiplier < 0.25,
        )

    async def build_planner_context(
        self,
        platform: str,
        account_id: str | None,
        topic_text: str = "",
    ) -> str:
        """在线程池读取相关草稿，并构建本轮 Planner 的日程参考。"""

        context = await asyncio.to_thread(self.build_planner_context_sync, platform, account_id)
        state = self.ensure_account(platform, account_id)
        if not topic_text.strip():
            return context
        drafts = await asyncio.to_thread(self._list_drafts_sync, state.account_key, 10)
        normalized_topic = topic_text.strip()
        related = [draft for draft in drafts if self._draft_matches_topic(draft, normalized_topic)]
        if not related:
            return context
        draft = related[0]
        body = draft.body.strip()
        if len(body) > 300:
            body = f"{body[:300]}…"
        return f"{context}\n当前话题可能与一条内部日常草稿有关，仅在自然相关时参考，不要主动提及草稿来源：{body}"

    @staticmethod
    def _draft_matches_topic(draft: DailyRoutineDraft, topic_text: str) -> bool:
        normalized_topic = "".join(topic_text.split())
        if len(normalized_topic) < 4:
            return False
        searchable = f"{draft.title} {draft.body}"
        candidates = (normalized_topic, normalized_topic[:4], normalized_topic[-4:])
        return any(candidate in searchable for candidate in candidates)

    def build_planner_context_sync(self, platform: str, account_id: str | None) -> str:
        """构建只面向表达的 Planner 日程提示，不暴露内部状态数值。"""

        snapshot = self.get_snapshot_sync(platform, account_id)
        activity = snapshot.current_activity.name if snapshot.current_activity else "没有特别安排"
        activity_hint = snapshot.current_activity.activity_type if snapshot.current_activity else "free"
        if snapshot.mood.energy >= 75:
            energy_label = "精力正常"
        elif snapshot.mood.energy <= 35:
            energy_label = "精力偏低"
        else:
            energy_label = "精力一般"
        if snapshot.mood.social_desire >= 75:
            social_label = "比较愿意交流"
        elif snapshot.mood.social_desire <= 35:
            social_label = "社交欲偏低"
        else:
            social_label = "社交欲普通"
        return (
            "日程状态仅作为表达参考，不要求主动引导话题，也不允许主动向群聊发送日程草稿。"
            f"当前时段活动：{activity}（{activity_hint}）；{energy_label}；{social_label}。"
            "如果当前话题无关，请忽略这段信息；如果需要回复，保持自然、简短并符合当前状态。"
        )

    def record_interaction_sync(self, platform: str, account_id: str | None, positive: bool | None = None) -> None:
        """记录聊天互动反馈，供下一次状态推进使用。"""

        state = self.ensure_account(platform, account_id)
        state.last_interaction_at = self._local_now(state.timezone)
        state.interaction_count += 1
        if positive:
            state.positive_interaction_count += 1
            state.mood.mood = min(100, state.mood.mood + 2)
            state.mood.social_desire = min(100, state.mood.social_desire + 2)
        state.last_updated_at = self._local_now(state.timezone)

    async def create_draft(
        self,
        platform: str,
        account_id: str | None,
        *,
        body: str,
        title: str = "",
        draft_type: str = "draft",
        activity_id: str | None = None,
        source_refs: list[dict[str, Any]] | None = None,
        dedupe_key: str,
        expires_at: datetime | None = None,
    ) -> bool:
        """幂等保存一个不发送的日程草稿。"""

        state = self.ensure_account(platform, account_id)
        draft = DailyRoutineDraft(
            draft_id=sha256(f"{state.account_key}:{dedupe_key}".encode("utf-8")).hexdigest()[:64],
            account_key=state.account_key,
            activity_id=activity_id,
            draft_type=draft_type,
            title=title,
            body=body,
            source_refs_json=json.dumps(source_refs or [], ensure_ascii=False),
            dedupe_key=dedupe_key,
            status="draft",
            expires_at=expires_at,
        )
        return await asyncio.to_thread(self._save_draft_sync, draft)

    async def list_drafts(self, platform: str, account_id: str | None, limit: int = 20) -> list[DailyRoutineDraft]:
        """读取账号级未过期日程草稿。"""

        state = self.ensure_account(platform, account_id)
        return await asyncio.to_thread(self._list_drafts_sync, state.account_key, limit)

    def list_drafts_sync(self, platform: str, account_id: str | None, limit: int = 20) -> list[DailyRoutineDraft]:
        """同步读取账号级草稿，供 WebUI 同步端点使用。"""

        state = self.ensure_account(platform, account_id)
        return self._list_drafts_sync(state.account_key, limit)

    def count_drafts_sync(self, platform: str, account_id: str | None, day_key: str) -> int:
        """统计指定日期已生成的草稿数量，保证重启后仍遵守每日预算。"""

        state = self.ensure_account(platform, account_id)
        return self._count_drafts_sync(state.account_key, day_key, state.timezone)

    async def tick(self) -> None:
        """推进状态并持久化，实际数据库操作在线程池中执行。"""

        if not self._loaded:
            return
        for state in self._accounts.values():
            self._advance_state(state, self._local_now(state.timezone))
        await self.persist()

    def all_snapshots(self) -> list[RoutineSnapshot]:
        """返回当前已加载账号的轻量快照，供 WebUI 读取。"""

        return [self.get_snapshot_sync(state.platform, state.account_id) for state in self._accounts.values()]

    @staticmethod
    def _local_now(timezone_name: str) -> datetime:
        return datetime.now(ZoneInfo(timezone_name))

    def _advance_state(self, state: _AccountState, now: datetime) -> None:
        local_now = (
            now.astimezone(ZoneInfo(state.timezone)) if now.tzinfo else now.replace(tzinfo=ZoneInfo(state.timezone))
        )
        day_key = local_now.date().isoformat()
        if state.day_key != day_key:
            state.day_key = day_key
            state.mood = RoutineMood(energy=70, mood=60, social_desire=55, focus=60)
            state.interaction_count = 0
            state.positive_interaction_count = 0
            state.last_sleep_quality = max(50, min(90, state.last_sleep_quality))
            state.activities = []
            state.plan_generated = False
        if not state.plan_generated:
            state.activities = self._generate_plan(state)
            state.plan_generated = True
        last_updated = state.last_updated_at
        if last_updated.tzinfo is None:
            last_updated = last_updated.replace(tzinfo=ZoneInfo(state.timezone))
        elapsed_hours = max(0.0, (local_now - last_updated).total_seconds() / 3600)
        if elapsed_hours > 0:
            current = next(
                (item for item in state.activities if item.scheduled_start <= local_now < item.scheduled_end), None
            )
            if current and current.activity_type == "fixed" and current.activity_id == "sleep":
                state.mood.energy += int(elapsed_hours * 6)
                state.mood.focus += int(elapsed_hours * 3)
            else:
                state.mood.energy -= int(elapsed_hours * 3)
                state.mood.focus -= int(elapsed_hours * 1.5)
            state.mood.clamp()
        state.activities = [
            RoutineActivity(
                activity_id=item.activity_id,
                name=item.name,
                activity_type=item.activity_type,
                scheduled_start=item.scheduled_start,
                scheduled_end=item.scheduled_end,
                status=(
                    "active"
                    if item.scheduled_start <= local_now < item.scheduled_end
                    else "completed"
                    if local_now >= item.scheduled_end
                    else "planned"
                ),
            )
            for item in state.activities
        ]
        state.last_updated_at = local_now

    def _generate_plan(self, state: _AccountState) -> list[RoutineActivity]:
        local_date = date.fromisoformat(state.day_key)
        seed_bytes = f"{state.account_key}:{state.day_key}".encode("utf-8")
        rng = random.Random(int.from_bytes(sha256(seed_bytes).digest()[:8], "big"))
        plan: list[RoutineActivity] = []
        for spec in _ACTIVITY_SPECS:
            probability = (
                global_config.daily_routine.interest_probability
                if spec.activity_type == "interest"
                else spec.probability
            )
            if probability < 1.0 and rng.random() > probability:
                continue
            variance = rng.randint(-spec.variance_minutes, spec.variance_minutes)
            start = datetime.combine(
                local_date,
                time(spec.start_hour, spec.start_minute),
                tzinfo=ZoneInfo(state.timezone),
            ) + timedelta(minutes=variance)
            end = start + timedelta(minutes=spec.duration_minutes)
            plan.append(
                RoutineActivity(
                    activity_id=spec.activity_id,
                    name=spec.name,
                    activity_type=spec.activity_type,
                    scheduled_start=start,
                    scheduled_end=end,
                    status="planned",
                )
            )
        return sorted(plan, key=lambda item: item.scheduled_start)

    @staticmethod
    def _snapshot_from_state(state: _AccountState, now: datetime) -> RoutineSnapshot:
        local_now = (
            now.astimezone(ZoneInfo(state.timezone)) if now.tzinfo else now.replace(tzinfo=ZoneInfo(state.timezone))
        )
        activities = tuple(
            RoutineActivity(
                activity_id=item.activity_id,
                name=item.name,
                activity_type=item.activity_type,
                scheduled_start=item.scheduled_start,
                scheduled_end=item.scheduled_end,
                status=(
                    "active"
                    if item.scheduled_start <= local_now < item.scheduled_end
                    else "completed"
                    if local_now >= item.scheduled_end
                    else "planned"
                ),
            )
            for item in state.activities
        )
        current_activity = next((item for item in activities if item.status == "active"), None)
        return RoutineSnapshot(
            account_key=state.account_key,
            platform=state.platform,
            account_id=state.account_id,
            timezone=state.timezone,
            day_key=state.day_key,
            current_activity=current_activity,
            activities=activities,
            mood=RoutineMood(**asdict(state.mood)),
            interaction_count=state.interaction_count,
            last_sleep_quality=state.last_sleep_quality,
            updated_at=state.last_updated_at,
        )

    @staticmethod
    def _load_states_sync() -> list[DailyRoutineState]:
        with get_db_session(auto_commit=False) as session:
            return list(session.exec(select(DailyRoutineState)).all())

    @staticmethod
    def _persist_sync(
        records: list[DailyRoutineState],
        activities: list[tuple[str, str, RoutineActivity]],
    ) -> None:
        with get_db_session() as session:
            for record in records:
                existing = session.get(DailyRoutineState, record.account_key)
                if existing is None:
                    session.add(record)
                else:
                    existing.platform = record.platform
                    existing.account_id = record.account_id
                    existing.timezone = record.timezone
                    existing.day_key = record.day_key
                    existing.state_json = record.state_json
                    existing.plan_json = record.plan_json
                    existing.last_updated_at = record.last_updated_at
                    existing.last_interaction_at = record.last_interaction_at
                    existing.today_interaction_count = record.today_interaction_count
                    existing.today_positive_interactions = record.today_positive_interactions
                    existing.last_sleep_quality = record.last_sleep_quality
            for account_key, day_key, activity in activities:
                statement = select(DailyRoutineActivity).where(
                    DailyRoutineActivity.account_key == account_key,
                    DailyRoutineActivity.day_key == day_key,
                    DailyRoutineActivity.activity_id == activity.activity_id,
                )
                existing = session.exec(statement).first()
                payload = DailyRoutineActivity(
                    account_key=account_key,
                    day_key=day_key,
                    activity_id=activity.activity_id,
                    name=activity.name,
                    activity_type=activity.activity_type,
                    scheduled_start=activity.scheduled_start,
                    scheduled_end=activity.scheduled_end,
                    status=activity.status,
                )
                if existing is None:
                    session.add(payload)
                else:
                    existing.name = payload.name
                    existing.activity_type = payload.activity_type
                    existing.scheduled_start = payload.scheduled_start
                    existing.scheduled_end = payload.scheduled_end
                    existing.status = payload.status

    @staticmethod
    def _save_draft_sync(draft: DailyRoutineDraft) -> bool:
        with get_db_session() as session:
            statement = select(DailyRoutineDraft).where(
                DailyRoutineDraft.account_key == draft.account_key,
                DailyRoutineDraft.dedupe_key == draft.dedupe_key,
            )
            existing = session.exec(statement).first()
            if existing is not None:
                return False
            session.add(draft)
            return True

    @staticmethod
    def _list_drafts_sync(account_key: str, limit: int) -> list[DailyRoutineDraft]:
        now = datetime.now()
        with get_db_session(auto_commit=False) as session:
            statement = (
                select(DailyRoutineDraft)
                .where(
                    DailyRoutineDraft.account_key == account_key,
                    DailyRoutineDraft.status == "draft",
                    (DailyRoutineDraft.expires_at.is_(None) | (DailyRoutineDraft.expires_at > now)),
                )
                .order_by(desc(DailyRoutineDraft.created_at))
                .limit(max(1, min(limit, 100)))
            )
            return list(session.exec(statement).all())

    @staticmethod
    def _count_drafts_sync(account_key: str, day_key: str, timezone_name: str) -> int:
        timezone = ZoneInfo(timezone_name)
        start = datetime.combine(date.fromisoformat(day_key), time.min, tzinfo=timezone)
        end = start + timedelta(days=1)
        with get_db_session(auto_commit=False) as session:
            statement = (
                select(func.count())
                .select_from(DailyRoutineDraft)
                .where(
                    DailyRoutineDraft.account_key == account_key,
                    DailyRoutineDraft.created_at >= start,
                    DailyRoutineDraft.created_at < end,
                )
            )
            return int(session.exec(statement).one())

    @staticmethod
    def _state_from_record(record: DailyRoutineState) -> _AccountState:
        try:
            raw_state = json.loads(record.state_json or "{}")
            mood = RoutineMood(**{key: raw_state.get(key, value) for key, value in asdict(RoutineMood()).items()})
        except (TypeError, ValueError, json.JSONDecodeError):
            mood = RoutineMood()
        activities: list[RoutineActivity] = []
        try:
            raw_plan = json.loads(record.plan_json or "[]")
            for item in raw_plan:
                activities.append(
                    RoutineActivity(
                        activity_id=str(item["activity_id"]),
                        name=str(item["name"]),
                        activity_type=str(item["activity_type"]),
                        scheduled_start=datetime.fromisoformat(item["scheduled_start"]),
                        scheduled_end=datetime.fromisoformat(item["scheduled_end"]),
                        status=str(item.get("status", "planned")),
                    )
                )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            activities = []
        return _AccountState(
            platform=record.platform,
            account_id=record.account_id or "",
            timezone=record.timezone,
            day_key=record.day_key,
            mood=mood,
            activities=activities,
            last_updated_at=record.last_updated_at,
            last_interaction_at=record.last_interaction_at,
            interaction_count=record.today_interaction_count,
            positive_interaction_count=record.today_positive_interactions,
            last_sleep_quality=record.last_sleep_quality,
            plan_generated=bool(activities),
        )

    @staticmethod
    def _record_from_state(state: _AccountState) -> DailyRoutineState:
        plan_json = json.dumps(
            [
                {
                    "activity_id": item.activity_id,
                    "name": item.name,
                    "activity_type": item.activity_type,
                    "scheduled_start": item.scheduled_start.isoformat(),
                    "scheduled_end": item.scheduled_end.isoformat(),
                    "status": item.status,
                }
                for item in state.activities
            ],
            ensure_ascii=False,
        )
        return DailyRoutineState(
            account_key=state.account_key,
            platform=state.platform,
            account_id=state.account_id or None,
            timezone=state.timezone,
            day_key=state.day_key,
            state_json=json.dumps(asdict(state.mood), ensure_ascii=False),
            plan_json=plan_json,
            last_updated_at=state.last_updated_at,
            last_interaction_at=state.last_interaction_at,
            today_interaction_count=state.interaction_count,
            today_positive_interactions=state.positive_interaction_count,
            last_sleep_quality=state.last_sleep_quality,
        )


_daily_routine_service = DailyRoutineService()


def get_daily_routine_service() -> DailyRoutineService:
    """返回进程内共享的日程服务。"""

    return _daily_routine_service
