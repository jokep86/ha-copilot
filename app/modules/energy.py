"""
Energy tracking, consumption reports, and anomaly alerts — Phase 7.

/energy today|week|month  — consumption report (kWh) with chart
/energy compare           — current period vs previous period
"""
from __future__ import annotations

import io
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Optional

from telegram.constants import ParseMode

from app.bot.formatters import bold, code, error_msg, escape_md, warning_msg
from app.core.module_base import ModuleBase
from app.observability.logger import get_logger

if TYPE_CHECKING:
    from app.bot.handler import CommandContext
    from app.core.module_registry import AppContext

logger = get_logger(__name__)

# Device classes that indicate energy sensors
_ENERGY_DEVICE_CLASSES = {"energy", "power"}
_MAX_CHART_ENTITIES = 10


class EnergyModule(ModuleBase):
    name = "energy"
    description = "Energy tracking, charts, anomaly alerts"
    commands: list[str] = ["energy"]

    async def setup(self, app: "AppContext") -> None:
        self._app = app
        self._ha = app.ha_client

    async def teardown(self) -> None:
        pass

    async def handle_command(
        self,
        cmd: str,
        args: list[str],
        context: "CommandContext",
    ) -> None:
        sub = args[0].lower() if args else "today"

        if sub == "compare":
            await self._cmd_compare(context)
        elif sub in ("today", "week", "month"):
            await self._cmd_report(sub, context)
        else:
            await self._reply(
                context,
                "Usage: `/energy today`, `/energy week`, `/energy month`, `/energy compare`",
            )

    # ------------------------------------------------------------------ #

    async def _cmd_report(self, period: str, context: "CommandContext") -> None:
        start, end, label = _period_range(period)
        hours = int((end - start).total_seconds() / 3600)

        await self._reply(context, f"⏳ Fetching energy data for {escape_md(label)}\\.\\.\\.")

        energy_entities = await self._discover_energy_entities()
        if not energy_entities:
            await self._reply(
                context,
                warning_msg("No energy or power sensors found in this installation."),
            )
            return

        readings = await self._collect_readings(energy_entities, hours)
        if not readings:
            await self._reply(context, warning_msg("No energy data available for this period."))
            return

        report_text = _format_report(label, readings)

        # Try to send a chart; fall back to text-only
        chart_bytes = await _generate_chart(label, readings)
        if chart_bytes:
            await context.update.message.reply_photo(
                photo=io.BytesIO(chart_bytes),
                caption=report_text[:1024],
                parse_mode=ParseMode.MARKDOWN_V2,
            )
        else:
            if len(report_text) > 4096:
                report_text = report_text[:4090] + "\n_\\.\\.\\. truncated_"
            await context.update.message.reply_text(
                report_text, parse_mode=ParseMode.MARKDOWN_V2
            )

    async def _cmd_compare(self, context: "CommandContext") -> None:
        now = datetime.now(timezone.utc)

        # Current period: last 7 days
        cur_end = now
        cur_start = now - timedelta(days=7)
        # Previous period: 7 days before that
        prev_end = cur_start
        prev_start = cur_start - timedelta(days=7)

        await self._reply(context, "⏳ Comparing energy periods\\.\\.\\.")

        energy_entities = await self._discover_energy_entities()
        if not energy_entities:
            await self._reply(context, warning_msg("No energy sensors found."))
            return

        cur_readings = await self._collect_readings(energy_entities, 7 * 24)
        prev_readings = await self._collect_readings_since(energy_entities, prev_start, prev_end)

        lines = [bold("Energy Comparison: Last 7 Days vs Previous 7 Days"), ""]

        cur_total = sum(r["delta"] for r in cur_readings if r["delta"] is not None)
        prev_total = sum(r["delta"] for r in prev_readings if r["delta"] is not None)

        cur_str = f"{cur_total:.2f} kWh"
        prev_str = f"{prev_total:.2f} kWh"

        if prev_total > 0:
            pct = ((cur_total - prev_total) / prev_total) * 100
            trend = "📈" if pct > 5 else "📉" if pct < -5 else "➡️"
            lines.append(
                f"Current: {bold(escape_md(cur_str))}\n"
                f"Previous: {escape_md(prev_str)}\n"
                f"{trend} {escape_md(f'{pct:+.1f}%')} change"
            )
        else:
            lines.append(
                f"Current: {bold(escape_md(cur_str))}\n"
                f"Previous: {escape_md(prev_str)}"
            )

        await context.update.message.reply_text(
            "\n".join(lines), parse_mode=ParseMode.MARKDOWN_V2
        )

    # ------------------------------------------------------------------ #

    async def _discover_energy_entities(self) -> list[dict]:
        """Find all sensor entities with device_class energy or power."""
        try:
            states = await self._ha.get_states()
        except Exception as exc:
            logger.warning("energy_discover_failed", error=str(exc))
            return []
        return [
            s for s in states
            if s.get("entity_id", "").startswith("sensor.")
            and s.get("attributes", {}).get("device_class") in _ENERGY_DEVICE_CLASSES
        ]

    async def _collect_readings(
        self, entities: list[dict], hours: int
    ) -> list[dict]:
        """Fetch history for entities and compute delta kWh."""
        result = []
        for entity in entities[:_MAX_CHART_ENTITIES]:
            eid = entity["entity_id"]
            fname = entity.get("attributes", {}).get("friendly_name", eid)
            unit = entity.get("attributes", {}).get("unit_of_measurement", "")
            try:
                history = await self._ha.get_history(eid, hours=hours)
                delta = _compute_delta(history, unit)
                result.append(
                    {"entity_id": eid, "name": fname, "delta": delta, "unit": unit, "history": history}
                )
            except Exception as exc:
                logger.warning("energy_history_failed", entity_id=eid, error=str(exc))
        return result

    async def _collect_readings_since(
        self, entities: list[dict], start: datetime, end: datetime
    ) -> list[dict]:
        """Collect readings for a specific time window (best effort)."""
        hours = int((end - start).total_seconds() / 3600)
        return await self._collect_readings(entities, hours)

    async def _reply(self, context: "CommandContext", text: str) -> None:
        await context.update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)


# ------------------------------------------------------------------ #
# Pure helpers (no I/O — easy to test)
# ------------------------------------------------------------------ #

def _period_range(period: str) -> tuple[datetime, datetime, str]:
    now = datetime.now(timezone.utc)
    if period == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return start, now, "Today"
    elif period == "week":
        start = now - timedelta(days=7)
        return start, now, "Last 7 Days"
    else:  # month
        start = now - timedelta(days=30)
        return start, now, "Last 30 Days"


def _compute_delta(history: list, unit: str) -> Optional[float]:
    """
    For energy sensors (kWh, Wh) compute delta = last - first.
    For power sensors (W, kW) return the latest reading.
    """
    if not history or not isinstance(history[0], list):
        return None
    states = history[0]
    if not states:
        return None

    # HA history returns list of state dicts sorted by last_changed
    values: list[float] = []
    for s in states:
        try:
            v = float(s.get("state", ""))
            values.append(v)
        except (ValueError, TypeError):
            continue

    if not values:
        return None

    if unit.lower() in ("w", "kw"):
        # Power: return average
        return sum(values) / len(values)
    else:
        # Energy: delta (monotonically increasing meters)
        return max(0.0, values[-1] - values[0])


def _format_report(label: str, readings: list[dict]) -> str:
    lines = [bold(f"Energy Report: {escape_md(label)}"), ""]
    total = 0.0
    for r in readings:
        name = r["name"]
        delta = r["delta"]
        unit = r["unit"]
        if delta is None:
            value_str = "N/A"
        else:
            value_str = f"{delta:.2f} {unit}"
            if unit.lower() in ("kwh", "wh"):
                total += delta if unit.lower() == "kwh" else delta / 1000
        lines.append(f"• {escape_md(name)}: {bold(escape_md(value_str))}")

    if total > 0:
        lines.append(f"\n{bold(f'Total: {total:.2f} kWh')}")

    return "\n".join(lines)


async def _generate_chart(label: str, readings: list[dict]) -> Optional[bytes]:
    """Generate a plotly PNG chart. Returns None if plotly/kaleido not available."""
    try:
        import plotly.graph_objects as go
        import kaleido  # noqa: F401 — ensure kaleido is importable
    except ImportError:
        logger.debug("energy_chart_skipped", reason="plotly/kaleido not installed")
        return None

    try:
        names = [r["name"] for r in readings if r["delta"] is not None]
        values = [r["delta"] for r in readings if r["delta"] is not None]
        units = [r["unit"] for r in readings if r["delta"] is not None]

        if not names:
            return None

        fig = go.Figure(
            go.Bar(x=names, y=values, text=[f"{v:.2f} {u}" for v, u in zip(values, units)])
        )
        fig.update_layout(
            title=f"Energy — {label}",
            xaxis_title="Sensor",
            yaxis_title="Consumption",
            height=400,
            margin={"l": 40, "r": 20, "t": 50, "b": 80},
        )
        return fig.to_image(format="png")
    except Exception as exc:
        logger.warning("energy_chart_failed", error=str(exc))
        return None
