from app.routes.chat import _memory_compaction_threshold
from app.schemas.agent import AgentCreateRequest, AgentUpdateRequest


def test_agent_context_token_limit_is_accepted_and_used_for_compaction() -> None:
    created = AgentCreateRequest(
        org_id="org_test",
        actor_user_id="user_test",
        name="Test agent",
        context_token_limit=4800,
    )
    updated = AgentUpdateRequest(actor_user_id="user_test", context_token_limit=3200)

    assert created.context_token_limit == 4800
    assert updated.model_dump(exclude_unset=True)["context_token_limit"] == 3200
    assert _memory_compaction_threshold(created.context_token_limit) == 4800


def test_agent_context_token_limit_keeps_the_safe_minimum() -> None:
    assert _memory_compaction_threshold(10) == 800
