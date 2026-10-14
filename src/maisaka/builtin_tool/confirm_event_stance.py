"""确认当前群聊事件的临时立场工具。"""

from typing import Optional

from src.core.tooling import ToolExecutionContext, ToolExecutionResult, ToolInvocation, ToolSpec

from .context import BuiltinToolRuntimeContext


def get_tool_spec() -> ToolSpec:
    """返回事件立场确认工具定义。"""

    return ToolSpec(
        name="confirm_event_stance",
        description=(
            "在群聊事件分析达到可操作完成条件后确认该事件的临时立场；"
            "信息不足时必须使用 neutral，不得为了站队制造确定结论。"
        ),
        parameters_schema={
            "type": "object",
            "properties": {
                "event_id": {"type": "string", "description": "事件内部参考中的 event_id。"},
                "stance_type": {
                    "type": "string",
                    "enum": ["neutral", "support", "oppose", "mixed"],
                },
                "summary": {"type": "string"},
                "reasoning": {"type": "string"},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            },
            "required": ["event_id", "stance_type", "summary", "reasoning", "confidence"],
        },
        provider_name="maisaka_builtin",
        provider_type="builtin",
    )


async def handle_tool(
    tool_ctx: BuiltinToolRuntimeContext,
    invocation: ToolInvocation,
    context: Optional[ToolExecutionContext] = None,
) -> ToolExecutionResult:
    """保存当前群聊事件的统一临时立场。"""

    del context
    from src.services.group_event_service import get_group_event_service

    service = get_group_event_service()
    arguments = invocation.arguments or {}
    event_id = str(arguments.get("event_id") or "").strip()
    trigger_message_id = tool_ctx.runtime.message_cache[-1].message_id if tool_ctx.runtime.message_cache else ""
    contexts = await service.get_contexts_for_source(
        tool_ctx.runtime.session_id,
        str(trigger_message_id or ""),
    )
    event_context = next((context for context in contexts if context.event_id == event_id), None)
    if event_context is None:
        return tool_ctx.build_failure_result(invocation.tool_name, "当前会话没有指定的活跃事件。")
    if event_context.status != "ready_for_stance":
        return tool_ctx.build_failure_result(
            invocation.tool_name,
            f"当前事件状态为 {event_context.status}，尚未进入立场确认阶段。",
        )

    stance_type = str(arguments.get("stance_type") or "neutral").strip()
    summary = str(arguments.get("summary") or "").strip()
    reasoning = str(arguments.get("reasoning") or "").strip()
    try:
        confidence = float(arguments.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    if stance_type != "neutral" and not summary:
        return tool_ctx.build_failure_result(invocation.tool_name, "非 neutral 立场必须提供 summary。")

    saved = await service.confirm_stance(
        event_id=event_id,
        stance_type=stance_type,
        summary=summary or "证据仍不足，暂不形成单方面立场。",
        reasoning=reasoning,
        confidence=confidence,
    )
    if not saved:
        return tool_ctx.build_failure_result(invocation.tool_name, "事件立场保存失败。")
    return tool_ctx.build_success_result(
        invocation.tool_name,
        f"已确认事件 {event_context.event_id} 的临时立场：{stance_type}。",
        structured_content={
            "event_id": event_context.event_id,
            "stance_type": stance_type,
            "summary": summary or "证据仍不足，暂不形成单方面立场。",
            "confidence": max(0.0, min(1.0, confidence)),
        },
    )
