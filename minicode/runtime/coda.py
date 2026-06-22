"""Turn coda: metrics, work-chain finalization, learning, and reports."""
from __future__ import annotations

import time
from typing import Any

from minicode.context.tokens import estimate_message_tokens
from minicode.control.stability import MetricSnapshot
from minicode.integrations.hooks import HookEvent, fire_hook_sync
from minicode.memory import MemoryScope
from minicode.observability.decision_audit import DecisionOutcome
from minicode.observability.logging import get_logger
from minicode.runtime.kernel import build_turn_coda_summary, finalize_work_chain_task
from minicode.runtime.smart_routing import TaskOutcome
from minicode.runtime.tasks.graph import TaskState as GraphTaskState
from minicode.runtime.tasks.object import TaskState
from minicode.control.supervisor import save_supervisor_report

logger = get_logger("runtime.coda")

def finalize_turn_coda(
    turn_state: Any,
    metrics_collector: Any,
    current_messages: Any,
    context_manager: Any,
    enable_work_chain: Any,
    prelude: Any,
    orch: Any,
    reflection_engine: Any,
    memory_injector: Any,
    memory_mgr: Any,
    smart_router: Any,
    model: Any,
    model_switcher: Any,
    feedback_controller: Any,
    stability_monitor: Any,
    state_observer: Any,
    context_cybernetics: Any,
    predictive_controller: Any,
    self_healing_engine: Any,
    decoupling_controller: Any,
    context_compactor: Any,
    cost_control: Any,
    tool_scheduler: Any,
    adaptive_pid_tuner: Any,
    cybernetic_supervisor: Any,
    max_steps: Any,
) -> None:
    fire_hook_sync(
        HookEvent.AGENT_STOP,
        step=turn_state.step,
        tool_errors=turn_state.tool_error_count,
    )
    step = turn_state.step
    if metrics_collector and metrics_collector._current_turn is not None:
        total_tokens = sum(
            estimate_message_tokens(m) for m in current_messages
        ) if context_manager else 0
        metrics_collector.end_turn(total_tokens=total_tokens)

    context_usage = 0.0
    if context_manager:
        try:
            context_usage = context_manager.get_stats().usage_percentage / 100.0
        except Exception:
            context_usage = 0.0
    coda_summary = build_turn_coda_summary(
        turn_state=turn_state,
        context_usage=context_usage,
    )

    if enable_work_chain and prelude.task:
        finalize_work_chain_task(
            task=prelude.task,
            auditor=prelude.auditor,
            coda_summary=coda_summary,
            success_outcome=DecisionOutcome.SUCCESS,
            failure_outcome=DecisionOutcome.FAILURE,
        )

        if prelude.task_graph and prelude.task_slot_key:
            try:
                if coda_summary.task_state is TaskState.COMPLETED:
                    prelude.task_graph.complete_task(
                        prelude.task_slot_key,
                        result=prelude.task.result_summary,
                    )
                elif coda_summary.task_state is TaskState.PAUSED:
                    slot = prelude.task_graph.slots.get(prelude.task_slot_key)
                    if slot is not None:
                        slot.state = GraphTaskState.QUEUED
                        slot.result = prelude.task.result_summary
                        prelude.task_graph.updated_at = time.time()
                else:
                    prelude.task_graph.fail_task(
                        prelude.task_slot_key,
                        prelude.task.result_summary,
                    )
            except Exception:
                logger.debug("TaskGraph finalization skipped", exc_info=True)

        logger.info(
            "Work chain completed: task=%s state=%s stop_reason=%s steps=%d errors=%d",
            prelude.task.id,
            prelude.task.state.value,
            coda_summary.stop_reason,
            turn_state.step,
            turn_state.tool_error_count,
        )

        # 任务后自省：提取经验教训
        if orch and prelude.task:
            try:
                execution_trace: list[dict[str, Any]] = [
                    {"type": "tool_call", "count": turn_state.step},
                    {
                        "type": "error",
                        "count": turn_state.tool_error_count,
                        "content": f"{turn_state.tool_error_count} errors",
                    }
                    if turn_state.tool_error_count > 0
                    else {},
                    {"type": "assistant", "steps": turn_state.step},
                ]
                orch.reflect_on_task(
                    task_description=(
                        prelude.task.raw_input
                        if hasattr(prelude.task, "raw_input")
                        else str(prelude.task.id)
                    ),
                    step=turn_state.step,
                    tool_error_count=turn_state.tool_error_count,
                    execution_trace=execution_trace,
                )
            except Exception:
                pass
        elif reflection_engine and prelude.task:
            try:
                execution_trace: list[dict[str, Any]] = [
                    {"type": "tool_call", "count": turn_state.step},
                    {
                        "type": "error",
                        "count": turn_state.tool_error_count,
                        "content": f"{turn_state.tool_error_count} errors",
                    }
                    if turn_state.tool_error_count > 0
                    else {},
                    {"type": "assistant", "steps": turn_state.step},
                ]
                reflection = reflection_engine.reflect(
                    task_description=(
                        prelude.task.raw_input
                        if hasattr(prelude.task, "raw_input")
                        else str(prelude.task.id)
                    ),
                    execution_trace=execution_trace,
                )
                logger.info(
                    "AgentReflection: success=%s confidence=%.2f lessons=%d improvements=%d",
                    reflection.success, reflection.confidence,
                    len(reflection.lessons_learned), len(reflection.suggested_improvements),
                )
            except Exception:
                pass

        # 记忆质量反馈：任务成功→注入的记忆 usage_count+1
        if memory_injector and hasattr(memory_injector, '_cached_result'):
            try:
                from minicode.memory import MemoryScope
                for mem in memory_injector._cached_result:
                    if not hasattr(mem, 'id'):
                        continue
                    try:
                        _mgr = memory_mgr
                    except NameError:
                        continue
                    for scope_name in ['project', 'local', 'user']:
                        try:
                            scope = MemoryScope(scope_name)
                            if scope in _mgr.memories:
                                entry = _mgr.memories[scope]._id_index.get(mem.id)
                                if entry:
                                    entry.usage_count += (
                                        2 if turn_state.tool_error_count == 0 else -1
                                    )
                                    entry.last_accessed = time.time()
                                    break
                                    entry.last_accessed = time.time()
                                    break
                        except (ValueError, KeyError):
                            continue
            except Exception:
                pass

        # 路由反馈学习：记录任务结果以优化未来路由
        if smart_router and prelude.task:
            try:
                outcome = TaskOutcome(
                    task_text=(
                        prelude.task.raw_input
                        if hasattr(prelude.task, "raw_input")
                        else str(prelude.task.id)
                    ),
                    assigned_model=(
                        model.model_id if hasattr(model, "model_id") else "unknown"
                    ),
                    success=(turn_state.tool_error_count == 0),
                    duration_ms=turn_state.step * 2000.0,
                    cost_usd=0.0,
                    tool_errors=turn_state.tool_error_count,
                    model_switches=model_switcher.switch_count() if model_switcher else 0,
                )
                smart_router.learner().record_outcome(outcome)
            except Exception:
                pass

    # 控制论反馈：记录模式有效性
    if enable_work_chain and feedback_controller and prelude.task:
        pattern_id = (
            f"{prelude.task_metadata.get('intent_type', 'unknown')}_{prelude.task.id}"
        )
        feedback_controller.record_pattern_effectiveness(
            pattern_id, turn_state.tool_error_count == 0
        )

    # 稳定性监测：记录快照
    if stability_monitor:
        from minicode.control.stability import MetricSnapshot
        snapshot = MetricSnapshot(
            timestamp=time.time(),
            error_rate=float(turn_state.tool_error_count) / max(turn_state.step, 1),
            avg_latency=step * 2.0,  # 简化估算
            context_usage=context_manager.get_stats().usage_percentage if context_manager else 0.0,
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
        # Apply outer-loop ControlSignal to runtime parameters
        if control_signal.confidence > 0.6:
            if control_signal.limit_max_steps and control_signal.limit_max_steps < max_steps:
                logger.info(
                    "FeedbackController: limiting max_steps %d → %d",
                    max_steps, control_signal.limit_max_steps,
                )
                max_steps = control_signal.limit_max_steps
            if control_signal.adjust_token_budget != 1.0:
                if context_compactor and hasattr(context_compactor, '_tool_budget') and context_compactor._tool_budget:
                    new_budget = max(
                        1000,
                        int(context_compactor._tool_budget.budget_per_message * control_signal.adjust_token_budget),
                    )
                    context_compactor._tool_budget.budget_per_message = new_budget
                    logger.info(
                        "FeedbackController: token budget adjusted to %d (mult=%.2f)",
                        new_budget, control_signal.adjust_token_budget,
                    )
            if control_signal.reduce_parallelism:
                # Cap tool concurrency at 2
                if not hasattr(tool_scheduler, '_force_max_workers'):
                    tool_scheduler._force_max_workers = 2
                logger.info(
                    "FeedbackController: reduce_parallelism → max_workers=2 "
                    "(oscillation=%.2f)", control_signal.oscillation_index,
                )
            if control_signal.adjust_concurrency != 0:
                cap = max(1, 4 + control_signal.adjust_concurrency)
                tool_scheduler._force_max_workers = cap
                logger.info(
                    "FeedbackController: adjust_concurrency=%+d → max_workers=%d",
                    control_signal.adjust_concurrency, cap,
                )
            if control_signal.increase_model_level:
                logger.info(
                    "FeedbackController: model upgrade recommended (errors=%.2f perf=%.2f)",
                    system_state.error_frequency, system_state.performance_score(),
                )
                if model_switcher:
                    model_switcher._pending_upgrade = True
            if control_signal.decrease_model_level:
                logger.info(
                    "FeedbackController: model downgrade recommended (efficiency=%.2f)",
                    system_state.token_efficiency,
                )
            if control_signal.suggest_memory_persistence:
                logger.info("FeedbackController: persisting working memory")
                if context_compactor and hasattr(context_compactor, '_tool_budget'):
                    try:
                        context_compactor._tool_budget.flush()
                    except Exception:
                        pass
            if control_signal.recommend_skill_update:
                logger.info("FeedbackController: skill update recommended (pattern=%.2f)",
                           system_state.pattern_reuse_rate)
                if not hasattr(tool_scheduler, '_pending_skill_update'):
                    tool_scheduler._pending_skill_update = True

            if control_signal.reduce_tool_timeout:
                new_timeout = max(5.0, control_signal.reduce_tool_timeout)
                tool_scheduler._force_tool_timeout = new_timeout
                logger.info(
                    "FeedbackController: tool timeout reduced to %.1fs",
                    new_timeout,
                )
            elif hasattr(tool_scheduler, '_force_tool_timeout'):
                del tool_scheduler._force_tool_timeout

            if control_signal.increase_nudge_frequency:
                tool_scheduler._force_nudge_frequency = True
                logger.info(
                    "FeedbackController: nudge frequency increased (stability=%.2f)",
                    system_state.stability_score(),
                )
            elif hasattr(tool_scheduler, '_force_nudge_frequency'):
                del tool_scheduler._force_nudge_frequency

            if control_signal.promote_pattern:
                feedback_controller.record_pattern_effectiveness(
                    control_signal.promote_pattern, True
                )
                logger.info(
                    "FeedbackController: pattern promoted '%s'",
                    control_signal.promote_pattern,
                )

            if control_signal.force_compaction and context_compactor:
                try:
                    compacted = context_compactor.compact_messages()
                    logger.info(
                        "FeedbackController: forced compaction (%d messages)",
                        len(compacted) if compacted else 0,
                    )
                except Exception as exc:
                    logger.warning("FeedbackController: forced compaction failed: %s", exc)

        # 自适应PID调参：每20轮自动调节内外环PID参数
        if adaptive_pid_tuner and step > 0 and step % 20 == 0 and feedback_controller:
            try:
                stability_error = 1.0 - system_state.stability_score()
                perf_score = system_state.performance_score()
                tuned = adaptive_pid_tuner.tune(
                    stability_error, dt=1.0, performance_score=perf_score
                )
                if tuned and adaptive_pid_tuner._performance_history:
                    recent_perf = adaptive_pid_tuner._performance_history[-5:]
                    avg_perf = sum(recent_perf) / len(recent_perf)
                    if context_cybernetics:
                        cp = context_cybernetics.pid
                        cp.kp = tuned.kp
                        cp.ki = tuned.ki
                        cp.kd = tuned.kd
                        logger.info(
                            "AdaptivePIDTuner: context PID tuned kp=%.3f ki=%.3f kd=%.3f "
                            "method=%s perf=%.2f",
                            tuned.kp, tuned.ki, tuned.kd,
                            adaptive_pid_tuner._active_method.value if hasattr(adaptive_pid_tuner, '_active_method') else 'unknown',
                            avg_perf,
                        )
            except Exception:
                pass  # 调参失败不能拖垮主循环

    # 总监督层: 汇总局部控制器输出为统一风险视图
    if cybernetic_supervisor:
        supervisor_snapshots = []
        if context_cybernetics:
            supervisor_snapshots.append(
                cybernetic_supervisor.snapshot_from_context(context_cybernetics.get_stats())
            )
        if cost_control:
            supervisor_snapshots.append(
                cybernetic_supervisor.snapshot_from_cost(cost_control.get_stats())
            )
        if tool_scheduler.last_decision:
            supervisor_snapshots.append(
                cybernetic_supervisor.snapshot_from_tool_decision(
                    tool_scheduler.last_decision.to_dict()
                )
            )
        supervisor_report = cybernetic_supervisor.report(supervisor_snapshots)
        save_supervisor_report(supervisor_report)
        logger.info(
            "CyberneticSupervisor: health=%.2f risk=%s actions=%s",
            supervisor_report.overall_health,
            supervisor_report.risk_level.value,
            "; ".join(supervisor_report.recommended_actions[:3]),
        )

__all__ = ["finalize_turn_coda"]
