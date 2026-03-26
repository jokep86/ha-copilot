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
        fuzzy: bool = True,
    ) -> list[dict]:
        """
        Search entities by substring match on entity_id and friendly_name.
        With fuzzy=True (default), also returns close matches using difflib
        when no exact substring match is found (typo tolerance).
        """
        states = await self.get_all_states()
        q = query.lower()

        # Domain filter
        candidates = [
            s for s in states
            if not domain or s.get("entity_id", "").startswith(f"{domain}.")
        ]

        # Exact substring matches first
        exact: list[dict] = []
        for s in candidates:
            eid = s.get("entity_id", "")
            fname = s.get("attributes", {}).get("friendly_name", "")
            if q in eid.lower() or q in fname.lower():
                exact.append(s)

        if exact or not fuzzy:
            return exact

        # Fuzzy fallback: difflib close matches on friendly names and entity ids
        import difflib

        all_names = []
        name_to_state: dict[str, dict] = {}
        for s in candidates:
            eid = s.get("entity_id", "")
            fname = s.get("attributes", {}).get("friendly_name", eid)
            all_names.append(eid)
            name_to_state[eid] = s
            if fname and fname != eid:
                all_names.append(fname.lower())
                name_to_state[fname.lower()] = s

        close = difflib.get_close_matches(q, all_names, n=5, cutoff=0.6)
        seen: set[str] = set()
        fuzzy_results: list[dict] = []
        for match in close:
            s = name_to_state.get(match)
            if s:
                eid = s.get("entity_id", "")
                if eid not in seen:
                    seen.add(eid)
                    fuzzy_results.append(s)

        return fuzzy_results

    async def resolve_entity_id(self, query: str) -> tuple[str | None, str | None]:
        """
        Resolve a user query to a single entity_id.
        Returns (entity_id, None) on success, (None, error_message) on failure.

        Strategy:
        1. Exact match in cache (fast path for correctly-typed entity_ids)
        2. Fuzzy search on entity_id + friendly_name via find_entity()
        3. Multiple fuzzy matches → return the best-ranked one (difflib order)
        """
        states = await self.get_all_states()

        # Fast path: exact entity_id match
        if "." in query:
            for s in states:
                if s.get("entity_id") == query:
                    return query, None

        # Fuzzy search
        matches = await self.find_entity(query, fuzzy=True)
        if not matches:
            return None, f"No entity found matching '{query}'"

        # Return best match; if multiple, caller may log the ambiguity
        return matches[0].get("entity_id", query), None

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
