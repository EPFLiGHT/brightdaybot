"""Tests for _build_api_params parameter shaping."""


from integrations.openai import _build_api_params


def _build(model, **kwargs):
    return _build_api_params(
        messages=None,
        input_text="hello",
        instructions=None,
        model=model,
        max_tokens=kwargs.get("max_tokens"),
        temperature=kwargs.get("temperature"),
        reasoning_effort=kwargs.get("reasoning_effort"),
    )


class TestBuildApiParams:
    def test_gpt5_drops_temperature(self):
        """gpt-5* rejects temperature even when reasoning_effort isn't passed."""
        params = _build("gpt-5.5", temperature=0.7)
        assert "temperature" not in params

    def test_gpt5_with_reasoning_effort_keeps_reasoning_drops_temperature(self):
        params = _build("gpt-5.5", temperature=0.7, reasoning_effort="low")
        assert params.get("reasoning") == {"effort": "low"}
        assert "temperature" not in params

    def test_gpt4_keeps_temperature(self):
        """Non-reasoning models still get temperature."""
        params = _build("gpt-4.1", temperature=0.7)
        assert params["temperature"] == 0.7

    def test_o3_drops_temperature(self):
        params = _build("o3-mini", temperature=0.5)
        assert "temperature" not in params
