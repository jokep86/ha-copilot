"""
Unit tests for YAMLGenerator.
Covers: fence stripping, YAML parsing, Pydantic validation,
Claude call delegation, and error propagation for automation/scene/dashboard.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ai.yaml_generator import YAMLGenerator, YAMLGenerationError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_generator() -> YAMLGenerator:
    """Build a YAMLGenerator with mocked config, discovery, and AI client."""
    config = MagicMock()
    config.anthropic_api_key = "test_key"
    config.ai_model = "claude-test"
    config.ai_max_tokens = 1024

    discovery = MagicMock()
    discovery.get_domains = AsyncMock(return_value={})
    discovery.get_entities_by_domain = AsyncMock(return_value=[])

    with patch("app.ai.yaml_generator.anthropic.AsyncAnthropic"):
        gen = YAMLGenerator(config, discovery)
    return gen


def _mock_claude(gen: YAMLGenerator, yaml_text: str) -> None:
    """Configure the AI client mock to return yaml_text."""
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=yaml_text)]
    mock_response.usage.input_tokens = 100
    mock_response.usage.output_tokens = 50
    gen._ai.messages.create = AsyncMock(return_value=mock_response)


# ---------------------------------------------------------------------------
# _parse_yaml
# ---------------------------------------------------------------------------

class TestParseYaml:
    def test_clean_yaml(self):
        gen = _make_generator()
        result = gen._parse_yaml(
            "alias: Lights On\ntrigger: []\naction: []"
        )
        assert result["alias"] == "Lights On"

    def test_strips_yaml_code_fence(self):
        gen = _make_generator()
        raw = "```yaml\nalias: test\ntrigger: []\naction: []\n```"
        result = gen._parse_yaml(raw)
        assert result["alias"] == "test"

    def test_strips_plain_code_fence(self):
        gen = _make_generator()
        raw = "```\nalias: test\ntrigger: []\naction: []\n```"
        result = gen._parse_yaml(raw)
        assert result["alias"] == "test"

    def test_raises_on_invalid_yaml(self):
        gen = _make_generator()
        with pytest.raises(YAMLGenerationError, match="YAML parse error"):
            gen._parse_yaml("{{{broken: yaml")

    def test_raises_when_result_is_list_not_dict(self):
        gen = _make_generator()
        with pytest.raises(YAMLGenerationError, match="Expected YAML dict"):
            gen._parse_yaml("- item_one\n- item_two\n")

    def test_raises_when_result_is_string(self):
        gen = _make_generator()
        with pytest.raises(YAMLGenerationError, match="Expected YAML dict"):
            gen._parse_yaml("just a plain string")


# ---------------------------------------------------------------------------
# _load_prompt
# ---------------------------------------------------------------------------

class TestLoadPrompt:
    def test_raises_when_file_missing(self):
        gen = _make_generator()
        with patch("app.ai.yaml_generator.PROMPTS_DIR") as mock_dir:
            mock_path = MagicMock()
            mock_path.exists.return_value = False
            mock_dir.__truediv__ = MagicMock(return_value=mock_path)
            with pytest.raises(YAMLGenerationError, match="Prompt file not found"):
                gen._load_prompt("nonexistent.txt")

    def test_returns_file_content(self):
        gen = _make_generator()
        with patch("app.ai.yaml_generator.PROMPTS_DIR") as mock_dir:
            mock_path = MagicMock()
            mock_path.exists.return_value = True
            mock_path.read_text.return_value = "prompt content {entity_context}"
            mock_dir.__truediv__ = MagicMock(return_value=mock_path)
            result = gen._load_prompt("system.txt")
        assert result == "prompt content {entity_context}"


# ---------------------------------------------------------------------------
# generate_automation
# ---------------------------------------------------------------------------

class TestGenerateAutomation:
    async def test_happy_path_returns_automation_config(self):
        gen = _make_generator()
        yaml_text = (
            "alias: Turn on light\n"
            "trigger:\n  - platform: state\n    entity_id: binary_sensor.door\n"
            "action:\n  - service: light.turn_on\n    target:\n      entity_id: light.sala\n"
        )
        with patch.object(gen, "_load_prompt", return_value="{entity_context}\n{user_request}"):
            _mock_claude(gen, yaml_text)
            result = await gen.generate_automation("turn on light when door opens")

        assert result.alias == "Turn on light"
        assert len(result.trigger) == 1
        assert len(result.action) == 1

    async def test_raises_on_missing_alias(self):
        gen = _make_generator()
        yaml_text = "trigger: []\naction: []\n"  # missing alias
        with patch.object(gen, "_load_prompt", return_value="{entity_context}\n{user_request}"):
            _mock_claude(gen, yaml_text)
            with pytest.raises(YAMLGenerationError, match="schema validation failed"):
                await gen.generate_automation("test")

    async def test_raises_on_claude_api_failure(self):
        gen = _make_generator()
        gen._ai.messages.create = AsyncMock(side_effect=Exception("rate limit"))
        with patch.object(gen, "_load_prompt", return_value="{entity_context}\n{user_request}"):
            with pytest.raises(YAMLGenerationError, match="Claude call failed"):
                await gen.generate_automation("test")

    async def test_fenced_yaml_is_accepted(self):
        gen = _make_generator()
        yaml_text = (
            "```yaml\n"
            "alias: Night mode\n"
            "trigger:\n  - platform: time\n    at: '22:00'\n"
            "action:\n  - service: scene.turn_on\n    target:\n      entity_id: scene.night\n"
            "```"
        )
        with patch.object(gen, "_load_prompt", return_value="{entity_context}\n{user_request}"):
            _mock_claude(gen, yaml_text)
            result = await gen.generate_automation("night mode at 22:00")

        assert result.alias == "Night mode"


# ---------------------------------------------------------------------------
# generate_scene
# ---------------------------------------------------------------------------

class TestGenerateScene:
    async def test_happy_path_returns_scene_config(self):
        gen = _make_generator()
        yaml_text = (
            "name: Morning\n"
            "entities:\n"
            "  light.sala:\n"
            "    state: 'on'\n"
            "    brightness: 128\n"
        )
        with patch.object(gen, "_load_prompt", return_value="{entity_context}\n{user_request}"):
            _mock_claude(gen, yaml_text)
            result = await gen.generate_scene("morning scene with warm lights")

        assert result.name == "Morning"
        assert "light.sala" in result.entities

    async def test_raises_on_missing_name(self):
        gen = _make_generator()
        yaml_text = "entities:\n  light.sala:\n    state: 'on'\n"
        with patch.object(gen, "_load_prompt", return_value="{entity_context}\n{user_request}"):
            _mock_claude(gen, yaml_text)
            with pytest.raises(YAMLGenerationError, match="schema validation failed"):
                await gen.generate_scene("test")

    async def test_raises_on_claude_api_failure(self):
        gen = _make_generator()
        gen._ai.messages.create = AsyncMock(side_effect=Exception("timeout"))
        with patch.object(gen, "_load_prompt", return_value="{entity_context}\n{user_request}"):
            with pytest.raises(YAMLGenerationError, match="Claude call failed"):
                await gen.generate_scene("test")


# ---------------------------------------------------------------------------
# generate_dashboard
# ---------------------------------------------------------------------------

class TestGenerateDashboard:
    async def test_returns_string_without_fences(self):
        gen = _make_generator()
        yaml_text = "```yaml\ntitle: Living Room\ncards: []\n```"
        with patch.object(gen, "_load_prompt", return_value="{entity_context}\n{user_request}"):
            _mock_claude(gen, yaml_text)
            result = await gen.generate_dashboard("dashboard for living room")

        assert isinstance(result, str)
        assert "title: Living Room" in result
        assert "```" not in result

    async def test_no_pydantic_validation_accepts_any_schema(self):
        """Dashboard YAML is not validated with Pydantic — Lovelace schema is open-ended."""
        gen = _make_generator()
        yaml_text = "arbitrary_key: value\ncards:\n  - type: glance\n    entities: []\n"
        with patch.object(gen, "_load_prompt", return_value="{entity_context}\n{user_request}"):
            _mock_claude(gen, yaml_text)
            result = await gen.generate_dashboard("test")

        assert "arbitrary_key: value" in result

    async def test_raises_on_claude_failure(self):
        gen = _make_generator()
        gen._ai.messages.create = AsyncMock(side_effect=Exception("network error"))
        with patch.object(gen, "_load_prompt", return_value="{entity_context}\n{user_request}"):
            with pytest.raises(YAMLGenerationError, match="Claude call failed"):
                await gen.generate_dashboard("test")


# ---------------------------------------------------------------------------
# generate_automation_edit
# ---------------------------------------------------------------------------

class TestGenerateAutomationEdit:
    async def test_returns_updated_automation(self):
        gen = _make_generator()
        current = (
            "alias: Turn on light\n"
            "trigger:\n  - platform: state\n    entity_id: binary_sensor.door\n"
            "action:\n  - service: light.turn_on\n    target:\n      entity_id: light.sala\n"
        )
        updated = (
            "alias: Turn on light\n"
            "trigger:\n  - platform: state\n    entity_id: binary_sensor.door\n"
            "action:\n  - service: light.turn_on\n    target:\n      entity_id: light.sala\n"
            "    data:\n      brightness: 128\n"
        )
        _mock_claude(gen, updated)
        result = await gen.generate_automation_edit(current, "set brightness to 50%")
        assert result.alias == "Turn on light"
        assert result.action[0].get("data", {}).get("brightness") == 128

    async def test_raises_on_invalid_output(self):
        gen = _make_generator()
        _mock_claude(gen, "trigger: []\naction: []\n")  # missing alias
        with pytest.raises(YAMLGenerationError, match="schema validation failed"):
            await gen.generate_automation_edit("alias: test\ntrigger: []\naction: []\n", "break it")

    async def test_raises_on_claude_failure(self):
        gen = _make_generator()
        gen._ai.messages.create = AsyncMock(side_effect=Exception("network error"))
        with pytest.raises(YAMLGenerationError, match="Claude call failed"):
            await gen.generate_automation_edit("alias: x\ntrigger: []\naction: []\n", "add delay")


# ---------------------------------------------------------------------------
# Complex automation structures (schema validation)
# ---------------------------------------------------------------------------

class TestComplexAutomationSchema:
    """Verify AutomationConfig accepts choose/repeat/parallel action structures."""

    async def test_choose_action_accepted(self):
        gen = _make_generator()
        yaml_text = """
alias: Choose test
trigger:
  - platform: state
    entity_id: input_boolean.flag
action:
  - choose:
      - conditions:
          - condition: state
            entity_id: input_boolean.flag
            state: "on"
        sequence:
          - service: light.turn_on
            target:
              entity_id: light.sala
    default:
      - service: light.turn_off
        target:
          entity_id: light.sala
"""
        with patch.object(gen, "_load_prompt", return_value="{entity_context}\n{user_request}"):
            _mock_claude(gen, yaml_text)
            result = await gen.generate_automation("if flag on, turn on light else off")

        assert result.alias == "Choose test"
        action = result.action[0]
        assert "choose" in action

    async def test_repeat_action_accepted(self):
        gen = _make_generator()
        yaml_text = """
alias: Flash light
trigger:
  - platform: event
    event_type: test_event
action:
  - repeat:
      count: 3
      sequence:
        - service: light.turn_on
          target:
            entity_id: light.sala
        - delay: "00:00:01"
        - service: light.turn_off
          target:
            entity_id: light.sala
        - delay: "00:00:01"
"""
        with patch.object(gen, "_load_prompt", return_value="{entity_context}\n{user_request}"):
            _mock_claude(gen, yaml_text)
            result = await gen.generate_automation("flash light 3 times")

        assert result.alias == "Flash light"
        assert "repeat" in result.action[0]

    async def test_parallel_action_accepted(self):
        gen = _make_generator()
        yaml_text = """
alias: Parallel notify
trigger:
  - platform: state
    entity_id: binary_sensor.smoke
    to: "on"
action:
  - parallel:
    - service: notify.mobile_app
      data:
        message: "Smoke detected!"
    - service: light.turn_on
      target:
        entity_id: light.all
      data:
        flash: short
"""
        with patch.object(gen, "_load_prompt", return_value="{entity_context}\n{user_request}"):
            _mock_claude(gen, yaml_text)
            result = await gen.generate_automation("on smoke: notify and flash lights simultaneously")

        assert result.alias == "Parallel notify"
        assert "parallel" in result.action[0]

    async def test_multiple_triggers_accepted(self):
        gen = _make_generator()
        yaml_text = """
alias: Multi trigger
trigger:
  - platform: state
    entity_id: binary_sensor.door
    to: "on"
  - platform: time
    at: "08:00:00"
action:
  - service: light.turn_on
    target:
      entity_id: light.sala
"""
        with patch.object(gen, "_load_prompt", return_value="{entity_context}\n{user_request}"):
            _mock_claude(gen, yaml_text)
            result = await gen.generate_automation("turn on when door opens or at 8am")

        assert len(result.trigger) == 2

    async def test_conditions_block_accepted(self):
        gen = _make_generator()
        yaml_text = """
alias: Conditional light
trigger:
  - platform: state
    entity_id: binary_sensor.motion
    to: "on"
condition:
  - condition: time
    after: "08:00:00"
    before: "22:00:00"
  - condition: state
    entity_id: binary_sensor.someone_home
    state: "on"
action:
  - service: light.turn_on
    target:
      entity_id: light.sala
"""
        with patch.object(gen, "_load_prompt", return_value="{entity_context}\n{user_request}"):
            _mock_claude(gen, yaml_text)
            result = await gen.generate_automation("turn on only when home and between 8-22h")

        assert len(result.condition) == 2
