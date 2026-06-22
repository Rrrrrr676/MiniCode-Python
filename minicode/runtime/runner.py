from __future__ import annotations

import concurrent.futures
import time
from typing import Any, Callable

from minicode.context.tokens import estimate_message_tokens
from minicode.context.manager import ContextManager
from minicode.observability.logging import get_logger
from minicode.safety.permissions import PermissionManager
from minicode.core.state import Store, AppState, increment_tool_calls, set_busy, set_idle
from minicode.tooling import ToolContext, ToolRegistry, ToolResult
from minicode.core.types import (
    AgentStep,
    ChatMessage,
    ModelAdapter,
    RuntimeEvent,
    RuntimeEventCategory,
)

# Hooks integration
from minicode.integrations.hooks import HookEvent, fire_hook_sync

# Intelligence integration
from minicode.observability.metrics import AgentMetricsCollector
from minicode.runtime.intelligence import ErrorClassifier, NudgeGenerator, ToolScheduler
from minicode.context.working import get_working_memory, protect_context

# Work chain integration
from minicode.runtime.intent import parse_intent
from minicode.runtime.tasks.object import build_task, TaskObject, TaskState
from minicode.runtime.tasks.graph import TaskGraph, TaskState as GraphTaskState
from minicode.runtime.pipeline import get_pipeline_engine
from minicode.runtime.capabilities import get_registry, CapabilityDomain
from minicode.context.layered import ContextBuilder, LayeredContext
from minicode.observability.decision_audit import get_auditor, DecisionOutcome
from minicode.runtime.profiles import resolve_runtime_profile

# 工程控制论集成
from minicode.control.orchestrator import CyberneticOrchestrator
from minicode.control.supervisor import save_supervisor_report
from minicode.control.feedforward import FeedforwardController

# 高级控制论模块
from minicode.control.state_observer import MeasurementVector
from minicode.control.recovery import SelfHealingEngine

# 任务进度控制
from minicode.control.progress import ProgressSignal, ProgressAction

# 记忆注入和模型选择控制
from minicode.memory.injector import MemoryInjectionSignal, MemoryInjector
from minicode.providers.registry import ModelSelectionSignal

# 智能路由与自省 (Phase 3 导入)
from minicode.runtime.smart_routing import SmartRouter, TaskOutcome
from minicode.memory.reflection import ReflectionEngine

# 上下文管理集成 (Claude Code-style + Engineering Cybernetics)
from minicode.context.compaction import (
    ContextCompactor,
    AutoCompactConfig,
)
from minicode.control.context import ContextCyberneticsOrchestrator
from minicode.control.cost import CostControlLoop
from minicode.context.compaction.micro_legacy import MicroCompactor
from minicode.context.compaction.circuit_breaker import CompactionCircuitBreaker
from minicode.memory import MemoryManager
from minicode.runtime.kernel import (
    TurnPreludeState,
    TurnRecurrentState,
    TurnVerificationState,
    build_stable_task_pack,
    build_turn_coda_summary,
    build_widening_transition_nudge,
    decide_tool_turn,
    decide_assistant_turn,
    derive_turn_step_policy,
    finalize_work_chain_task,
    render_turn_policy_message,
)
from minicode.runtime.lifecycle import (
    upsert_stable_task_state_message as _upsert_stable_task_state_message,
)
from minicode.runtime.model_execution import (
    format_diagnostics as _format_diagnostics,
    infer_active_model_id as _infer_active_model_id,
    is_empty_assistant_response as _is_empty_assistant_response,
    is_recoverable_thinking_stop as _is_recoverable_thinking_stop,
    model_next as _model_next,
    should_attempt_model_fallback as _should_attempt_model_fallback,
    should_treat_assistant_as_progress as _should_treat_assistant_as_progress,
    summarize_model_api_failure as _summarize_model_api_failure,
)
from minicode.runtime.policy import is_at_blocking_limit as _is_at_blocking_limit
from minicode.runtime.tool_execution import execute_single_tool as _execute_single_tool

from minicode.runtime.prelude import (
    _build_layered_context,
    _build_work_chain_task,
    _register_tool_capabilities,
)
from minicode.runtime.control_runtime import _apply_control_signal

from minicode.runtime.coda import finalize_turn_coda

from minicode.runtime.composition import compose_runtime

logger = get_logger("runtime.runner")

# 甯搁噺锛氶伩鍏嶉噸澶嶇殑鎻愮ず鏂囨湰
NUDGE_CONTINUE = (
    "Continue immediately from your <progress> update with concrete tool calls, "
    "code changes, or an explicit <final> answer only if the task is complete. "
    "Prefer taking the next concrete action over explaining what you plan to do."
)

NUDGE_AFTER_TOOL_RESULT = (
    "You have received tool results. Review them briefly, then take the next "
    "concrete action: call another tool, edit code, or give an explicit <final> "
    "answer only if the task is truly complete. Do not restate what you just saw."
)

NUDGE_AFTER_EMPTY_RESPONSE = (
    "Your last response was empty. This often happens after tool errors or when "
    "the model is uncertain. Pick the most likely next action and try it — you can "
    "adjust based on results. Call a tool, edit code, or give <final> if done."
)

NUDGE_AFTER_EMPTY_NO_TOOLS = (
    "Your last response was empty but you have not used any tools yet. Start by "
    "inspecting the relevant files (read_file, grep_files, list_files) to understand "
    "the codebase before making changes."
)

RESUME_AFTER_PAUSE = (
    "Resume from the previous pause. Continue with the next concrete tool call, "
    "code change, or <final> answer."
)

RESUME_AFTER_MAX_TOKENS = (
    "Your previous response was cut short by the token limit. Resume immediately "
    "with the next concrete action — pick up where you left off."
)












def run_agent_turn(
    *,
    model: ModelAdapter,
    tools: ToolRegistry,
    messages: list[ChatMessage],
    cwd: str,
    permissions: PermissionManager | None = None,
    session: Any | None = None,
    store: Store[AppState] | None = None,
    max_steps: int = 50,
    on_tool_start: Callable[[str, dict], None] | None = None,
    on_tool_result: Callable[[str, str, bool], None] | None = None,
    on_assistant_message: Callable[[str], None] | None = None,
    on_progress_message: Callable[[str], None] | None = None,
    on_runtime_event: Callable[[RuntimeEvent], None] | None = None,
    on_assistant_stream_chunk: Callable[[str], None] | None = None,
    on_thinking_chunk: Callable[[str], None] | None = None,
    context_manager: ContextManager | None = None,
    runtime: dict | None = None,
    metrics_collector: AgentMetricsCollector | None = None,
    system_prompt: str = "",
    project_context: str = "",
    enable_work_chain: bool = True,
) -> list[ChatMessage]:
    # Prelude: prepare per-turn state before we enter the recurrent think/act loop.
    current_messages = list(messages)
    runtime = runtime or {}
    configured_runtime_model = (
        str(runtime.get("configuredModel", "")).strip()
        or str(runtime.get("model", "")).strip()
        or str(getattr(model, "model_id", "") or "").strip()
    )
    if configured_runtime_model:
        runtime.setdefault("configuredModel", configured_runtime_model)
    runtime_profile = resolve_runtime_profile(runtime, fallback_max_steps=max_steps)
    turn_state = TurnRecurrentState(
        max_steps=runtime_profile.max_steps,
        profile_name=runtime_profile.name,
        widen_after_step=runtime_profile.widen_after_step,
        empty_response_retry_limit=runtime_profile.empty_response_retry_limit,
        recoverable_thinking_retry_limit=runtime_profile.recoverable_thinking_retry_limit,
        verification_state=TurnVerificationState(
            strict=runtime_profile.strict_step_verification,
            requires_explicit_final=runtime_profile.strict_step_verification,
        ),
    )
    max_steps = runtime_profile.max_steps

    def emit_runtime_event(
        *,
        category: RuntimeEventCategory,
        message: str,
        emit_progress: bool = True,
        stop_reason: str = "",
        widening_reason: str = "",
        evidence_summary: str = "",
    ) -> None:
        policy = turn_state.step_policy
        event = RuntimeEvent(
            category=category,
            message=message,
            step=turn_state.step or None,
            profile=runtime_profile.name,
            phase=policy.phase if policy is not None else "",
            verification_focus=(
                policy.verification_focus if policy is not None else ""
            ),
            stop_reason=stop_reason,
            widening_reason=widening_reason,
            evidence_summary=evidence_summary,
        )
        if on_runtime_event:
            on_runtime_event(event)
        if emit_progress and on_progress_message:
            on_progress_message(message)

    tool_scheduler = ToolScheduler(metrics_collector=metrics_collector)

    composition = compose_runtime(
        model=model,
        tools=tools,
        current_messages=current_messages,
        cwd=cwd,
        runtime=runtime,
        enable_work_chain=enable_work_chain,
        system_prompt=system_prompt,
        project_context=project_context,
        context_manager=context_manager,
        tool_scheduler=tool_scheduler,
        turn_state=turn_state,
        on_assistant_message=on_assistant_message,
    )
    model = composition.model
    current_messages = composition.current_messages
    max_steps = composition.max_steps
    prelude = composition.prelude
    orch = composition.orch
    feedback_controller = composition.feedback_controller
    feedforward_controller = composition.feedforward_controller
    stability_monitor = composition.stability_monitor
    cybernetic_supervisor = composition.cybernetic_supervisor
    adaptive_pid_tuner = composition.adaptive_pid_tuner
    state_observer = composition.state_observer
    decoupling_controller = composition.decoupling_controller
    predictive_controller = composition.predictive_controller
    self_healing_engine = composition.self_healing_engine
    progress_controller = composition.progress_controller
    memory_injection_ctrl = composition.memory_injection_ctrl
    model_selection_ctrl = composition.model_selection_ctrl
    smart_router = composition.smart_router
    reflection_engine = composition.reflection_engine
    model_switcher = composition.model_switcher
    memory_injector = composition.memory_injector
    context_compactor = composition.context_compactor
    context_cybernetics = composition.context_cybernetics
    memory_mgr = composition.memory_mgr
    micro_compactor = composition.micro_compactor
    compaction_breaker = composition.compaction_breaker
    cost_control = composition.cost_control

    try:
        # Recurrent kernel: repeated think/act/observe iterations over one turn.
        while turn_state.has_remaining_steps():
            step = turn_state.begin_step()
            previous_policy = turn_state.step_policy
            current_policy = derive_turn_step_policy(turn_state)
            policy_message = render_turn_policy_message(
                previous_policy=previous_policy,
                current_policy=current_policy,
            )
            if policy_message:
                turn_state.set_progress_summary(policy_message)
                emit_runtime_event(category="phase", message=policy_message)
                logger.info("Turn policy update: %s", policy_message)
            if (
                current_policy.should_compact_aggressively
                and context_manager
                and context_manager.should_auto_compact()
                and compaction_breaker.is_allowed()
            ):
                try:
                    current_messages = context_manager.compact_messages()
                    compaction_breaker.record_success()
                except Exception as exc:
                    compaction_breaker.record_failure()
                    logger.warning("Aggressive compaction failed: %s", exc)
                emit_runtime_event(
                    category="compaction",
                    message="Compacted context for the current runtime phase.",
                )
            protected_context = get_working_memory().get_protected_content()
            turn_state.stable_task_pack = build_stable_task_pack(
                task=prelude.task,
                task_metadata=prelude.task_metadata,
                protected_context=protected_context,
                task_graph=prelude.task_graph,
                task_slot_key=prelude.task_slot_key,
                latest_tool_result_summary=turn_state.latest_tool_result_summary,
                progress_state=turn_state.progress_state,
                verification_state=turn_state.verification_state,
                budget_signals=turn_state.budget_signals,
            )
            if turn_state.stable_task_pack:
                stable_text = turn_state.stable_task_pack.to_protected_text()
                current_messages = _upsert_stable_task_state_message(
                    current_messages,
                    stable_text,
                )
                if runtime_profile.name == "single-deep":
                    protect_context(
                        content=stable_text,
                        entry_type="active_task",
                        ttl_seconds=runtime_profile.working_memory_ttl_seconds,
                        importance=runtime_profile.working_memory_importance,
                    )
                if context_manager:
                    context_manager.messages = current_messages

            # Hook: agent turn started
            fire_hook_sync(HookEvent.AGENT_START, step=step, cwd=cwd)

            # 高级控制论闭环（每个 step 开始时执行）
            if enable_work_chain and orch:
                orch.step_start(
                    context_manager=context_manager,
                    step=step,
                    tool_error_count=turn_state.tool_error_count,
                    saw_tool_result=turn_state.saw_tool_result,
                )
            elif enable_work_chain:
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

                    # 将 Kalman 估计值输入到控制器
                    if observed_state.confidence > 0.4:
                        if observed_state.internal_load > 0.8:
                            logger.info(
                                "StateObserver: high internal_load=%.2f, reduce concurrency",
                                observed_state.internal_load,
                            )
                        if observed_state.hidden_errors > 0.5 and self_healing_engine:
                            self_healing_engine.detect_and_heal({
                                "error_rate": observed_state.hidden_errors * 5.0,
                                "context_usage": observed_state.context_pressure,
                            })
                        if observed_state.system_degradation > 0.4:
                            logger.warning(
                                "StateObserver: system degradation=%.2f confidence=%.2f",
                                observed_state.system_degradation,
                                observed_state.confidence,
                            )

                # 预测控制：预测未来趋势并提前调整
                if predictive_controller:
                    if context_manager:
                        stats = context_manager.get_stats()
                        predictive_controller.update("context_usage", stats.usage_percentage / 100.0)
                    predictive_controller.update("error_rate", turn_state.tool_error_count / max(step, 1))

                    if step > 2:
                        actions = predictive_controller.generate_predictive_actions()
                        if actions and actions[0].urgency > 0.7:
                            action = actions[0]
                            logger.info(
                                "Predictive action: %s urgency=%.2f horizon=%s",
                                action.recommended_action, action.urgency,
                                getattr(action, 'horizon', 'unknown'),
                            )
                            # Execute predictive actions via dispatch
                            dispatch: dict[str, Callable[[], None]] = {
                                "trigger_compaction": lambda: (
                                    context_cybernetics.try_reactive_recover(current_messages, "predictive")
                                    if context_cybernetics else None
                                ),
                                "enable_safe_mode": lambda: logger.info(
                                    "Predictive: safe_mode recommended (reduce concurrency, extend timeouts)"
                                ),
                                "reduce_concurrency": lambda: logger.info(
                                    "Predictive: reduce_concurrency recommended"
                                ),
                            }
                            handler = dispatch.get(action.recommended_action)
                            if handler:
                                try:
                                    handler()
                                except Exception as exc:
                                    logger.warning(
                                        "Predictive action %s failed: %s",
                                        action.recommended_action, exc,
                                    )
                            # Also run self-healing for corroboration
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
                # ── Layer 0: Preemptive context guard (CC-style blocking limit)
                if context_manager:
                    cm_stats = context_manager.get_stats()
                    if _is_at_blocking_limit(
                        cm_stats.total_tokens,
                        context_manager.context_window,
                    ):
                        blocking_msg = (
                            f"Context near limit ({cm_stats.total_tokens} / "
                            f"{context_manager.context_window} tokens). "
                            "Use /compact manually, or reduce task scope."
                        )
                        logger.warning("Preemptive guard: %s", blocking_msg)
                        emit_runtime_event(
                            category="stop",
                            message=blocking_msg,
                            stop_reason="blocked",
                        )
                        if on_assistant_message:
                            on_assistant_message(blocking_msg)
                        current_messages.append(
                            {"role": "assistant", "content": blocking_msg}
                        )
                        return current_messages

                next_step = _model_next(
                    model,
                    current_messages,
                    on_stream_chunk=on_assistant_stream_chunk,
                    on_thinking_chunk=on_thinking_chunk,
                    store=store,
                )
            except KeyboardInterrupt:
                raise  # Let Ctrl-C propagate
            except ConnectionError as error:
                fallback = f"Network error (connection failed or dropped): {error}"
                logger.error("Model API connection error: %s", error)
                turn_state.set_stop_reason("blocked")
                emit_runtime_event(
                    category="stop",
                    message=fallback,
                    emit_progress=False,
                    stop_reason="blocked",
                )
                if on_assistant_message:
                    on_assistant_message(fallback)
                current_messages.append({"role": "assistant", "content": fallback})
                if metrics_collector:
                    metrics_collector.end_turn(total_tokens=0)
                return current_messages
            except TimeoutError as error:
                fallback = f"Model API timeout: {error}"
                logger.error("Model API timeout: %s", error)
                turn_state.set_stop_reason("blocked")
                emit_runtime_event(
                    category="stop",
                    message=fallback,
                    emit_progress=False,
                    stop_reason="blocked",
                )
                if on_assistant_message:
                    on_assistant_message(fallback)
                current_messages.append({"role": "assistant", "content": fallback})
                if metrics_collector:
                    metrics_collector.end_turn(total_tokens=0)
                return current_messages
            except Exception as error:
                # Catch-all for unexpected errors (rate limit, auth, server 5xx, etc.)
                error_type = type(error).__name__
                active_model_id = _infer_active_model_id(model, runtime, error)
                fallback = _summarize_model_api_failure(
                    error_type=error_type,
                    error=error,
                    active_model_id=active_model_id,
                    runtime=runtime,
                )
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

                # ModelSwitcher: 尝试切换到备用模型并重试
                if model_switcher and "rate" not in error_str and _should_attempt_model_fallback(error_str):
                    try:
                        if hasattr(model_switcher, "sync_current_model"):
                            model_switcher.sync_current_model(active_model_id, adapter=model)
                        if hasattr(model_switcher, "record_runtime_failure"):
                            model_switcher.record_runtime_failure(active_model_id)
                        if runtime is not None:
                            runtime["recentFailures"] = int(runtime.get("recentFailures", 0) or 0) + 1
                        switch_result = model_switcher.switch_to(
                            "",  # Let switcher pick fallback
                            reason=f"{error_type}: {error_str[:80]}",
                        )
                        if switch_result.success and switch_result.adapter is not None:
                            model = switch_result.adapter
                            fallback_message = (
                                f"Model fallback: switched from {switch_result.old_model} "
                                f"to {switch_result.new_model} after {error_type}."
                            )
                            logger.info(
                                "ModelSwitcher: switched to %s, retrying with new adapter",
                                switch_result.new_model,
                            )
                            emit_runtime_event(
                                category="recovery",
                                message=fallback_message,
                            )
                            continue
                        fallback = _summarize_model_api_failure(
                            error_type=error_type,
                            error=error,
                            active_model_id=active_model_id,
                            fallback_errors=switch_result.errors,
                            runtime=runtime,
                        )
                    except Exception:
                        pass

                if on_assistant_message:
                    on_assistant_message(fallback)
                turn_state.set_stop_reason("blocked")
                emit_runtime_event(
                    category="stop",
                    message=fallback,
                    emit_progress=False,
                    stop_reason="blocked",
                )
                current_messages.append({"role": "assistant", "content": fallback})
                if metrics_collector:
                    metrics_collector.end_turn(total_tokens=0)
                return current_messages

            if next_step.type == "assistant":
                is_empty = _is_empty_assistant_response(next_step.content)
                diagnostics = next_step.diagnostics
                assistant_decision = decide_assistant_turn(
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
                    step_policy=turn_state.step_policy,
                )

                if assistant_decision.kind == "progress":
                    if assistant_decision.assistant_content:
                        turn_state.set_progress_summary(assistant_decision.assistant_content)
                        if assistant_decision.runtime_event_category is not None:
                            emit_runtime_event(
                                category=assistant_decision.runtime_event_category,
                                message=assistant_decision.assistant_content,
                                evidence_summary=(
                                    turn_state.verification_state.evidence_summary
                                    or turn_state.latest_tool_result_summary
                                ),
                            )
                        elif on_progress_message:
                            on_progress_message(assistant_decision.assistant_content)
                        current_messages.append(
                            {
                                "role": "assistant_progress",
                                "content": assistant_decision.assistant_content,
                            }
                        )
                    if assistant_decision.user_content:
                        current_messages.append(
                            {
                                "role": "user",
                                "content": assistant_decision.user_content,
                            }
                        )
                    continue

                if assistant_decision.kind == "retry":
                    if assistant_decision.user_content:
                        current_messages.append(
                            {
                                "role": "user",
                                "content": assistant_decision.user_content,
                            }
                        )
                    continue

                if assistant_decision.kind == "fallback":
                    if assistant_decision.stop_reason == "widen_needed":
                        transitioned = turn_state.activate_widening(
                            extra_steps=runtime_profile.widening_step_bonus,
                        )
                        if transitioned:
                            widening_message = (
                                assistant_decision.assistant_content
                                or "Depth stalled; switching to widened mode."
                            )
                            if turn_state.widening_trigger_reason:
                                widening_message += (
                                    " Escalation trigger: "
                                    f"{turn_state.widening_trigger_reason}."
                                )
                            turn_state.set_progress_summary(
                                "runtime widened after the narrow path stalled"
                            )
                            emit_runtime_event(
                                category="widening",
                                message=widening_message,
                                widening_reason=turn_state.widening_trigger_reason,
                                evidence_summary=turn_state.widening_trigger_evidence,
                            )
                            current_messages.append(
                                {
                                    "role": "assistant_progress",
                                    "content": widening_message,
                                }
                            )
                            current_messages.append(
                                {
                                    "role": "user",
                                    "content": build_widening_transition_nudge(
                                        turn_state.latest_tool_result_summary,
                                        widening_reason=turn_state.widening_trigger_reason,
                                        widening_evidence_summary=turn_state.widening_trigger_evidence,
                                    ),
                                }
                            )
                            continue
                    if assistant_decision.stop_reason:
                        turn_state.set_stop_reason(assistant_decision.stop_reason)
                        emit_runtime_event(
                            category="stop",
                            message=(
                                assistant_decision.assistant_content
                                or "Turn stopped without a final answer."
                            ),
                            emit_progress=False,
                            stop_reason=assistant_decision.stop_reason,
                            evidence_summary=(
                                turn_state.verification_state.evidence_summary
                                or turn_state.latest_tool_result_summary
                            ),
                        )
                    if assistant_decision.assistant_content and on_assistant_message:
                        on_assistant_message(assistant_decision.assistant_content)
                    if assistant_decision.assistant_content:
                        current_messages.append(
                            {
                                "role": "assistant",
                                "content": assistant_decision.assistant_content,
                            }
                        )
                    return current_messages

                if assistant_decision.stop_reason:
                    turn_state.set_stop_reason(assistant_decision.stop_reason)
                    emit_runtime_event(
                        category="stop",
                        message=assistant_decision.assistant_content or "Turn completed.",
                        emit_progress=False,
                        stop_reason=assistant_decision.stop_reason,
                        evidence_summary=(
                            turn_state.verification_state.evidence_summary
                            or turn_state.latest_tool_result_summary
                        ),
                    )
                if model_switcher and hasattr(model_switcher, "clear_runtime_failures"):
                    model_switcher.clear_runtime_failures()
                if assistant_decision.assistant_content:
                    turn_state.set_progress_summary("assistant finalized the turn")
                    if on_assistant_message:
                        on_assistant_message(assistant_decision.assistant_content)
                    current_messages.append(
                        {
                            "role": "assistant",
                            "content": assistant_decision.assistant_content,
                        }
                    )
                if assistant_decision.protect_final_answer and assistant_decision.assistant_content:
                    protect_context(
                        content=assistant_decision.assistant_content[:500],
                        entry_type="key_decision",
                        ttl_seconds=runtime_profile.working_memory_ttl_seconds,
                        importance=runtime_profile.working_memory_importance,
                    )
                return current_messages

            if next_step.content:
                role = "assistant_progress" if next_step.contentKind == "progress" else "assistant"
                if role == "assistant_progress":
                    turn_state.set_progress_summary(next_step.content)
                    if on_progress_message:
                        on_progress_message(next_step.content)
                    current_messages.append({"role": role, "content": next_step.content})
                    current_messages.append(
                        {
                            "role": "user",
                            "content": NUDGE_CONTINUE,
                        }
                    )
                else:
                    turn_state.set_progress_summary(next_step.content)
                    if on_assistant_message:
                        on_assistant_message(next_step.content)
                    current_messages.append({"role": role, "content": next_step.content})

            if not next_step.calls and next_step.content and next_step.contentKind != "progress":
                turn_state.set_stop_reason("done")
                emit_runtime_event(
                    category="stop",
                    message=next_step.content,
                    emit_progress=False,
                    stop_reason="done",
                    evidence_summary=(
                        turn_state.verification_state.evidence_summary
                        or turn_state.latest_tool_result_summary
                    ),
                )
                return current_messages

            # --- Concurrent tool execution ---
            # Classify calls into concurrent-safe (read-only) vs serial (writes/commands)
            calls = next_step.calls
            _results: list[tuple[dict, ToolResult]] = []

            if len(calls) <= 1:
                # Single call — no benefit from concurrency, run directly
                call = calls[0]
                if metrics_collector:
                    metrics_collector.start_tool(call["toolName"])
                result = _execute_single_tool(
                    call, tools, cwd, permissions, session, runtime, store, step,
                    on_tool_start, on_tool_result, tool_scheduler,
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

                _results.clear()  # Reuse outer declaration

                # Phase 1: Run all concurrent-safe tools in parallel
                if concurrent_calls:
                    max_workers = tool_scheduler.get_recommended_max_workers(
                        concurrent_calls,
                        error_rate=turn_state.tool_error_count / max(step, 1),
                        avg_latency=step * 2.0,
                        recent_failures=turn_state.tool_error_count,
                    )
                    # Apply cybernetic concurrency cap if FeedbackController reduced parallelism
                    force_cap = getattr(tool_scheduler, '_force_max_workers', None)
                    if force_cap:
                        max_workers = min(max_workers, force_cap)
                    if tool_scheduler.last_decision:
                        logger.info(
                            "ToolSchedulerController: workers=%d multiplier=%.2f cooldown=%.2fs [%s]",
                            max_workers,
                            tool_scheduler.last_decision.concurrency_multiplier,
                            tool_scheduler.last_decision.cooldown_seconds,
                            ", ".join(tool_scheduler.last_decision.reasons or []),
                        )
                    with concurrent.futures.ThreadPoolExecutor(
                        max_workers=max_workers,
                        thread_name_prefix="mc-tool",
                    ) as pool:
                        future_to_call = {
                            pool.submit(
                                _execute_single_tool,
                                call, tools, cwd, permissions, session, runtime, None, step,
                                None, None, tool_scheduler,  # No UI callbacks during concurrent phase
                            ): call
                            for call in concurrent_calls
                        }
                        for future in concurrent.futures.as_completed(future_to_call):
                            call = future_to_call[future]
                            try:
                                result = future.result()
                            except Exception as exc:
                                result = ToolResult(ok=False, output=f"Concurrent execution error: {exc}")
                            _results.append((call, result))

                # Phase 2: Run serial tools sequentially (in original order)
                if serial_calls:
                    for call in serial_calls:
                        if metrics_collector:
                            metrics_collector.start_tool(call["toolName"])
                        result = _execute_single_tool(
                            call, tools, cwd, permissions, session, runtime, store, step,
                            on_tool_start, on_tool_result, tool_scheduler,
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

            # Process all results and build messages (preserve original call order)
            call_order = {call["id"]: idx for idx, call in enumerate(calls)}
            _results.sort(key=lambda pair: call_order.get(pair[0]["id"], 999))

            for call, result in _results:
                # Fire hooks and UI callbacks for concurrent calls (deferred)
                tool_def = tools.find(call["toolName"])
                is_concurrent = tool_def and tool_def.is_concurrency_safe and len(calls) > 1

                if is_concurrent:
                    # Deferred UI callbacks for concurrent tools
                    if on_tool_start:
                        on_tool_start(call["toolName"], call["input"])
                    if store:
                        store.set_state(set_busy(call["toolName"]))
                        store.set_state(increment_tool_calls())
                        store.set_state(set_idle())
                    # Hook: pre-tool-use (fire after the fact for concurrent tools)
                    fire_hook_sync(
                        HookEvent.PRE_TOOL_USE,
                        tool_name=call["toolName"],
                        tool_input=call["input"],
                        step=step,
                    )

                # Hook: post-tool-use
                fire_hook_sync(
                    HookEvent.POST_TOOL_USE,
                    tool_name=call["toolName"],
                    tool_output=result.output,
                    is_error=not result.ok,
                    step=step,
                )

                if is_concurrent:
                    if on_tool_result:
                        on_tool_result(call["toolName"], result.output, not result.ok)

                tool_summary = f"{call['toolName']}: {result.output[:200]}"
                turn_state.record_tool_result(result.ok, summary=tool_summary)
                tool_decision = decide_tool_turn(
                    tool_name=call["toolName"],
                    result_output=result.output,
                    await_user=result.awaitUser,
                )
                if tool_decision.progress_summary:
                    turn_state.set_progress_summary(tool_decision.progress_summary)
                if not result.ok:
                    # Use ErrorClassifier for intelligent error handling
                    classified = ErrorClassifier.classify(result.output, tool_name=call["toolName"])
                    nudge = NudgeGenerator.generate(classified, retry_count=turn_state.tool_error_count)
                    # Append nudge to tool result content for model context
                    result_output = result.output + "\n\n[System note: " + nudge + "]"
                else:
                    result_output = result.output
                    # Increased nudge frequency: provide steering even on success
                    if getattr(tool_scheduler, '_force_nudge_frequency', False):
                        success_nudge = (
                            f"Tool '{call['toolName']}' succeeded. "
                            "The system is under stability pressure — prefer smaller, "
                            "incremental steps and verify each result before proceeding."
                        )
                        result_output = result.output + "\n\n[System note: " + success_nudge + "]"

                # Record conflicts between concurrent tools if both failed
                if not result.ok and len(calls) > 1:
                    for other_call, other_result in _results:
                        if other_call["id"] == call["id"]:
                            continue
                        if not other_result.ok:
                            tool_scheduler.record_conflict(call["toolName"], other_call["toolName"])

                # ReadDedup: 去重相同文件的重复读取，节省上下文空间
                if (
                    context_compactor
                    and result.ok
                    and call.get("toolName") == "read_file"
                ):
                    file_path = call.get("input", {}).get("path", "")
                    if file_path:
                        dedup_mgr = context_compactor.read_dedup
                        if dedup_mgr.should_dedup(file_path, result_output):
                            result_output = dedup_mgr.get_stub(file_path)
                            logger.debug("ReadDedup replaced content for %s (stub)", file_path)
                        dedup_mgr.register_read(file_path, result_output, len(current_messages))

                current_messages.append(
                    {
                        "role": "assistant_tool_call",
                        "toolUseId": call["id"],
                        "toolName": call["toolName"],
                        "input": call["input"],
                    }
                )
                current_messages.append(
                    {
                        "role": "tool_result",
                        "toolUseId": call["id"],
                        "toolName": call["toolName"],
                        "content": result_output,
                        "isError": not result.ok,
                    }
                )
                if tool_decision.kind == "await_user":
                    if tool_decision.stop_reason:
                        turn_state.set_stop_reason(tool_decision.stop_reason)
                        emit_runtime_event(
                            category="stop",
                            message=tool_decision.assistant_content or result_output,
                            emit_progress=False,
                            stop_reason=tool_decision.stop_reason,
                            evidence_summary=turn_state.latest_tool_result_summary,
                        )
                    if tool_decision.assistant_content and on_assistant_message:
                        on_assistant_message(tool_decision.assistant_content)
                    current_messages.append(
                        {
                            "role": "assistant",
                            "content": tool_decision.assistant_content or result_output,
                        }
                    )
                    if metrics_collector:
                        metrics_collector.end_turn(total_tokens=0)
                    return current_messages

            # 工具执行完成后的控制论反馈
            if enable_work_chain:
                # 多变量解耦：消除工具间的耦合影响
                if decoupling_controller:
                    decoupling_controller.record_measurement({
                        "token_usage_to_latency": (
                            context_manager.get_stats().usage_percentage / 100.0 if context_manager else 0.0,
                            step * 2.0 / 60.0,
                        ),
                        "context_pressure_to_errors": (
                            context_manager.get_stats().usage_percentage / 100.0 if context_manager else 0.0,
                            turn_state.tool_error_count / max(step, 1),
                        ),
                    })
                    decoupling_controller.compute_decoupling_matrix()

                if orch:
                    step_summary = orch.step_end(
                        tool_scheduler=tool_scheduler,
                        context_manager=context_manager,
                        step=step,
                        tool_error_count=turn_state.tool_error_count,
                        saw_tool_result=turn_state.saw_tool_result,
                        max_steps=turn_state.max_steps,
                    )
                    turn_state.max_steps = _apply_control_signal(
                        control_signal=step_summary.get("control_signal"),
                        system_state=step_summary.get("system_state"),
                        max_steps=turn_state.max_steps,
                        tool_scheduler=tool_scheduler,
                        context_compactor=context_compactor,
                        model_switcher=model_switcher,
                        feedback_controller=feedback_controller,
                    )
                else:
                    # 自愈检测：检测并修复故障
                    if self_healing_engine:
                        metrics_for_healing = {
                            "error_rate": turn_state.tool_error_count / max(step, 1),
                            "context_usage": context_manager.get_stats().usage_percentage / 100.0 if context_manager else 0.0,
                            "oscillation_index": feedback_controller._compute_oscillation() if feedback_controller else 0.0,
                        }
                        healing_actions = self_healing_engine.detect_and_heal(metrics_for_healing)
                        if healing_actions:
                            logger.info("Self-healing triggered: %s", healing_actions[0].strategy)

                    # 进度控制：检测任务是否卡住或完成
                    if progress_controller:
                        progress_signal = ProgressSignal(
                            total_steps=turn_state.max_steps,
                            completed_steps=step - turn_state.tool_error_count,
                            failed_steps=turn_state.tool_error_count,
                            tool_calls=step,
                            tool_errors=turn_state.tool_error_count,
                            output_changed=turn_state.saw_tool_result,
                            elapsed_seconds=step * 2.0,
                            max_steps=turn_state.max_steps,
                        )
                        progress_decision = progress_controller.decide(progress_signal)
                        if progress_decision.action in (ProgressAction.STOP, ProgressAction.REQUEST_CONFIRMATION):
                            logger.warning(
                                "ProgressController: action=%s health=%.2f stall=%.2f reasons=%s",
                                progress_decision.action.value,
                                progress_decision.health_score,
                                progress_decision.stall_score,
                                ", ".join(progress_decision.reasons),
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
        turn_state.set_stop_reason("max_steps")
        emit_runtime_event(
            category="stop",
            message=fallback,
            emit_progress=False,
            stop_reason="max_steps",
            evidence_summary=(
                turn_state.verification_state.evidence_summary
                or turn_state.latest_tool_result_summary
            ),
        )
        if on_assistant_message:
            on_assistant_message(fallback)
        current_messages.append({"role": "assistant", "content": fallback})
        return current_messages
    finally:
        # Coda: finalize metrics, work-chain bookkeeping, and control summaries.
        finalize_turn_coda(
            turn_state=turn_state,
            metrics_collector=metrics_collector,
            current_messages=current_messages,
            context_manager=context_manager,
            enable_work_chain=enable_work_chain,
            prelude=prelude,
            orch=orch,
            reflection_engine=reflection_engine,
            memory_injector=memory_injector,
            memory_mgr=memory_mgr,
            smart_router=smart_router,
            model=model,
            model_switcher=model_switcher,
            feedback_controller=feedback_controller,
            stability_monitor=stability_monitor,
            state_observer=state_observer,
            context_cybernetics=context_cybernetics,
            predictive_controller=predictive_controller,
            self_healing_engine=self_healing_engine,
            decoupling_controller=decoupling_controller,
            context_compactor=context_compactor,
            cost_control=cost_control,
            tool_scheduler=tool_scheduler,
            adaptive_pid_tuner=adaptive_pid_tuner,
            cybernetic_supervisor=cybernetic_supervisor,
            max_steps=max_steps,
        )
