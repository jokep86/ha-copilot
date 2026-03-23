"""
Progressive context loading for Claude (see ADR-010).

Pass 1: domain list + entity counts → keyword heuristic selects relevant domains.
Pass 2: full entity list for selected domains only.
~40-60% token reduction vs sending all entities.

Cache: entity list in memory, invalidated by WS state_changed events.
Fallback: 5-min TTL if WS disconnects.
"""
from __future__ import annotations

import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.ha.discovery import EntityDiscovery

from app.observability.logger import get_logger

logger = get_logger(__name__)

CACHE_TTL_SECONDS = 300  # 5-min fallback TTL when WS is disconnected

# Keyword → domain(s) heuristic map
_DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "light": ["light", "lamp", "bulb", "luz", "lámpara", "luces"],
    "switch": ["switch", "outlet", "plug", "enchufe", "tomacorriente"],
    "climate": ["climate", "thermostat", "ac", "air", "temperatura", "calefacción", "heater", "cooling", "heating"],
    "sensor": ["sensor", "temperature", "humidity", "pressure", "co2", "temperatura", "humedad"],
    "binary_sensor": ["door", "window", "motion", "puerta", "ventana", "movimiento", "contact", "presence"],
    "cover": ["cover", "blind", "curtain", "shutter", "persiana", "cortina", "garage"],
    "media_player": ["media", "tv", "speaker", "music", "player", "television", "tele", "chromecast", "sonos"],
    "fan": ["fan", "ventilador", "ventilation"],
    "lock": ["lock", "cerradura", "door lock"],
    "camera": ["camera", "cámara", "snapshot"],
    "alarm_control_panel": ["alarm", "security", "alarma", "seguridad"],
    "automation": ["automation", "automatización", "automatización"],
    "scene": ["scene", "escena"],
    "script": ["script", "guión"],
    "input_boolean": ["input", "boolean", "toggle"],
    "person": ["person", "persona", "who", "home", "away"],
}

_DOMAIN_GROUPS = {
    "energy": ["sensor", "utility_meter"],
    "presence": ["person", "device_tracker", "binary_sensor"],
}


def _guess_domains(query: str) -> list[str]:
    """
    Given a natural language query, return the likely relevant HA domains.
    Returns an empty list if the query is domain-agnostic.
    """
    q = query.lower()
    matched: set[str] = set()
    for domain, keywords in _DOMAIN_KEYWORDS.items():
        if any(kw in q for kw in keywords):
            matched.add(domain)
    return list(matched)


class ContextLoader:
    """
    Builds the entity context string to include in Claude prompts.
    Keeps an in-memory cache of entity states with TTL-based fallback.
    """

    def __init__(self, discovery: "EntityDiscovery") -> None:
        self._discovery = discovery
        self._cached_domains: dict[str, int] | None = None
        self._cache_ts: float = 0.0

    async def get_prompt_context(
        self,
        query: str,
        entity_aliases: dict[str, str] | None = None,
        max_entities_per_domain: int = 50,
    ) -> str:
        """
        Build the entity context block for the system prompt.
        Uses domain heuristics to limit what's sent to Claude.
        """
        # Get domain counts (fast, cached)
        domains = await self._get_domain_counts()
        if not domains:
            return "No entities available."

        # Guess which domains the query needs
        wanted = _guess_domains(query)

        # If no match, include the top 5 domains by entity count
        if not wanted:
            wanted = sorted(domains, key=lambda d: domains[d], reverse=True)[:5]

        # Include automation/scene/script always (low count, always useful)
        for always in ("automation", "scene", "script"):
            if always in domains and always not in wanted:
                wanted.append(always)

        lines: list[str] = [f"Available domains: {', '.join(sorted(domains))}"]
        lines.append(f"Entity counts: {', '.join(f'{d}:{n}' for d, n in sorted(domains.items()))}")
        lines.append("")
        lines.append("Entities for your query:")

        for domain in wanted:
            if domain not in domains:
                continue
            entities = await self._discovery.get_entities_by_domain(domain)
            for entity in entities[:max_entities_per_domain]:
                eid = entity.get("entity_id", "")
                state = entity.get("state", "unknown")
                fname = entity.get("attributes", {}).get("friendly_name", eid)
                unit = entity.get("attributes", {}).get("unit_of_measurement", "")
                state_str = f"{state} {unit}".strip()
                lines.append(f"  {eid} | {fname} | {state_str}")

        if entity_aliases:
            lines.append("")
            lines.append("User aliases:")
            for alias, eid in entity_aliases.items():
                lines.append(f"  '{alias}' → {eid}")

        return "\n".join(lines)

    async def _get_domain_counts(self) -> dict[str, int]:
        now = time.monotonic()
        if self._cached_domains is None or (now - self._cache_ts) > CACHE_TTL_SECONDS:
            self._cached_domains = await self._discovery.get_domains()
            self._cache_ts = now
        return self._cached_domains

    def invalidate(self) -> None:
        """Force domain count refresh on next call."""
        self._cached_domains = None
