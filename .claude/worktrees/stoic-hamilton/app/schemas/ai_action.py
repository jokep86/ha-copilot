"""
AI response schemas: AIAction and AIResponse.
All Claude responses are validated against these models before execution.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class ActionType(str, Enum):
    CALL_SERVICE = "call_service"
    GET_STATE = "get_state"
    LIST_ENTITIES = "list_entities"
    CREATE_AUTOMATION = "create_automation"
    EDIT_AUTOMATION = "edit_automation"
    DELETE_AUTOMATION = "delete_automation"
    TOGGLE_AUTOMATION = "toggle_automation"
    TRIGGER_AUTOMATION = "trigger_automation"
    CREATE_SCENE = "create_scene"
    ACTIVATE_SCENE = "activate_scene"
    DELETE_SCENE = "delete_scene"
    SYSTEM_INFO = "system_info"
    UNKNOWN = "unknown"
    CLARIFICATION_NEEDED = "clarification_needed"


class AIAction(BaseModel):
    action_type: ActionType
    domain: Optional[str] = None
    service: Optional[str] = None
    entity_id: Optional[str] = None
    entity_ids: list[str] = Field(default_factory=list)
    service_data: dict[str, Any] = Field(default_factory=dict)
    yaml_payload: Optional[str] = None
    message: Optional[str] = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class AIResponse(BaseModel):
    actions: list[AIAction]
    raw_response: str
    prompt_version: str
    model: str
    input_tokens: int
    output_tokens: int
    trace_id: str
    from_cache: bool = False
