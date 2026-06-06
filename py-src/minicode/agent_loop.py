from __future__ import annotations

import concurrent.futures
import inspect
import time
from typing import Any, Callable

from minicode.context_manager import ContextManager, estimate_message_tokens
from minicode.logging_config import get_logger
from minicode.permissions import PermissionManager
from minicode.state import Store, AppState, increment_tool_calls, add_cost, record_api_error, update_context_usage, set_busy, set_idle
from minicode.tooling import ToolContext, ToolRegistry, ToolResult
from minicode.types import AgentStep, ChatMessage, ModelAdapter

# Hooks integration
from minicode.hooks import HookEvent, fire_hook_sync

# Intelligence integration
from minicode.agent_metrics import AgentMetricsCollector
from minicode.agent_intelligence import ErrorClassifier, NudgeGenerator, RecoveryStrategy, ToolScheduler
from minicode.working_memory import protect_context

# Work chain integration
from minicode.intent_parser import parse_intent
from minicode.task_object import build_task, TaskObject, TaskState
from minicode.pipeline_engine import get_pipeline_engine, PipelineEngine
from minicode.capability_registry import get_registry, CapabilityDomain
from minicode.layered_context import ContextBuilder, LayeredContext, ContextLayer
from minicode.decision_audit import get_auditor, DecisionType, DecisionOutcome
from minicode.turn_kernel import (
    AssistantMessageReplay,
    AssistantTurnDecision,
    ToolBatchPlan,
    ToolReplayPlan,
    ToolResultDecision,
    ToolResultReplay,
    ToolStepFeedback,
    apply_tool_step_feedback,
    build_tool_batch_plan,
    build_tool_replay_plan,
    build_tool_result_replay,
    build_assistant_turn_replay,
    build_step_content_replay,
    build_tool_step_feedback,
    build_turn_coda_summary,
    finalize_work_chain_task,
    TurnPreludeState,
    TurnRecurrentState,
    decide_assistant_turn,
)

# 工程控制论集成
from minicode.feedback_controller import FeedbackController, SystemState
from minicode.feedforward_controller import FeedforwardController, PreemptiveConfig
from minicode.stability_monitor import StabilityMonitor, HealthLevel

# 高级控制论模块
from minicode.adaptive_pid_tuner import AdaptivePIDTuner, PIDParameters
from minicode.state_observer import StateObserver, MeasurementVector, ObservedState
from minicode.decoupling_controller import DecouplingController
from minicode.predictive_controller import PredictiveController, PredictionHorizon
from minicode.self_healing_engine import SelfHealingEngine, FaultType, FaultSeverity

# 上下文管理集成 (Claude Code-style + Engineering Cybernetics)
from minicode.context_compactor import (
    ContextCompactor,
    AutoCompactConfig,
    CompactTrigger,
    CompactStrategy,
)
from minicode.context_cybernetics import ContextCyberneticsOrchestrator
from minicode.cost_control import CostControlLoop
from minicode.memory import MemoryManager

logger = get_logger("agent_loop")

# 甯搁噺锛氶伩鍏嶉噸澶嶇殑鎻愮ず鏂囨湰
NUDGE_CONTINUE = (
    "Continue immediately from your <progress> update with concrete tool calls, "
    "code changes, or an explicit <final> answer only if the task is complete."
)

NUDGE_AFTER_TOOL_RESULT = (
    "Continue from your progress update. You have already used tools in this turn, "
    "so treat plain status text as progress, not a final answer. Respond with the "
    "next concrete tool call, code change, or an explicit <final> answer only if "
    "the task is truly complete."
)

NUDGE_AFTER_EMPTY_RESPONSE = (
    "Your last response was empty after recent tool results. Continue immediately "
    "by trying the next concrete step, adapting to any tool errors, or giving an "
    "explicit <final> answer only if the task is complete."
)

NUDGE_AFTER_EMPTY_NO_TOOLS = (
    "Your last response was empty. Continue immediately with concrete tool calls, "
    "code changes, or an explicit <final> answer only if the task is complete."
)

RESUME_AFTER_PAUSE = (
    "Resume from the previous pause and continue immediately with the next concrete "
    "tool call, code change, or an explicit <final> answer only if the task is complete."
)

RESUME_AFTER_MAX_TOKENS = (
    "Your previous response hit max_tokens during thinking before producing the next "
    "actionable step. Resume immediately and continue with the next concrete tool call, "
    "code change, or an explicit <final> answer only if the task is complete."
)


def _is_empty_assistant_response(content: str) -> bool:
    return len(content.strip()) == 0


def _extract_task_description(messages: list[ChatMessage]) -> str:
    """Extract the original task description from messages."""
    for msg in messages:
        if msg.get("role") == "user" and msg.get("content"):
            content = str(msg["content"])
            if not content.startswith("Continue") and not content.startswith("Your last"):
                return content[:500]
    return "Unknown task"


def _build_work_chain_task(messages: list[ChatMessage]) -> tuple[TaskObject | None, dict]:
    """Build TaskObject from conversation messages and return it with metadata."""
    raw_input = _extract_task_description(messages)
    if raw_input == "Unknown task":
        return None, {}
    intent = parse_intent(raw_input)
    task = build_task(intent, raw_input)
    metadata = {
        "intent_type": intent.intent_type.value,
        "action_type": intent.action_type.value,
        "confidence": intent.confidence,
        "entities": intent.entities,
        "complexity": intent.complexity_hint,
    }
    logger.info(
        "Work chain: intent=%s action=%s confidence=%.2f complexity=%s",
        intent.intent_type.value, intent.action_type.value,
        intent.confidence, intent.complexity_hint,
    )
    return task, metadata


def _build_layered_context(
    messages: list[ChatMessage],
    system_prompt: str = "",
    project_context: str = "",
    task: TaskObject | None = None,
) -> tuple[LayeredContext, ContextBuilder]:
    """Build layered context from conversation and task."""
    context = LayeredContext()
    builder = ContextBuilder(context)
    if system_prompt:
        builder.set_system_prompt(system_prompt)
    if project_context:
        builder.add_project_memory(project_context)
    for msg in messages:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        if content:
            builder.add_session_message(role, content)
    if task:
        scratchpad = (
            f"Task: {task.title}\n"
            f"Goal: {task.goal}\n"
            f"Constraints: {len(task.constraints)}\n"
            f"Expected outputs: {len(task.expected_outputs)}"
        )
        builder.add_scratchpad(scratchpad)
    return context, builder


def _register_tool_capabilities(tools: ToolRegistry) -> None:
    """Register existing tools as capabilities in the registry."""
    registry = get_registry()
    if registry.list_all():
        return
    for tool_name in tools.list_all():
        try:
            from minicode.capability_registry import CapabilityMetadata, CapabilityScope
            tool_def = tools.find(tool_name)
            if not tool_def:
                continue
            domain = CapabilityDomain.UNKNOWN
            if "file" in tool_name or "write" in tool_name or "read" in tool_name:
                domain = CapabilityDomain.FILE
            elif "search" in tool_name or "grep" in tool_name:
                domain = CapabilityDomain.SEARCH
            elif "web" in tool_name or "http" in tool_name or "fetch" in tool_name:
                domain = CapabilityDomain.WEB
            elif "command" in tool_name or "run" in tool_name or "exec" in tool_name:
                domain = CapabilityDomain.EXECUTION
            elif "code" in tool_name or "diff" in tool_name or "review" in tool_name:
                domain = CapabilityDomain.CODE
            elif "memory" in tool_name:
                domain = CapabilityDomain.MEMORY
            scope = CapabilityScope.READONLY
            if any(k in tool_name for k in ("write", "modify", "edit", "delete", "create")):
                scope = CapabilityScope.WRITE
            if any(k in tool_name for k in ("command", "exec", "run")):
                scope = CapabilityScope.DESTRUCTIVE
            if any(k in tool_name for k in ("web", "fetch", "http")):
                scope = CapabilityScope.EXTERNAL
            metadata = CapabilityMetadata(
                name=tool_name, domain=domain, scope=scope,
                description=tool_def.description or f"Tool: {tool_name}",
                tags=["tool", tool_name],
            )
            registry.register(metadata, lambda **kw: tools.execute(tool_name, kw, ToolContext()), None)
        except Exception as e:
            logger.debug("Failed to register tool %s as capability: %s", tool_name, e)


def _execute_single_tool(
    call: dict,
    tools: ToolRegistry,
    cwd: str,
    permissions: Any | None,
    runtime: dict | None,
    store: Any | None,
    step: int,
    on_tool_start: Callable[[str, dict], None] | None,
    on_tool_result: Callable[[str, str, bool], None] | None,
) -> ToolResult:
    """Execute a single tool call with state updates, callbacks, and crash protection.
    
    Used both for serial execution and as a worker function for concurrent execution.
    When running concurrently (store/on_tool_start/on_tool_result are None),
    UI callbacks are deferred to the result processing phase.
    
    Includes a global exception safety net: any unexpected crash in the tool
    execution pipeline (hooks, state updates, etc.) is caught and converted
    to an error ToolResult, preventing the entire agent loop from crashing.
    """
    tool_name = call["toolName"]
    tool_input = call["input"]
    
    try:
        # Pre-tool hooks and UI (only for serial execution)
        if on_tool_start:
            on_tool_start(tool_name, tool_input)
        
        if store:
            store.set_state(set_busy(tool_name))
        
        # Execute the tool (ToolRegistry.execute already has its own safety net)
        result = tools.execute(
            tool_name,
            tool_input,
            ToolContext(cwd=cwd, permissions=permissions, _runtime=runtime),
        )
        
        # Post-tool state updates (only for serial execution)
        if store:
            store.set_state(increment_tool_calls())
            store.set_state(set_idle())
        
        if on_tool_result:
            on_tool_result(tool_name, result.output, not result.ok)
        
        return result
    
    except (KeyboardInterrupt, SystemExit):
        # Always propagate these
        raise
    except Exception as exc:  # noqa: BLE001
        # Global safety net: catch ANY unexpected error in the tool execution
        # pipeline (hooks, state updates, permission checks, etc.) and convert
        # it to an error result. This prevents a single tool crash from
        # cascading into a full session failure.
        import traceback
        tb_excerpt = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)[-3:]).strip()
        error_type = type(exc).__name__
        
        logger.error("Tool execution pipeline crashed (%s): %s", error_type, exc)
        
        # Ensure state is reset even on crash
        if store:
            try:
                store.set_state(set_idle())
            except Exception:
                pass
        
        return ToolResult(
            ok=False,
            output=f"[{error_type}] Tool execution pipeline crashed: {exc}\n"
                   f"Traceback:\n{tb_excerpt}"
        )


def _format_diagnostics(stop_reason: str | None, block_types: list[str] | None, ignored_block_types: list[str] | None) -> str:
    parts: list[str] = []
    if stop_reason:
        parts.append(f"stop_reason={stop_reason}")
    if block_types:
        parts.append(f"blocks={','.join(block_types)}")
    if ignored_block_types:
        parts.append(f"ignored={','.join(ignored_block_types)}")
    return f" Diagnostics: {'; '.join(parts)}." if parts else ""


def _is_recoverable_thinking_stop(*, is_empty: bool, stop_reason: str | None, ignored_block_types: list[str] | None) -> bool:
    if not is_empty:
        return False
    if stop_reason not in {"pause_turn", "max_tokens"}:
        return False
    return "thinking" in (ignored_block_types or [])


def _should_treat_assistant_as_progress(*, kind: str | None, content: str, saw_tool_result: bool) -> bool:
    if kind == "progress":
        return True
    if kind == "final":
        return False
    if not saw_tool_result:
        return False
    return False


def _model_next(
    model: ModelAdapter,
    messages: list[ChatMessage],
    *,
    on_stream_chunk: Callable[[str], None] | None,
    store: Store[AppState] | None,
) -> AgentStep:
    """Call provider adapters with store support while preserving test doubles."""
    if store is None:
        return model.next(messages, on_stream_chunk=on_stream_chunk)

    try:
        signature = inspect.signature(model.next)
    except (TypeError, ValueError):
        return model.next(messages, on_stream_chunk=on_stream_chunk, store=store)

    supports_store = any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD or parameter.name == "store"
        for parameter in signature.parameters.values()
    )
    if supports_store:
        return model.next(messages, on_stream_chunk=on_stream_chunk, store=store)
    return model.next(messages, on_stream_chunk=on_stream_chunk)


def run_agent_turn(
    *,
    model: ModelAdapter,
    tools: ToolRegistry,
    messages: list[ChatMessage],
    cwd: str,
    permissions: PermissionManager | None = None,
    store: Store[AppState] | None = None,
    max_steps: int = 50,
    on_tool_start: Callable[[str, dict], None] | None = None,
    on_tool_result: Callable[[str, str, bool], None] | None = None,
    on_assistant_message: Callable[[str], None] | None = None,
    on_progress_message: Callable[[str], None] | None = None,
    on_assistant_stream_chunk: Callable[[str], None] | None = None,
    context_manager: ContextManager | None = None,
    runtime: dict | None = None,
    metrics_collector: AgentMetricsCollector | None = None,
    system_prompt: str = "",
    project_context: str = "",
    enable_work_chain: bool = True,
) -> list[ChatMessage]:
    current_messages = list(messages)
    turn_state = TurnRecurrentState(max_steps=max_steps)

    tool_scheduler = ToolScheduler(metrics_collector=metrics_collector)

    # Prelude: initialize once-per-turn work chain artifacts.
    prelude = TurnPreludeState(auditor=get_auditor() if enable_work_chain else None)
    pipeline_engine: PipelineEngine | None = None

    # 工程控制论控制器初始化
    feedback_controller: FeedbackController | None = None
    feedforward_controller: FeedforwardController | None = None
    stability_monitor: StabilityMonitor | None = None

    # 高级控制论模块
    adaptive_pid_tuner: AdaptivePIDTuner | None = None
    state_observer: StateObserver | None = None
    decoupling_controller: DecouplingController | None = None
    predictive_controller: PredictiveController | None = None
    self_healing_engine: SelfHealingEngine | None = None

    if enable_work_chain:
        prelude.task, prelude.task_metadata = _build_work_chain_task(current_messages)
        prelude.layered_context, prelude.context_builder = _build_layered_context(
            current_messages, system_prompt, project_context, prelude.task,
        )
        pipeline_engine = get_pipeline_engine()
        _register_tool_capabilities(tools)

        # 初始化反馈控制器（负反馈 + 正反馈）
        feedback_controller = FeedbackController()
        logger.info("Feedback controller initialized: negative + positive feedback loops")

        # 初始化前馈控制器（预判式优化）
        if prelude.task:
            feedforward_controller = FeedforwardController()
            preemptive_config = feedforward_controller.preconfigure(
                prelude.task.parsed_intent, prelude.task.raw_input
            )
            risk_assessment = feedforward_controller.assess_risks(
                prelude.task.parsed_intent, preemptive_config
            )
            logger.info(
                "Feedforward control: config=%s risk=%s",
                preemptive_config.recommended_model, risk_assessment.risk_level,
            )

        # 初始化稳定性监测器（系统观测器）
        stability_monitor = StabilityMonitor(window_size=100)
        logger.info("Stability monitor initialized: real-time health tracking")

        # 初始化自适应PID调参器
        adaptive_pid_tuner = AdaptivePIDTuner()
        logger.info("Adaptive PID tuner initialized: self-tuning control")

        # 初始化状态观测器（卡尔曼滤波）
        state_observer = StateObserver()
        logger.info("State observer initialized: Kalman filter-based estimation")

        # 初始化多变量解耦控制器
        decoupling_controller = DecouplingController()
        logger.info("Decoupling controller initialized: multi-variable control")

        # 初始化预测控制器
        predictive_controller = PredictiveController()
        logger.info("Predictive controller initialized: proactive control")

        # 初始化上下文管理器 (Claude Code-style + Engineering Cybernetics)
        # 必须在 SelfHealingEngine 之前初始化，因为自愈引擎需要委托压缩操作
        context_compactor: ContextCompactor | None = None
        context_cybernetics: ContextCyberneticsOrchestrator | None = None
        if context_manager:
            compact_config = AutoCompactConfig(
                threshold_ratio=0.85,
                circuit_breaker_limit=3,
                session_memory_enabled=True,
            )
            memory_mgr = MemoryManager(project_root=cwd)
            context_compactor = ContextCompactor(
                context_window=context_manager.context_window,
                workspace=cwd,
                memory_manager=memory_mgr,
                estimate_fn=estimate_message_tokens,
                config=compact_config,
            )
            context_cybernetics = ContextCyberneticsOrchestrator(
                context_compactor,
                kp=2.0, ki=0.15, kd=0.3,
                pid_setpoint=0.70,
                base_threshold=0.85,
                safety_margin_turns=3,
                enabled=True,
            )
            if task and hasattr(task, 'parsed_intent') and task.parsed_intent:
                context_cybernetics.set_intent(str(task.parsed_intent.intent_type))
            logger.info("ContextCybernetics initialized: PID control loop + predictive guard")

        # 初始化自愈引擎（接收 cybernetics 引用用于 CONTEXT_OVERFLOW 委托）
        self_healing_engine = SelfHealingEngine(orchestrator=context_cybernetics)
        logger.info("Self-healing engine initialized: automated recovery + compaction delegation")

        # 初始化成本控制闭环 (CostTracker → PID → ToolResultBudgetManager)
        cost_control = CostControlLoop(
            target_cost_per_min=0.50,
            kp=1.5, ki=0.08, kd=0.2,
            enabled=True,
        )
        logger.info("CostControlLoop initialized: BudgetPIDController for cost regulation")

    # 检查上下文状态 + 运行 Claude Code-style 预请求优化管线
    if context_manager:
        context_manager.messages = current_messages
        stats = context_manager.get_stats()
        logger.info("Context: %d tokens (%.0f%%), %d messages",
                   stats.total_tokens, stats.usage_percentage, stats.messages_count)

        # 运行控制论闭环优化管线 (Sense → Predict → Control → Act → Learn)
        if context_cybernetics:
            if cost_control and context_compactor:
                est_cost = stats.total_tokens * 0.000015
                adj = cost_control.run(
                    cost_usd=est_cost,
                    total_tokens=stats.total_tokens,
                    total_calls=max(turn_state.step, 1),
                )
                if context_compactor._tool_budget:
                    cost_control.apply_to_budget_manager(context_compactor._tool_budget)

            cyber_messages, cyber_result, cyber_action = context_cybernetics.run_cycle(
                current_messages,
                error_rate=(
                    float(turn_state.tool_error_count) / max(turn_state.step, 1)
                    if turn_state.step > 0
                    else 0.0
                ),
                avg_latency=turn_state.step * 2.0,
                turn_id=turn_state.step,
            )
            if cyber_result and cyber_result.effective:
                current_messages = cyber_messages
                context_manager.messages = current_messages
                logger.info(
                    "Cybernetics[%s]: %s intensity=%.2f freed=%d tokens [%s]",
                    cyber_action.reason if cyber_action else "unknown",
                    cyber_result.strategy.value,
                    cyber_action.compaction_intensity if cyber_action else 0,
                    cyber_result.tokens_freed,
                    cyber_result.summary_text[:80] if cyber_result.summary_text else "",
                )
        elif context_compactor:
            compaction_result = context_compactor.process_request(current_messages)
            if compaction_result.effective:
                current_messages = compaction_result.messages
                context_manager.messages = current_messages
                logger.info(
                    "ContextCompactor: %s freed %d tokens [%s]",
                    compaction_result.strategy.value,
                    compaction_result.tokens_freed,
                    compaction_result.summary_text[:80],
                )
        elif context_manager.should_auto_compact():
            logger.warning("Context near limit, auto-compacting...")
            current_messages = context_manager.compact_messages()
            if on_assistant_message:
                on_assistant_message(context_manager.get_context_summary())

    try:
        while turn_state.has_remaining_steps():
            step = turn_state.begin_step()

            # Hook: agent turn started
            fire_hook_sync(HookEvent.AGENT_START, step=step, cwd=cwd)

            # 高级控制论闭环（每个 step 开始时执行）
            if enable_work_chain:
                # 状态观测：通过可测量输出估计系统内部状态
                if state_observer:
                    measurement = MeasurementVector(
                        timestamp=time.time(),
                        response_time=step * 2.0,  # 估算响应时间
                        success_rate=1.0 - (turn_state.tool_error_count / max(step, 1)),
                        context_length=context_manager.get_stats().total_tokens if context_manager else 0,
                        error_count=turn_state.tool_error_count,
                        tool_calls=0,
                    )
                    observed_state = state_observer.update(measurement)

                # 预测控制：预测未来趋势并提前调整
                if predictive_controller:
                    if context_manager:
                        stats = context_manager.get_stats()
                        predictive_controller.update("context_usage", stats.usage_percentage / 100.0)
                    predictive_controller.update(
                        "error_rate", turn_state.tool_error_count / max(step, 1)
                    )

                    if step > 2:
                        actions = predictive_controller.generate_predictive_actions()
                        if actions and actions[0].urgency > 0.7:
                            logger.info("Predictive action triggered: %s", actions[0].recommended_action)
                            if self_healing_engine:
                                healing_actions = self_healing_engine.detect_and_heal({
                                    "context_usage": stats.usage_percentage / 100.0 if context_manager else 0.0,
                                    "error_rate": turn_state.tool_error_count / max(step, 1),
                                })
                                if healing_actions:
                                    logger.info("Self-healing: %s", healing_actions[0].strategy)

            if metrics_collector:
                metrics_collector.start_turn(step)

            next_step: AgentStep
            try:
                next_step = _model_next(
                    model,
                    current_messages,
                    on_stream_chunk=on_assistant_stream_chunk,
                    store=store,
                )
            except KeyboardInterrupt:
                raise  # Let Ctrl-C propagate
            except ConnectionError as error:
                fallback = f"Network error (connection failed or dropped): {error}"
                logger.error("Model API connection error: %s", error)
                if on_assistant_message:
                    on_assistant_message(fallback)
                current_messages.append({"role": "assistant", "content": fallback})
                if metrics_collector:
                    metrics_collector.end_turn(total_tokens=0)
                return current_messages
            except TimeoutError as error:
                fallback = f"Model API timeout: {error}"
                logger.error("Model API timeout: %s", error)
                if on_assistant_message:
                    on_assistant_message(fallback)
                current_messages.append({"role": "assistant", "content": fallback})
                if metrics_collector:
                    metrics_collector.end_turn(total_tokens=0)
                return current_messages
            except Exception as error:
                # Catch-all for unexpected errors (rate limit, auth, server 5xx, etc.)
                error_type = type(error).__name__
                fallback = f"Model API error ({error_type}): {error}"
                logger.error("Model API error (%s): %s", error_type, error)

                # Reactive Compact: 控制论恢复路径
                error_str = str(error).lower()
                needs_recovery = "prompt" in error_str and ("too long" in error_str or "exceeds" in error_str)
                if context_cybernetics and needs_recovery:
                    recovered_messages, recovery_result = context_cybernetics.try_reactive_recover(current_messages, error_str)
                    if recovery_result and recovery_result.effective:
                        current_messages = recovered_messages
                        if context_manager:
                            context_manager.messages = current_messages
                        logger.info(
                            "Cybernetics Reactive recovered: freed %d tokens",
                            recovery_result.tokens_freed,
                        )
                        continue
                elif context_compactor and needs_recovery:
                    recovery_result = context_compactor.reactive_recover(current_messages, error_str)
                    if recovery_result and recovery_result.effective:
                        current_messages = recovery_result.messages
                        if context_manager:
                            context_manager.messages = current_messages
                        logger.info(
                            "Reactive Compact recovered: freed %d tokens",
                            recovery_result.tokens_freed,
                        )
                        continue

                if on_assistant_message:
                    on_assistant_message(fallback)
                current_messages.append({"role": "assistant", "content": fallback})
                if metrics_collector:
                    metrics_collector.end_turn(total_tokens=0)
                return current_messages

            if next_step.type == "assistant":
                is_empty = _is_empty_assistant_response(next_step.content)
                diagnostics = next_step.diagnostics
                decision: AssistantTurnDecision = decide_assistant_turn(
                    turn_state=turn_state,
                    step_content=next_step.content,
                    step_kind=getattr(next_step, "kind", None),
                    stop_reason=diagnostics.stopReason if diagnostics else None,
                    block_types=diagnostics.blockTypes if diagnostics else None,
                    ignored_block_types=diagnostics.ignoredBlockTypes if diagnostics else None,
                    is_empty=is_empty,
                    treat_as_progress=(
                        not is_empty
                        and _should_treat_assistant_as_progress(
                            kind=getattr(next_step, "kind", None),
                            content=next_step.content,
                            saw_tool_result=turn_state.saw_tool_result,
                        )
                    ),
                    is_recoverable_thinking_stop=_is_recoverable_thinking_stop(
                        is_empty=is_empty,
                        stop_reason=diagnostics.stopReason if diagnostics else None,
                        ignored_block_types=diagnostics.ignoredBlockTypes if diagnostics else None,
                    ),
                    format_diagnostics=_format_diagnostics,
                    nudge_continue=NUDGE_CONTINUE,
                    nudge_after_tool_result=NUDGE_AFTER_TOOL_RESULT,
                    resume_after_pause=RESUME_AFTER_PAUSE,
                    resume_after_max_tokens=RESUME_AFTER_MAX_TOKENS,
                    nudge_after_empty_response=NUDGE_AFTER_EMPTY_RESPONSE,
                    nudge_after_empty_no_tools=NUDGE_AFTER_EMPTY_NO_TOOLS,
                )

                assistant_replay: AssistantMessageReplay = build_assistant_turn_replay(
                    decision=decision
                )
                if assistant_replay.callback_kind == "progress" and on_progress_message and assistant_replay.callback_content:
                    on_progress_message(assistant_replay.callback_content)
                elif assistant_replay.callback_kind == "assistant" and on_assistant_message and assistant_replay.callback_content:
                    on_assistant_message(assistant_replay.callback_content)

                current_messages.extend(assistant_replay.transcript_messages)
                if not assistant_replay.should_return:
                    continue

                # Protect final answer in working memory
                if assistant_replay.protect_final_answer and assistant_replay.callback_content:
                    protect_context(
                        content=assistant_replay.callback_content[:500],
                        entry_type="key_decision",
                        ttl_seconds=3600,
                    )
                return current_messages

            if next_step.content:
                step_content_replay: AssistantMessageReplay = build_step_content_replay(
                    content=next_step.content,
                    content_kind=next_step.contentKind,
                    has_calls=bool(next_step.calls),
                    nudge_continue=NUDGE_CONTINUE,
                )
                if step_content_replay.callback_kind == "progress":
                    if on_progress_message and step_content_replay.callback_content:
                        on_progress_message(step_content_replay.callback_content)
                elif step_content_replay.callback_kind == "assistant":
                    if on_assistant_message and step_content_replay.callback_content:
                        on_assistant_message(step_content_replay.callback_content)
                current_messages.extend(step_content_replay.transcript_messages)
                if step_content_replay.should_return:
                    return current_messages

            # --- Concurrent tool execution ---
            # Classify calls into concurrent-safe (read-only) vs serial (writes/commands)
            calls = next_step.calls
            _results: list[tuple[dict, ToolResult]] = []

            if len(calls) <= 1:
                # Single call — no benefit from concurrency, run directly
                call = calls[0]
                fire_hook_sync(
                    HookEvent.PRE_TOOL_USE,
                    tool_name=call["toolName"],
                    tool_input=call["input"],
                    step=step,
                )
                if metrics_collector:
                    metrics_collector.start_tool(call["toolName"])
                result = _execute_single_tool(
                    call, tools, cwd, permissions, runtime, store, step,
                    on_tool_start, on_tool_result,
                )
                if metrics_collector:
                    metrics_collector.end_tool(
                        success=result.ok,
                        error=result.output if not result.ok else "",
                    )
                _results.append((call, result))
            else:
                # Multiple calls — use ToolScheduler for intelligent partitioning
                concurrent_calls, serial_calls = tool_scheduler.schedule_calls(calls, tools)
                batch_plan: ToolBatchPlan = build_tool_batch_plan(
                    calls=calls,
                    concurrent_calls=concurrent_calls,
                    serial_calls=serial_calls,
                    get_recommended_max_workers=tool_scheduler.get_recommended_max_workers,
                )

                _results: list[tuple[dict, ToolResult]] = []

                # Phase 1: Run all concurrent-safe tools in parallel
                if batch_plan.concurrent_calls:
                    for call in batch_plan.concurrent_calls:
                        if on_tool_start:
                            on_tool_start(call["toolName"], call["input"])
                        fire_hook_sync(
                            HookEvent.PRE_TOOL_USE,
                            tool_name=call["toolName"],
                            tool_input=call["input"],
                            step=step,
                        )
                    with concurrent.futures.ThreadPoolExecutor(
                        max_workers=batch_plan.max_workers,
                        thread_name_prefix="mc-tool",
                    ) as pool:
                        future_to_call = {
                            pool.submit(
                                _execute_single_tool,
                                call, tools, cwd, permissions, runtime, None, step,
                                None, None,  # No UI callbacks during concurrent phase
                            ): call
                            for call in batch_plan.concurrent_calls
                        }
                        for future in concurrent.futures.as_completed(future_to_call):
                            call = future_to_call[future]
                            try:
                                result = future.result()
                            except Exception as exc:
                                result = ToolResult(ok=False, output=f"Concurrent execution error: {exc}")
                            _results.append((call, result))

                # Phase 2: Run serial tools sequentially (in original order)
                if batch_plan.serial_calls:
                    for call in batch_plan.serial_calls:
                        fire_hook_sync(
                            HookEvent.PRE_TOOL_USE,
                            tool_name=call["toolName"],
                            tool_input=call["input"],
                            step=step,
                        )
                        if metrics_collector:
                            metrics_collector.start_tool(call["toolName"])
                        result = _execute_single_tool(
                            call, tools, cwd, permissions, runtime, store, step,
                            on_tool_start, on_tool_result,
                        )
                        if metrics_collector:
                            metrics_collector.end_tool(
                                success=result.ok,
                                error=result.output if not result.ok else "",
                            )
                        _results.append((call, result))
                        # If a serial tool awaits user, return immediately
                        if result.awaitUser:
                            # Still need to process remaining results for messages
                            break
            
            replay_plan: ToolReplayPlan = build_tool_replay_plan(
                calls=calls,
                all_results=_results,
                is_concurrency_safe=lambda tool_name: bool(
                    (tool_def := tools.find(tool_name)) and tool_def.is_concurrency_safe
                ),
            )

            await_user_assistant_content: str | None = None
            for call, result in replay_plan.ordered_results:
                # Fire hooks and UI callbacks for concurrent calls (deferred)
                tool_def = tools.find(call["toolName"])
                # Hook: post-tool-use
                fire_hook_sync(
                    HookEvent.POST_TOOL_USE,
                    tool_name=call["toolName"],
                    tool_output=result.output,
                    is_error=not result.ok,
                    step=step,
                )

                tool_replay: ToolResultReplay = build_tool_result_replay(
                    call=call,
                    result=result,
                    turn_state=turn_state,
                    total_call_count=len(calls),
                    is_concurrency_safe=bool(tool_def and tool_def.is_concurrency_safe),
                    all_results=_results,
                    dedup_manager=(
                        context_compactor.read_dedup
                        if context_compactor
                        else None
                    ),
                    message_index=len(current_messages),
                    classify_error=lambda output, tool_name: ErrorClassifier.classify(
                        output,
                        tool_name=tool_name,
                    ),
                    generate_nudge=lambda classified, retry_count: NudgeGenerator.generate(
                        classified,
                        retry_count=retry_count,
                    ),
                    log_dedup=lambda file_path: logger.debug(
                        "ReadDedup replaced content for %s (stub)",
                        file_path,
                    ),
                )

                if tool_replay.should_emit_callback:
                    if on_tool_result:
                        on_tool_result(
                            call["toolName"],
                            tool_replay.callback_output,
                            not result.ok,
                        )
                    if store and tool_replay.should_increment_tool_calls:
                        store.set_state(increment_tool_calls())

                # Record conflicts between concurrent tools if both failed
                for conflicting_tool_name in tool_replay.conflicting_tool_names:
                    tool_scheduler.record_conflict(
                        call["toolName"],
                        conflicting_tool_name,
                    )

                # ReadDedup: 去重相同文件的重复读取，节省上下文空间
                tool_decision: ToolResultDecision = tool_replay.tool_decision
                current_messages.extend(tool_decision.transcript_messages)
                if tool_decision.should_return and await_user_assistant_content is None:
                    await_user_assistant_content = tool_decision.assistant_content

            if await_user_assistant_content is not None:
                if on_assistant_message:
                    on_assistant_message(await_user_assistant_content)
                current_messages.append(
                    {"role": "assistant", "content": await_user_assistant_content}
                )
                if metrics_collector:
                    metrics_collector.end_turn(total_tokens=0)
                return current_messages

            # 工具执行完成后的控制论反馈
            if enable_work_chain:
                # 多变量解耦：消除工具间的耦合影响
                step_feedback: ToolStepFeedback = build_tool_step_feedback(
                    turn_state=turn_state,
                    context_usage=(
                        context_manager.get_stats().usage_percentage / 100.0
                        if context_manager
                        else 0.0
                    ),
                    oscillation_index=(
                        feedback_controller._compute_oscillation()
                        if feedback_controller
                        else 0.0
                    ),
                )

                # 自愈检测：检测并修复故障
                apply_tool_step_feedback(
                    feedback=step_feedback,
                    decoupling_controller=decoupling_controller,
                    self_healing_engine=self_healing_engine,
                    log_healing=lambda strategy: logger.info(
                        "Self-healing triggered: %s", strategy
                    ),
                )

            # Tool execution completed for this step; ask the model for the next turn
            # instead of falling through to the max-step fallback.
            if metrics_collector:
                total_tokens = sum(
                    estimate_message_tokens(m) for m in current_messages
                ) if context_manager else 0
                metrics_collector.end_turn(total_tokens=total_tokens)
            continue

        fallback = "Reached the maximum tool step limit for this turn."
        if on_assistant_message:
            on_assistant_message(fallback)
        current_messages.append({"role": "assistant", "content": fallback})
        return current_messages
    finally:
        # Coda: finalize metrics, work-chain bookkeeping, and control summaries.
        fire_hook_sync(
            HookEvent.AGENT_STOP,
            step=turn_state.step,
            tool_errors=turn_state.tool_error_count,
        )
        task = prelude.task
        task_metadata = prelude.task_metadata
        auditor = prelude.auditor
        coda_summary = build_turn_coda_summary(
            turn_state=turn_state,
            context_usage=(
                context_manager.get_stats().usage_percentage
                if context_manager
                else 0.0
            ),
        )

        if metrics_collector and metrics_collector._current_turn is not None:
            total_tokens = sum(
                estimate_message_tokens(m) for m in current_messages
            ) if context_manager else 0
            metrics_collector.end_turn(total_tokens=total_tokens)

        if enable_work_chain and task:
            finalize_work_chain_task(
                task=task,
                auditor=auditor,
                coda_summary=coda_summary,
                success_outcome=DecisionOutcome.SUCCESS,
                failure_outcome=DecisionOutcome.FAILURE,
            )

            logger.info(
                "Work chain completed: task=%s state=%s steps=%d errors=%d",
                task.id,
                task.state.value,
                coda_summary.step,
                coda_summary.tool_error_count,
            )

        # 控制论反馈：记录模式有效性
        if enable_work_chain and feedback_controller and task:
            pattern_id = f"{task_metadata.get('intent_type', 'unknown')}_{task.id}"
            feedback_controller.record_pattern_effectiveness(
                pattern_id, coda_summary.success
            )

        # 稳定性监测：记录快照
        if stability_monitor:
            from minicode.stability_monitor import MetricSnapshot
            snapshot = MetricSnapshot(
                timestamp=time.time(),
                error_rate=coda_summary.error_rate,
                avg_latency=coda_summary.avg_latency,  # 简化估算
                context_usage=coda_summary.context_usage,
                active_tasks=1,
            )
            stability_monitor.record_snapshot(snapshot)
            if context_cybernetics:
                stability_monitor.feed_orchestrator(context_cybernetics)

        # 高级控制论：最终状态报告
        if enable_work_chain:
            # 状态观测器报告
            if state_observer:
                state_summary = state_observer.get_state_summary()
                logger.info("State observer summary: %s", state_summary)

            # 预测控制器报告
            if predictive_controller:
                pred_summary = predictive_controller.get_prediction_summary()
                logger.info("Prediction summary: accuracy=%s", pred_summary.get("accuracy", {}))

            # 自愈引擎统计
            if self_healing_engine:
                healing_stats = self_healing_engine.get_healing_statistics()
                logger.info("Self-healing stats: %s", healing_stats)

            # 多变量解耦状态
            if decoupling_controller:
                coupling_status = decoupling_controller.get_coupling_status()
                logger.info("Coupling status: strong=%s", coupling_status.get("strong_couplings", []))

        # 上下文管理管线统计 (Claude Code-style + Cybernetics)
        if context_compactor:
            compactor_stats = context_compactor.get_stats()
            logger.info(
                "ContextCompactor: passes=%d persisted=%d dedup=%d "
                "microcompact=%d boundaries=%d circuit=%s",
                compactor_stats["total_passes"],
                compactor_stats["tool_results_persisted"],
                compactor_stats["read_dedup_entries"],
                compactor_stats["microcompact_tokens_cleared"],
                compactor_stats["auto_compact_boundaries"],
                "TRIPPED" if compactor_stats["circuit_breaker_tripped"] else "OK",
            )
        # 控制论闭环统计 (Engineering Cybernetics)
        if context_cybernetics:
            cyber_stats = context_cybernetics.get_stats()
            logger.info(
                "Cybernetics: cycles=%d usage=%.1f%% pid_out=%.2f "
                "predict_overflow=%s urgency=%.2f threshold=%.2f feedback_eff=%.0f%%",
                cyber_stats["cycles_executed"],
                (cyber_stats["sensor"]["current_usage"] or 0) * 100,
                cyber_stats["pid"]["last_output"] or 0,
                cyber_stats["predictor"]["turns_until_overflow"],
                cyber_stats["predictor"]["urgency"] or 0,
                cyber_stats["threshold"]["effective_threshold"] or 0,
                (cyber_stats["feedback"]["effectiveness_rate"] or 0) * 100,
            )
        # 成本控制闭环统计 (BudgetPIDController)
        if cost_control:
            cc_stats = cost_control.get_stats()
            adj = cc_stats.get("adjustment")
            logger.info(
                "CostControl: cycles=%d cost/min=$%.4f pid_out=%.2f "
                "budget_mult=%.2f threshold_mult=%.2f [%s]",
                cc_stats["cycles_executed"],
                cc_stats["sensor"]["cost_per_min"],
                cc_stats["pid"]["last_output"] or 1.0,
                adj["budget_mult"] if adj else 1.0,
                adj["threshold_mult"] if adj else 1.0,
                adj["reason"] if adj else "none",
            )
        # 双层 PID 闭环: Cybernetics → FeedbackController
        if context_cybernetics and feedback_controller:
            system_state = context_cybernetics.to_system_state()
            control_signal = feedback_controller.observe(system_state)
            if control_signal.force_compaction and context_cybernetics.enabled:
                logger.info(
                    "Dual-PID: FeedbackController force_compaction=True, "
                    "stability=%.2f performance=%.2f",
                    system_state.stability_score(),
                    system_state.performance_score(),
                )


