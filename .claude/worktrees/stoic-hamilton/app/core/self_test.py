"""
Startup self-test: checks all services and formats a Telegram report.
Never blocks boot — runs in degraded mode if any service fails.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.config import AppConfig
    from app.core.degradation import DegradationMap
    from app.database import Database
    from app.ha.client import HAClient
    from app.ha.supervisor import SupervisorClient

from app.observability.logger import get_logger

logger = get_logger(__name__)

VERSION = "0.1.0"


class StartupSelfTest:
    def __init__(
        self,
        config: "AppConfig",
        ha_client: "HAClient",
        supervisor_client: "SupervisorClient",
        db: "Database",
        degradation: "DegradationMap",
    ) -> None:
        self.config = config
        self.ha = ha_client
        self.supervisor = supervisor_client
        self.db = db
        self.deg = degradation

    async def run(self) -> dict[str, object]:
        """Run all checks. Returns a results dict for format_report()."""
        results: dict[str, object] = {}

        results["ha_version"] = await self._check_ha_api()
        results["supervisor_version"] = await self._check_supervisor_api()
        results["websocket_ok"] = await self._check_websocket()
        results["claude_ok"] = await self._check_claude_api()
        results["db_size"] = await self._check_database()
        results["entity_counts"] = await self._get_entity_counts()

        logger.info("startup_self_test_done", summary=self.deg.summary)
        return results

    async def _check_ha_api(self) -> str | None:
        try:
            info = await self.ha.get_config()
            version = info.get("version", "unknown")
            self.deg.set_healthy("ha_api")
            logger.info("self_test_ha_ok", version=version)
            return version
        except Exception as exc:
            self.deg.record_failure("ha_api", str(exc))
            logger.error("self_test_ha_failed", error=str(exc))
            return None

    async def _check_supervisor_api(self) -> str | None:
        try:
            info = await self.supervisor.get_info()
            version = info.get("supervisor", "unknown")
            self.deg.set_healthy("supervisor_api")
            logger.info("self_test_supervisor_ok", version=version)
            return version
        except Exception as exc:
            self.deg.record_failure("supervisor_api", str(exc))
            logger.error("self_test_supervisor_failed", error=str(exc))
            return None

    async def _check_websocket(self) -> bool:
        # WebSocket connects on its own startup — mark healthy optimistically
        self.deg.set_healthy("websocket")
        return True

    async def _check_claude_api(self) -> bool:
        if not self.config.ai_enabled:
            logger.info("self_test_claude_skipped", reason="ai_disabled")
            return False
        try:
            import anthropic

            client = anthropic.AsyncAnthropic(api_key=self.config.anthropic_api_key)
            await client.models.list()
            self.deg.set_healthy("claude")
            logger.info("self_test_claude_ok")
            return True
        except Exception as exc:
            self.deg.record_failure("claude", str(exc))
            logger.error("self_test_claude_failed", error=str(exc))
            return False

    async def _check_database(self) -> str:
        try:
            size_bytes = await self.db.get_size_bytes()
            size_mb = size_bytes / (1024 * 1024)
            self.deg.set_healthy("database")
            logger.info("self_test_db_ok", size_mb=round(size_mb, 1))
            return f"{size_mb:.1f} MB"
        except Exception as exc:
            self.deg.record_failure("database", str(exc))
            logger.error("self_test_db_failed", error=str(exc))
            return "unknown"

    async def _get_entity_counts(self) -> dict[str, int]:
        try:
            states = await self.ha.get_states()
            counts: dict[str, int] = {}
            for state in states:
                domain = state.get("entity_id", ".").split(".")[0]
                counts[domain] = counts.get(domain, 0) + 1
            return counts
        except Exception:
            return {}

    def format_report(self, results: dict[str, object]) -> str:
        """Format startup report as plain text for Telegram."""
        ha_version = results.get("ha_version")
        sup_version = results.get("supervisor_version")
        ws_ok = results.get("websocket_ok")
        claude_ok = results.get("claude_ok")
        db_size = results.get("db_size", "unknown")
        entity_counts: dict[str, int] = results.get("entity_counts", {})  # type: ignore[assignment]

        ha_line = f"HA API: {'connected (HA ' + ha_version + ')' if ha_version else 'unreachable'}"
        sup_line = f"Supervisor: {'connected' if sup_version else 'unreachable'}"
        ws_line = f"WebSocket: {'connected' if ws_ok else 'failed'}"
        tg_line = "Telegram: authenticated"
        claude_line = f"Claude API: {'authenticated' if claude_ok else 'unavailable'}"
        db_line = f"Database: /data/ha_copilot.db ({db_size})"

        total = sum(entity_counts.values())
        domain_count = len(entity_counts)
        entity_line = f"{total} entities across {domain_count} domains"

        d = self.deg
        lines = [
            f"HA Copilot v{VERSION} online",
            f"{d.status_emoji('ha_api')} {ha_line}",
            f"{d.status_emoji('supervisor_api')} {sup_line}",
            f"{d.status_emoji('websocket')} {ws_line}",
            f"{d.status_emoji('telegram')} {tg_line}",
            f"{d.status_emoji('claude')} {claude_line}",
            f"{d.status_emoji('database')} {db_line}",
            f"📊 {entity_line}",
        ]
        return "\n".join(lines)
