"""日程后台运行时及不发送内容生成器。"""

from datetime import datetime, timedelta
from typing import Any

import asyncio

from src.common.logger import get_logger
from src.config.config import global_config
from src.llm_models.payload_content.context_item import ContextItemBuilder, RoleType
from src.services.daily_routine_service import RoutineSnapshot, get_daily_routine_service
from src.services.llm_service import LLMServiceClient

logger = get_logger("daily_routine_runtime")


_ROUTINE_PROMPTS = {
    "zh_CN": (
        "你是一个日常记录整理器。根据机器人今天的活动状态，写一篇不发送到群聊的短日常草稿。"
        "像社交平台短动态或说说，不要写成聊天回复，不要编造外部事实，不要呼吁用户互动。"
        "只输出正文，控制在 80 到 220 字。"
    ),
    "en_US": (
        "You are a private daily journal composer. Write a short unsent routine draft from the bot's activity state. "
        "It should feel like a social-media short post, not a chat reply. Do not invent external facts or ask users to engage. "
        "Output only the body, between 80 and 220 Chinese characters when the input is Chinese."
    ),
    "ja_JP": (
        "あなたは日常記録の整理役です。ボットの活動状態から、群聊へ送信しない短い日常下書きを作成してください。"
        "会話への返信ではなく、短いソーシャル投稿のようにし、外部事実を捏造せず、ユーザーへの呼びかけも避けてください。本文だけを出力してください。"
    ),
}


class RoutineContentComposer:
    """复用统一 LLM 服务层，但不暴露聊天工具和发送能力。"""

    def __init__(self) -> None:
        self._client = LLMServiceClient(task_name="daily_routine", request_type="daily_routine")

    async def compose(self, snapshot: RoutineSnapshot, *, trigger: str) -> str:
        activity = snapshot.current_activity.name if snapshot.current_activity else "今天的日常"
        prompt = (
            f"日期：{snapshot.day_key}\n"
            f"时区：{snapshot.timezone}\n"
            f"活动：{activity}\n"
            f"触发原因：{trigger}\n"
            "请写一条不发送的内部日常草稿。"
        )

        def build_context(_: Any) -> list[Any]:
            return [
                ContextItemBuilder().set_role(RoleType.System).add_text_content(_ROUTINE_PROMPTS["zh_CN"]).build(),
                ContextItemBuilder().set_role(RoleType.User).add_text_content(prompt).build(),
            ]

        result = await asyncio.wait_for(
            self._client.generate_response_with_context(
                context_factory=build_context,
                options=None,
            ),
            timeout=global_config.daily_routine.generation_timeout_seconds,
        )
        text = result.response.strip()
        if not text:
            raise ValueError("日程内容生成返回空文本")
        return text


class DailyRoutineRuntime:
    """与消息驱动心流并行的日程后台运行时。"""

    def __init__(self) -> None:
        self._service = get_daily_routine_service()
        self._composer = RoutineContentComposer()
        self._task: asyncio.Task[None] | None = None
        self._running = False
        self._last_generation_at: dict[str, datetime] = {}
        self._last_active_activity: dict[str, str | None] = {}
        self._daily_generated_count: dict[str, tuple[str, int]] = {}
        self._generation_semaphore = asyncio.Semaphore(1)
        self._pending_generations: set[str] = set()
        self._generation_tasks: set[asyncio.Task[None]] = set()

    async def start(self) -> None:
        """启动状态服务和后台 tick。"""

        if not global_config.daily_routine.enabled or self._running:
            return
        await self._service.start()
        self._generation_semaphore = asyncio.Semaphore(global_config.daily_routine.max_generation_concurrency)
        self._running = True
        self._task = asyncio.create_task(self._run_loop(), name="daily_routine_runtime")
        logger.info("日程后台运行时已启动: mode=internal-draft-only")

    async def stop(self) -> None:
        """停止后台 tick 并持久化状态。"""

        self._running = False
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None
        for task in self._generation_tasks:
            task.cancel()
        if self._generation_tasks:
            await asyncio.gather(*self._generation_tasks, return_exceptions=True)
        self._generation_tasks.clear()
        await self._service.stop()
        logger.info("日程后台运行时已停止")

    async def _run_loop(self) -> None:
        while self._running:
            try:
                await self._service.tick()
                await self._schedule_generation()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error(f"日程后台 tick 失败: {exc}", exc_info=True)
            await asyncio.sleep(global_config.daily_routine.tick_seconds)

    async def _schedule_generation(self) -> None:
        now = datetime.now().astimezone()
        for snapshot in self._service.all_snapshots():
            previous_activity_id = self._last_active_activity.get(snapshot.account_key)
            current_activity_id = snapshot.current_activity.activity_id if snapshot.current_activity else None
            self._last_active_activity[snapshot.account_key] = current_activity_id
            activity_ended = previous_activity_id is not None and current_activity_id != previous_activity_id
            last_generated = self._last_generation_at.get(snapshot.account_key)
            interval_due = last_generated is None or now - last_generated >= timedelta(
                minutes=global_config.daily_routine.draft_interval_minutes
            )
            if not activity_ended and not interval_due:
                continue
            day_count = self._daily_generated_count.get(snapshot.account_key)
            generated_count = day_count[1] if day_count and day_count[0] == snapshot.day_key else 0
            if not day_count or day_count[0] != snapshot.day_key:
                generated_count = await asyncio.to_thread(
                    self._service.count_drafts_sync,
                    snapshot.platform,
                    snapshot.account_id,
                    snapshot.day_key,
                )
                self._daily_generated_count[snapshot.account_key] = (snapshot.day_key, generated_count)
            if generated_count >= global_config.daily_routine.daily_draft_budget:
                continue
            if snapshot.account_key in self._pending_generations:
                continue
            self._pending_generations.add(snapshot.account_key)
            task = asyncio.create_task(
                self._generate_one(snapshot, "活动结束" if activity_ended else "低频日程检查"),
                name=f"daily_routine_draft:{snapshot.account_key}",
            )
            self._generation_tasks.add(task)
            task.add_done_callback(self._generation_tasks.discard)

    async def _generate_one(self, snapshot: RoutineSnapshot, trigger: str) -> None:
        async with self._generation_semaphore:
            try:
                body = await self._composer.compose(snapshot, trigger=trigger)
                created = await self._service.create_draft(
                    snapshot.platform,
                    snapshot.account_id,
                    body=body,
                    title=snapshot.current_activity.name if snapshot.current_activity else "日常记录",
                    draft_type="experience",
                    activity_id=snapshot.current_activity.activity_id if snapshot.current_activity else None,
                    dedupe_key=f"{snapshot.day_key}:{trigger}:{snapshot.current_activity.activity_id if snapshot.current_activity else 'daily'}",
                    expires_at=datetime.now().astimezone()
                    + timedelta(days=global_config.daily_routine.draft_retention_days),
                )
                self._last_generation_at[snapshot.account_key] = datetime.now().astimezone()
                if created:
                    day_count = self._daily_generated_count.get(snapshot.account_key)
                    current_count = day_count[1] if day_count and day_count[0] == snapshot.day_key else 0
                    self._daily_generated_count[snapshot.account_key] = (snapshot.day_key, current_count + 1)
                    logger.info(f"日程内部草稿已生成: account={snapshot.account_key} trigger={trigger}")
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning(f"日程内部草稿生成失败: account={snapshot.account_key} error={exc}")
            finally:
                self._pending_generations.discard(snapshot.account_key)


_daily_routine_runtime = DailyRoutineRuntime()


def get_daily_routine_runtime() -> DailyRoutineRuntime:
    """返回进程内共享的日程后台运行时。"""

    return _daily_routine_runtime
