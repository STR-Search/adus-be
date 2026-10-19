from app.deal_recommendation.agent.prompt import build_system_prompt


def test_prompt_is_deterministic_and_lists_slugs():
    options = {"market_type": ["mountain", "beach"], "execution_type": ["value_add", "turnkey"]}
    reordered = {"execution_type": ["turnkey", "value_add"], "market_type": ["beach", "mountain"]}
    prompt = build_system_prompt(options)
    assert prompt == build_system_prompt(reordered)
    assert prompt.index("execution_type") < prompt.index("market_type")
    assert prompt.index("beach") < prompt.index("mountain")
    assert "present_shortlist" in prompt
    assert "update_client_profile" in prompt
