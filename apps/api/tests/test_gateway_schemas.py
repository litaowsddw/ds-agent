from app.schemas.gateway import LLMGenerateResponse


def test_gateway_response_accepts_nested_provider_usage_details() -> None:
    response = LLMGenerateResponse(
        text="OK",
        provider="deepseek",
        model="deepseek-v4-pro",
        usage={
            "prompt_tokens": 12,
            "completion_tokens": 3,
            "prompt_tokens_details": {"cached_tokens": 0},
            "completion_tokens_details": {"reasoning_tokens": 2},
        },
    )

    assert response.usage["prompt_tokens_details"] == {"cached_tokens": 0}
