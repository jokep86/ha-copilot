"""
Dynamic domain/entity/service discovery (see ADR-006).
No hardcoded domain list — supports any HA integration automatically.
Phase 1: simple in-memory cache with full-refresh.
Phase 2: WS-driven invalidation (state_changed → update single entity).
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from app.ha.client import HAClient

from app.observability.logger import get_logger

logger = get_logger(__name__)


class EntityDiscovery:
    def __init__(self, ha_client: "HAClient") -> None:
        self.ha = ha_client
        self._cache: Optional[list[dict]] = None

    async def get_all_states(self, force_refresh: bool = False) -> list[dict]:
        """Return all entity states. Uses in-memory cache."""
        if self._cache is None or force_refresh:
            self._cache = await self.ha.get_states()
            logger.debug("entity_cache_refreshed", count=len(self._cache))
        return self._cache

    async def get_domains(self) -> dict[str, int]:
        """Return {domain: entity_count} mapping."""
        states = await self.get_all_states()
        counts: dict[str, int] = {}
        for s in states:
            domain = s.get("entity_id", ".").split(".")[0]
            counts[domain] = counts.get(domain, 0) + 1
        return counts

    async def get_entities_by_domain(self, domain: str) -> list[dict]:
        states = await self.get_all_states()
        return [s for s in states if s.get("entity_id", "").startswith(f"{domain}.")]

    async def find_entity(
        self,
        query: str,
        domain: Optional[str] = None,
    ) -> list[dict]:
        """
        Simple substring search on entity_id and friendly_name.
        Phase 2: add fuzzy matching.
        """
        states = await self.get_all_states()
        q = query.lower()
        results = []
        for s in states:
            eid = s.get("entity_id", "")
            fname = s.get("attributes", {}).get("friendly_name", "")
            if domain and not eid.startswith(f"{domain}."):
                continue
            if q in eid.lower() or q in fname.lower():
                results.append(s)
        return results

    def invalidate(self, entity_id: Optional[str] = None) -> None:
        """
        Invalidate cache entry.
        entity_id=None: full refresh on next access.
        entity_id=<id>: remove just that entry (Phase 2 WS integration).
        """
        if entity_id is None:
            self._cache = None
        elif self._cache is not None:
            self._cache = [s for s in self._cache if s.get("entity_id") != entity_id]
