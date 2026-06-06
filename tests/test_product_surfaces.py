from minicode.product_surfaces import build_readiness_report


def test_build_readiness_report_surfaces_viable_fallbacks() -> None:
    report = build_readiness_report(
        ".",
        runtime={
            "model": "claude-sonnet-4-20250514",
            "apiKey": "anthropic-key",
            "baseUrl": "https://api.anthropic.com",
            "fallbackModels": ["gpt-4o"],
            "openaiApiKey": "openai-key",
            "openaiBaseUrl": "https://api.openai.com",
        },
    )

    assert report.status == "ready"
    assert report.provider_ready is True
    assert report.fallback_ready is True
    assert report.fallback_candidates == ["gpt-4o", "claude-haiku-3-20240307"]
    assert report.viable_fallbacks == ["gpt-4o", "claude-haiku-3-20240307"]
    assert "fallbacks 2/2 locally ready" in report.summary


def test_build_readiness_report_warns_when_primary_ready_but_no_fallbacks() -> None:
    report = build_readiness_report(
        ".",
        runtime={
            "model": "deepseek-v4-pro[1m]",
            "baseUrl": "https://api.anthropic.com",
            "authToken": "proxy-token",
        },
    )

    assert report.status == "warning"
    assert report.provider_ready is True
    assert report.provider_channel == "anthropic-compatible via baseUrl/authToken"
    assert report.fallback_ready is False
    assert report.fallback_candidates == []
    assert any("single anthropic-compatible channel" in item.lower() for item in report.fallback_guidance)
    assert any("no local fallback credentials" in item.lower() for item in report.fallback_guidance)
    assert any("no configured or default fallback models" in issue.lower() for issue in report.issues)


def test_build_readiness_report_uses_default_fallback_coverage() -> None:
    report = build_readiness_report(
        ".",
        runtime={
            "model": "deepseek-v4-pro[1m]",
            "apiKey": "anthropic-key",
            "baseUrl": "https://api.anthropic.com",
            "openaiApiKey": "openai-key",
            "openaiBaseUrl": "https://api.openai.com",
        },
    )

    assert report.status == "ready"
    assert report.provider_ready is True
    assert report.fallback_ready is True
    assert report.fallback_candidates[:2] == ["gpt-4o", "gpt-4o-mini"]
    assert report.viable_fallbacks[:2] == ["gpt-4o", "gpt-4o-mini"]
