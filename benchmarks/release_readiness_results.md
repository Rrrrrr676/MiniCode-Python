# MiniCode Release Readiness

- Generated at: 2026-06-06T03:46:02.433983+00:00
- Status: at-risk

## Core Gate

| check | status | exit_code | summary |
| --- | --- | ---: | --- |
| compileall | passed | 0 | compileall completed. |
| pytest-q | passed | 0 | 1027 passed, 2 skipped, 3 warnings in 18.88s |
| runtime-profile-eval | passed | 0 | benchmarks\runtime_profile_eval_results.md |

## Product Smokes

| check | status | exit_code | summary |
| --- | --- | ---: | --- |
| list-sessions | passed | 0 | Total: 1231 session(s) |
| inspect-session | passed | 0 | - [tool:edit_file/success] Patched demo.txt |
| replay-session | passed | 0 | - [tool:edit_file/success] Patched demo.txt |
| preview-rewind | passed | 0 | Type: edit |

## Provider Diagnostics

| label | outcome | exit_code | summary |
| --- | --- | ---: | --- |
| headless-smoke | provider_outage | 0 | Provider availability failure: deepseek-v4-pro[1m] failed and all viable fallback models were unavailable. Remaining blocker is upstream provider/channel availability, not a local retry loop. Active channel: anthropic-compatible via baseUrl/authToken. Last error (RuntimeError): No available channel for model deepseek-v4-pro[1m] under group cc (distributor) (request id: 202606060346468033683028268d9d66QHAvNlc) Next step: Primary runtime is using a single anthropic-compatible channel from baseUrl/authToken. |

## Provider Fallback Coverage

- Provider: anthropic
- Provider ready: yes
- Channel: anthropic-compatible via baseUrl/authToken
- Fallback ready: no
- Summary: readiness: warning (anthropic) [Primary provider is ready, but no configured or default fallback models are available.]
- Guidance:
  - Primary runtime is using a single anthropic-compatible channel from baseUrl/authToken.
  - Add fallbackModels or anthropicFallbackModels to enable model failover.
  - No local fallback credentials are configured for OpenAI, OpenRouter, or custom providers.

## Runtime Profile Artifacts

- JSON: D:\Desktop\minicode\benchmarks\runtime_profile_eval_results.json
- Markdown: D:\Desktop\minicode\benchmarks\runtime_profile_eval_results.md