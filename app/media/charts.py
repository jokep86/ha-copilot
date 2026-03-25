"""
Plotly history chart generator.
Converts HA entity history into a PNG image for Telegram.
"""
from __future__ import annotations

from typing import Optional

from app.observability.logger import get_logger

logger = get_logger(__name__)


class ChartError(Exception):
    pass


def generate_history_chart(
    entity_id: str,
    friendly_name: str,
    history: list,
    unit: str = "",
    hours: int = 24,
) -> Optional[bytes]:
    """
    Generate a plotly line chart PNG from HA state history.
    Returns PNG bytes, or None if plotly/kaleido is not installed.
    Raises ChartError on unexpected failures.
    """
    try:
        import plotly.graph_objects as go
        import kaleido  # noqa: F401
    except ImportError:
        logger.debug("chart_skipped", reason="plotly/kaleido not installed")
        return None

    try:
        # HA history returns list[list[state_dict]] — unwrap outer list
        if history and isinstance(history[0], list):
            states = history[0]
        else:
            states = history

        timestamps = []
        values: list[float] = []
        for s in states:
            try:
                v = float(s.get("state", ""))
            except (ValueError, TypeError):
                continue
            ts = s.get("last_changed") or s.get("last_updated", "")
            timestamps.append(ts)
            values.append(v)

        if not values:
            raise ChartError(f"No numeric states for entity '{entity_id}'")

        label = f"{friendly_name} ({unit})" if unit else friendly_name
        fig = go.Figure(
            go.Scatter(
                x=timestamps,
                y=values,
                mode="lines+markers",
                name=label,
                line={"width": 2},
            )
        )
        fig.update_layout(
            title=f"{friendly_name} — last {hours}h",
            xaxis_title="Time",
            yaxis_title=unit or "Value",
            height=400,
            margin={"l": 50, "r": 20, "t": 50, "b": 60},
        )
        return fig.to_image(format="png")

    except ChartError:
        raise
    except Exception as exc:
        raise ChartError(f"Chart generation failed: {exc}") from exc
