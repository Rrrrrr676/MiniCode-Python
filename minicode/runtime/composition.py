"""Runtime service composition and pre-request preparation."""
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

from dataclasses import dataclass

logger = get_logger("runtime.composition")


@dataclass
class RuntimeComposition:
    model: Any = None
    current_messages: Any = None
    max_steps: Any = None
    prelude: Any = None
    orch: Any = None
    feedback_controller: Any = None
    feedforward_controller: Any = None
    stability_monitor: Any = None
    cybernetic_supervisor: Any = None
    adaptive_pid_tuner: Any = None
    state_observer: Any = None
    decoupling_controller: Any = None
    predictive_controller: Any = None
    self_healing_engine: Any = None
    progress_controller: Any = None
    memory_injection_ctrl: Any = None
    model_selection_ctrl: Any = None
    smart_router: Any = None
    reflection_engine: Any = None
    model_switcher: Any = None
    memory_injector: Any = None
    context_compactor: Any = None
    context_cybernetics: Any = None
    memory_mgr: Any = None
    micro_compactor: Any = None
    compaction_breaker: Any = None
    cost_control: Any = None

def compose_runtime(
    *,
    model: Any,
    tools: ToolRegistry,
    current_messages: list[ChatMessage],
    cwd: str,
    runtime: dict[str, Any],
    enable_work_chain: bool,
    system_prompt: str,
    project_context: str,
    context_manager: ContextManager | None,
    tool_scheduler: ToolScheduler,
    turn_state: TurnRecurrentState,
    on_assistant_message: Callable[[str], None] | None,
) -> RuntimeComposition:
    max_steps = turn_state.max_steps
    prelude = TurnPreludeState(auditor=get_auditor() if enable_work_chain else None)

    # 工程控制论控制器初始化（通过 Orchestrator 统一管理）
    orch: CyberneticOrchestrator | None = None
    feedback_controller: Any = None
    feedforward_controller: Any = None
    stability_monitor: Any = None
    cybernetic_supervisor: Any = None

    adaptive_pid_tuner: Any = None
    state_observer: Any = None
    decoupling_controller: Any = None
    predictive_controller: Any = None
    self_healing_engine: Any = None
    progress_controller: Any = None
    memory_injection_ctrl: Any = None
    model_selection_ctrl: Any = None
    smart_router: Any = None
    reflection_engine: Any = None
    model_switcher: Any = None
    memory_injector: Any = None
    context_compactor: ContextCompactor | None = None
    context_cybernetics: ContextCyberneticsOrchestrator | None = None
    memory_mgr: MemoryManager | None = None
    micro_compactor = MicroCompactor()
    compaction_breaker = CompactionCircuitBreaker()
    cost_control: Any = None

    if enable_work_chain:
        prelude.task, prelude.task_metadata = _build_work_chain_task(current_messages)
        if prelude.task:
            prelude.task_graph = TaskGraph(name=f"turn-{prelude.task.id}")
            graph_task = prelude.task_graph.add_task(
                name=prelude.task.title or prelude.task.id,
                description=prelude.task.goal or prelude.task.description,
            )
            prelude.task_graph_id = graph_task.id
            slot = prelude.task_graph.assign_slot(graph_task.id, slot_name="turn")
            prelude.task_slot_key = f"{slot.slot_name}:{slot.task_id}"
            prelude.task_graph.start_task(prelude.task_slot_key)
        prelude.layered_context, prelude.context_builder = _build_layered_context(
            current_messages, system_prompt, project_context, prelude.task,
        )
        get_pipeline_engine()
        _register_tool_capabilities(tools)

        # 初始化所有工程控制论控制器（通过 Orchestrator 统一管理）
        orch = CyberneticOrchestrator()
        orch.initialize(
            model,
            tools,
            runtime,
            smart_router=SmartRouter(),
            reflection=ReflectionEngine(memory_manager=None),
        )
        feedback_controller = orch.feedback
        cybernetic_supervisor = orch.cyber_supervisor
        stability_monitor = orch.stability
        adaptive_pid_tuner = orch.adaptive_tuner
        state_observer = orch.state_observer
        decoupling_controller = orch.decoupling
        predictive_controller = orch.predictive
        progress_controller = orch.progress
        memory_injection_ctrl = orch.memory_ctrl
        model_selection_ctrl = orch.model_ctrl
        smart_router = orch.smart_router
        reflection_engine = orch.reflection
        model_switcher = orch.model_switcher
        logger.info("CyberneticOrchestrator: %d controllers initialized", 15)
        if smart_router and prelude.task:
            try:
                current_model_id = model.model_id if hasattr(model, 'model_id') else ""
                task_text = prelude.task.raw_input if hasattr(prelude.task, 'raw_input') else str(current_messages[-1].get('content', ''))
                routing, switch_result = smart_router.route_and_switch(
                    task_text,
                    current_model=current_model_id,
                )
                logger.info(
                    "SmartRouter: model=%s tier=%s cost=$%.4f reason=%s",
                    routing.selected_model, routing.tier_name,
                    routing.estimated_cost, routing.reasoning[:80],
                )
                # 如果路由推荐了不同模型且切换成功，更新 model 引用
                if switch_result and switch_result.success:
                    model = switch_result.adapter
                    logger.info(
                        "SmartRouter: switched model %s -> %s",
                        switch_result.old_model, switch_result.new_model,
                    )
            except Exception:
                pass

        # 初始化前馈控制器（预判式优化）
        if prelude.task:
            feedforward_controller = FeedforwardController()
            preemptive_config = feedforward_controller.preconfigure(prelude.task.parsed_intent, prelude.task.raw_input)
            risk_assessment = feedforward_controller.assess_risks(prelude.task.parsed_intent, preemptive_config)
            logger.info(
                "Feedforward control: config=%s risk=%s",
                preemptive_config.recommended_model, risk_assessment.risk_level,
            )
            # Apply feedforward preemptive config to execution parameters
            if preemptive_config.confidence > 0.6:
                if turn_state.max_steps is None:
                    turn_state.max_steps = preemptive_config.max_turn_steps
                else:
                    turn_state.max_steps = min(
                        turn_state.max_steps,
                        preemptive_config.max_turn_steps,
                    )
                max_steps = turn_state.max_steps
                logger.info(
                    "Feedforward: max_steps=%d model=%s timeout=%.1fs",
                    preemptive_config.max_turn_steps,
                    preemptive_config.recommended_model,
                    preemptive_config.tool_timeout_seconds,
                )
            if risk_assessment.risk_level in ("high", "critical"):
                logger.warning(
                    "Feedforward risk assessment: level=%s probability=%.2f risks=%s",
                    risk_assessment.risk_level,
                    risk_assessment.estimated_failure_probability,
                    ", ".join(risk_assessment.identified_risks[:3]),
                )

        # 模型选择控制器：根据任务特征推荐模型
        if model_selection_ctrl and prelude.task:
            try:
                model_signal = ModelSelectionSignal(
                    task_complexity=getattr(prelude.task, 'complexity', 'moderate') if hasattr(prelude.task, 'complexity') else "moderate",
                    budget_pressure=0.3,
                    latency_pressure=0.3,
                    recent_failures=0,
                    current_model=model.model_id if hasattr(model, 'model_id') else "",
                )
                model_decision = model_selection_ctrl.decide(model_signal)
                logger.info(
                    "ModelSelectionController: model=%s score=%.2f effort=%s reasons=%s",
                    model_decision.model, model_decision.score,
                    model_decision.reasoning_effort.value,
                    ", ".join(model_decision.reasons),
                )
            except Exception:
                pass

        # 初始化上下文管理器 (Claude Code-style + Engineering Cybernetics)
        # 必须在 SelfHealingEngine 之前初始化，因为自愈引擎需要委托压缩操作
        context_compactor: ContextCompactor | None = None
        context_cybernetics: ContextCyberneticsOrchestrator | None = None
        memory_mgr: MemoryManager | None = None
        if context_manager:
            compact_config = AutoCompactConfig(
                threshold_ratio=0.85,
                circuit_breaker_limit=3,
                session_memory_enabled=True,
            )
            memory_mgr = MemoryManager(project_root=cwd)
            # 将 memory_mgr 注入 ReflectionEngine，使自省经验持久化
            if reflection_engine:
                reflection_engine.memory = memory_mgr
            # 初始化 MemoryInjector，将控制论决策落地为实际记忆注入
            # 同时创建 Reranker（使用真实 LLM 做记忆策展）
            memory_reranker = None
            try:
                from minicode.memory.reranker import MemoryReranker
                # Use the agent's model for reranking (lightweight prompt, ~500 tokens)
                memory_reranker = MemoryReranker(model_adapter=model)
            except Exception:
                pass
            memory_injector = MemoryInjector(
                memory_manager=memory_mgr,
                controller=memory_injection_ctrl,
                reranker=memory_reranker,
            )
            if orch:
                orch._last_model = model
                orch._workspace = cwd
                orch.wire_memory(memory_mgr)
                if orch.memory_pipeline is not None:
                    memory_injector = getattr(orch.memory_pipeline, "_injector", memory_injector)
            # 记忆注入控制器：根据上下文压力决定注入策略
            if memory_injection_ctrl:
                try:
                    inj_signal = MemoryInjectionSignal(
                        context_usage=context_manager.get_stats().usage_percentage / 100.0,
                        retrieval_quality=0.5,
                        recent_failure=False,
                    )
                    inj_decision = memory_injection_ctrl.decide(
                        inj_signal,
                        base_max_memories=5,
                        base_min_relevance=0.3,
                        base_max_tokens=200,
                    )
                    logger.info(
                        "MemoryInjectionController: mode=%s max_mem=%d min_rel=%.2f max_tok=%d",
                        inj_decision.mode.value, inj_decision.max_memories,
                        inj_decision.min_relevance, inj_decision.max_tokens_per_memory,
                    )
                except Exception:
                    pass
            # 执行实际记忆注入：将相关记忆注入到系统 prompt 中
            if orch and prelude.task:
                try:
                    task_desc = prelude.task.raw_input if hasattr(prelude.task, 'raw_input') else ""
                    current_messages = orch.inject_memories(task_desc, current_messages)
                except Exception:
                    pass
            elif memory_injector and prelude.task:
                try:
                    task_desc = prelude.task.raw_input if hasattr(prelude.task, 'raw_input') else ""
                    injected = memory_injector.inject_for_task(task_desc)
                    if injected:
                        logger.info(
                            "MemoryInjector: injected %d memories (mode=%s)",
                            len(injected),
                            memory_injector._last_decision.mode.value if memory_injector._last_decision else "?",
                        )
                        # 将注入的记忆追加到系统 prompt
                        memory_context = "\n## Injected Memory\n" + "\n".join(
                            f"- {m.content[:200]}" for m in injected[:5]
                        )
                        for i, msg in enumerate(current_messages):
                            if msg.get("role") == "system":
                                current_messages[i] = {
                                    **msg,
                                    "content": msg["content"] + memory_context,
                                }
                                break
                except Exception:
                    pass
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
            if prelude.task and hasattr(prelude.task, 'parsed_intent') and prelude.task.parsed_intent:
                context_cybernetics.set_intent(str(prelude.task.parsed_intent.intent_type))
            logger.info("ContextCybernetics initialized: PID control loop + predictive guard")
            if orch:
                orch.context_compactor = context_compactor
                orch.context_cybernetics = context_cybernetics

        # 初始化自愈引擎（接收 cybernetics 引用用于 CONTEXT_OVERFLOW 委托）
        if orch:
            orch.wire_healing(tool_scheduler, context_compactor)
            self_healing_engine = orch.healing
        else:
            self_healing_engine = SelfHealingEngine(
                orchestrator=context_cybernetics,
                tool_scheduler=tool_scheduler,
                compactor=context_compactor,
            )
        logger.info("Self-healing engine initialized: automated recovery + compaction delegation")

        # ── Micro-compaction + circuit breaker (CC-style layered defense) ─────
        micro_compactor = MicroCompactor()
        compaction_breaker = CompactionCircuitBreaker()
        logger.info("Micro-compactor + circuit breaker initialized for layered context defense")

        # 初始化成本控制闭环 (CostTracker → PID → ToolResultBudgetManager)
        cost_control = orch.cost_control if orch else None
        if cost_control is None:
            cost_control = CostControlLoop(
                target_cost_per_min=0.50,
                kp=1.5, ki=0.08, kd=0.2,
                enabled=True,
            )
        if orch:
            orch.cost_control = cost_control
        logger.info("CostControlLoop initialized: BudgetPIDController for cost regulation")

    # 检查上下文状态 + 运行 Claude Code-style 预请求优化管线
    if context_manager:
        context_manager.messages = current_messages
        stats = context_manager.get_stats()
        logger.info("Context: %d tokens (%.0f%%), %d messages",
                   stats.total_tokens, stats.usage_percentage, stats.messages_count)

        # ── Layer 1: Micro-compaction (lightest defense) ───────────────────
        current_messages, mc_stats = micro_compactor.compact(current_messages)
        if mc_stats.reason != "no_action":
            context_manager.messages = current_messages
            logger.info(
                "MicroCompact: %s — %d → %d messages",
                mc_stats.reason,
                mc_stats.messages_before,
                mc_stats.messages_after,
            )

        # 运行控制论闭环优化管线 (Sense → Predict → Control → Act → Learn)
        if context_cybernetics:
            if cost_control:
                est_cost = stats.total_tokens * 0.000015
                adj = cost_control.run(
                    cost_usd=est_cost,
                    total_tokens=stats.total_tokens,
                    total_calls=max(turn_state.step, 1),
                )
                if context_compactor and hasattr(context_compactor, '_tool_budget') and context_compactor._tool_budget:
                    cost_control.apply_to_budget_manager(context_compactor._tool_budget)
                elif adj and adj.budget_multiplier < 0.8:
                    logger.warning(
                        "CostControl: budget tightened (mult=%.2f reason=%s) but no compactor active",
                        adj.budget_multiplier, adj.reason,
                    )

            if compaction_breaker.is_allowed():
                try:
                    cyber_messages, cyber_result, cyber_action = context_cybernetics.run_cycle(
                        current_messages,
                        error_rate=float(turn_state.tool_error_count) / max(turn_state.step, 1) if turn_state.step > 0 else 0.0,
                        avg_latency=turn_state.step * 2.0,
                        turn_id=turn_state.step,
                    )
                except Exception as exc:
                    compaction_breaker.record_failure()
                    logger.warning("Cybernetics compaction raised: %s", exc)
                    cyber_result = None
                if cyber_result and cyber_result.effective:
                    compaction_breaker.record_success()
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
            else:
                logger.warning("Cybernetics compaction blocked by circuit breaker")
        elif context_compactor:
            if compaction_breaker.is_allowed():
                try:
                    compaction_result = context_compactor.process_request(current_messages)
                except Exception as exc:
                    compaction_breaker.record_failure()
                    logger.warning("Compactor raised: %s", exc)
                    compaction_result = None
                if compaction_result and compaction_result.effective:
                    compaction_breaker.record_success()
                    current_messages = compaction_result.messages
                    context_manager.messages = current_messages
                    logger.info(
                        "ContextCompactor: %s freed %d tokens [%s]",
                        compaction_result.strategy.value,
                        compaction_result.tokens_freed,
                        compaction_result.summary_text[:80],
                    )
            else:
                logger.warning("Compactor blocked by circuit breaker")
        elif context_manager.should_auto_compact():
            if compaction_breaker.is_allowed():
                try:
                    logger.warning("Context near limit, auto-compacting...")
                    current_messages = context_manager.compact_messages()
                    compaction_breaker.record_success()
                except Exception as exc:
                    compaction_breaker.record_failure()
                    logger.warning("Auto-compact failed: %s", exc)
                if on_assistant_message:
                    on_assistant_message(context_manager.get_context_summary())
            else:
                logger.warning("Auto-compact blocked by circuit breaker")

    return RuntimeComposition(
        model=model,
        current_messages=current_messages,
        max_steps=max_steps,
        prelude=prelude,
        orch=orch,
        feedback_controller=feedback_controller,
        feedforward_controller=feedforward_controller,
        stability_monitor=stability_monitor,
        cybernetic_supervisor=cybernetic_supervisor,
        adaptive_pid_tuner=adaptive_pid_tuner,
        state_observer=state_observer,
        decoupling_controller=decoupling_controller,
        predictive_controller=predictive_controller,
        self_healing_engine=self_healing_engine,
        progress_controller=progress_controller,
        memory_injection_ctrl=memory_injection_ctrl,
        model_selection_ctrl=model_selection_ctrl,
        smart_router=smart_router,
        reflection_engine=reflection_engine,
        model_switcher=model_switcher,
        memory_injector=memory_injector,
        context_compactor=context_compactor,
        context_cybernetics=context_cybernetics,
        memory_mgr=memory_mgr,
        micro_compactor=micro_compactor,
        compaction_breaker=compaction_breaker,
        cost_control=cost_control,
    )

__all__ = ["RuntimeComposition", "compose_runtime"]
