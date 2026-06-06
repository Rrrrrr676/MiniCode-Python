# Runtime Profile Eval

## Summary

| condition | runs | completion_rate | widened_rate | verification_guard_rate | avg_model_calls | avg_runtime_events | avg_wall_time_ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| single | 2 | 0.00 | 0.00 | 0.00 | 1.00 | 2.00 | 2.78 |
| single-deep | 2 | 1.00 | 0.50 | 0.00 | 6.00 | 4.50 | 1.64 |

## Scenario Rows

| scenario | condition | completed | stop_reason | widened | verification_guard | runtime_events | model_calls | wall_time_ms | final_message |
| --- | --- | --- | --- | --- | --- | ---: | ---: | ---: | --- |
| depth-budget-floor | single | no | max_steps | no | no | 2 | 1 | 4.34 | Reached the maximum tool step limit for this turn. |
| depth-budget-floor | single-deep | yes | done | no | no | 2 | 2 | 1.40 | done |
| widening-escalation | single | no | max_steps | no | no | 2 | 1 | 1.21 | Reached the maximum tool step limit for this turn. |
| widening-escalation | single-deep | yes | done | yes | no | 7 | 10 | 1.89 | done with a broader plan |

## Runtime Timelines

- `depth-budget-floor` / `single`: phase:explore@1 -> stop:max_steps@1
- `depth-budget-floor` / `single-deep`: phase:explore@1 -> stop:done@2
- `widening-escalation` / `single`: phase:explore@1 -> stop:max_steps@1
- `widening-escalation` / `single-deep`: phase:explore@1 -> phase:execute@3 -> phase:verify@4 -> phase:verify@9 -> widen:the model stalled repeatedly before producing new evidence@9 -> phase:execute@10 -> stop:done@10

## Provider Diagnostics

| label | outcome | exit_code | summary |
| --- | --- | ---: | --- |
| headless-smoke | provider_outage | 0 | Provider availability failure: deepseek-v4-pro[1m] failed and all viable fallback models were unavailable. Remaining blo... |