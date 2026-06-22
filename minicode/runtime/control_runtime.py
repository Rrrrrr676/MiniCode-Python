"""Apply outer-loop control signals to runtime services."""
from __future__ import annotations

from typing import Any

from minicode.observability.logging import get_logger

logger = get_logger("runtime.control_runtime")

def _apply_control_signal(
    *,
    control_signal: Any,
    system_state: Any,
    max_steps: int | None,
    tool_scheduler: ToolScheduler,
    context_compactor: ContextCompactor | None,
    model_switcher: Any | None,
    feedback_controller: Any | None = None,
) -> int | None:
    """Apply FeedbackController output to live runtime knobs."""
    if not control_signal or control_signal.confidence <= 0.6:
        return max_steps

    if (
        control_signal.limit_max_steps
        and max_steps is not None
        and control_signal.limit_max_steps < max_steps
    ):
        logger.info(
            "FeedbackController: limiting max_steps %d -> %d",
            max_steps, control_signal.limit_max_steps,
        )
        max_steps = control_signal.limit_max_steps

    if control_signal.adjust_token_budget != 1.0:
        if (
            context_compactor
            and hasattr(context_compactor, "_tool_budget")
            and context_compactor._tool_budget
        ):
            new_budget = max(
                1000,
                int(
                    context_compactor._tool_budget.budget_per_message
                    * control_signal.adjust_token_budget
                ),
            )
            context_compactor._tool_budget.budget_per_message = new_budget
            logger.info(
                "FeedbackController: token budget adjusted to %d (mult=%.2f)",
                new_budget, control_signal.adjust_token_budget,
            )

    if control_signal.reduce_parallelism:
        tool_scheduler._force_max_workers = min(
            getattr(tool_scheduler, "_force_max_workers", 2) or 2,
            2,
        )
        logger.info(
            "FeedbackController: reduce_parallelism -> max_workers=2 "
            "(oscillation=%.2f)",
            control_signal.oscillation_index,
        )

    if control_signal.adjust_concurrency != 0:
        cap = max(1, 4 + control_signal.adjust_concurrency)
        tool_scheduler._force_max_workers = cap
        logger.info(
            "FeedbackController: adjust_concurrency=%+d -> max_workers=%d",
            control_signal.adjust_concurrency, cap,
        )

    if control_signal.increase_model_level:
        logger.info(
            "FeedbackController: model upgrade recommended (errors=%.2f perf=%.2f)",
            system_state.error_frequency,
            system_state.performance_score(),
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
        if context_compactor and hasattr(context_compactor, "_tool_budget"):
            try:
                context_compactor._tool_budget.flush()
            except Exception:
                pass

    if control_signal.recommend_skill_update:
        logger.info(
            "FeedbackController: skill update recommended (pattern=%.2f)",
            system_state.pattern_reuse_rate,
        )
        # Queue skill update for next maintenance cycle
        if not hasattr(tool_scheduler, '_pending_skill_update'):
            tool_scheduler._pending_skill_update = True
        logger.info("FeedbackController: skill update queued for next maintenance cycle")

    if control_signal.reduce_tool_timeout:
        new_timeout = max(5.0, control_signal.reduce_tool_timeout)
        tool_scheduler._force_tool_timeout = new_timeout
        logger.info(
            "FeedbackController: tool timeout reduced to %.1fs (high error rate)",
            new_timeout,
        )
    elif hasattr(tool_scheduler, '_force_tool_timeout'):
        # Reset timeout when signal no longer active
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
        if feedback_controller:
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
                "FeedbackController: forced compaction completed (%d messages)",
                len(compacted) if compacted else 0,
            )
        except Exception as exc:
            logger.warning("FeedbackController: forced compaction failed: %s", exc)

    return max_steps

__all__ = ["_apply_control_signal"]
