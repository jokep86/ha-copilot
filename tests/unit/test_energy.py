"""
Unit tests for EnergyModule and energy helpers.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
import pytest

from app.modules.energy import (
    EnergyModule,
    _period_range,
    _compute_delta,
    _format_report,
)


def _energy_entity(eid="sensor.energy_main", device_class="energy", unit="kWh"):
    return {
        "entity_id": eid,
        "state": "123.5",
        "attributes": {
            "friendly_name": eid.split(".")[-1],
            "device_class": device_class,
            "unit_of_measurement": unit,
        },
    }


def _app(states=None, history=None):
    app = MagicMock()
    app.ha_client.get_states = AsyncMock(return_value=states or [])
    app.ha_client.get_history = AsyncMock(
        return_value=history
        or [
            [
                {"state": "100.0", "last_changed": "2026-03-24T00:00:00Z"},
                {"state": "105.0", "last_changed": "2026-03-24T12:00:00Z"},
                {"state": "110.0", "last_changed": "2026-03-24T23:00:00Z"},
            ]
        ]
    )
    return app


def _context():
    ctx = MagicMock()
    ctx.update.message.reply_text = AsyncMock()
    ctx.update.message.reply_photo = AsyncMock()
    return ctx


class TestEnergyHelpers:
    def test_period_range_today(self):
        start, end, label = _period_range("today")
        assert label == "Today"
        assert start <= end
        # Today starts at midnight
        assert start.hour == 0

    def test_period_range_week(self):
        start, end, label = _period_range("week")
        assert label == "Last 7 Days"
        delta = end - start
        assert 6 <= delta.days <= 7

    def test_period_range_month(self):
        _, _, label = _period_range("month")
        assert label == "Last 30 Days"

    def test_compute_delta_kwh(self):
        history = [[
            {"state": "100.0"},
            {"state": "110.0"},
            {"state": "115.0"},
        ]]
        assert _compute_delta(history, "kWh") == pytest.approx(15.0)

    def test_compute_delta_empty(self):
        assert _compute_delta([], "kWh") is None
        assert _compute_delta([[]], "kWh") is None

    def test_compute_delta_power_averages(self):
        history = [[
            {"state": "100.0"},
            {"state": "200.0"},
        ]]
        result = _compute_delta(history, "W")
        assert result == pytest.approx(150.0)

    def test_compute_delta_no_numeric(self):
        history = [[
            {"state": "unavailable"},
            {"state": "unknown"},
        ]]
        assert _compute_delta(history, "kWh") is None

    def test_format_report(self):
        readings = [
            {"name": "Main Meter", "delta": 12.5, "unit": "kWh", "history": []},
            {"name": "Solar", "delta": 3.0, "unit": "kWh", "history": []},
        ]
        text = _format_report("Today", readings)
        assert "Main Meter" in text
        # MarkdownV2-escaped: 12.50 → 12\.50 (or 12\\.50 in raw string)
        assert "12" in text
        assert "Total" in text


class TestEnergyModule:
    def test_commands(self):
        assert "energy" in EnergyModule.commands

    async def test_no_energy_sensors(self):
        m = EnergyModule()
        # No sensors with energy device class
        await m.setup(_app(states=[
            {"entity_id": "light.sala", "state": "on", "attributes": {}}
        ]))
        ctx = _context()
        await m.handle_command("energy", ["today"], ctx)
        # Should send 2 messages: "fetching..." and "no sensors found"
        assert ctx.update.message.reply_text.call_count == 2
        final = ctx.update.message.reply_text.call_args_list[-1][0][0]
        assert "no energy" in final.lower() or "no power" in final.lower() or "not found" in final.lower()

    async def test_today_with_energy_sensor(self):
        m = EnergyModule()
        await m.setup(_app(states=[_energy_entity()]))
        ctx = _context()
        await m.handle_command("energy", ["today"], ctx)
        # At minimum 1 "fetching..." text reply; report goes to reply_text or reply_photo
        total_calls = (
            ctx.update.message.reply_text.call_count
            + ctx.update.message.reply_photo.call_count
        )
        assert total_calls >= 2

    async def test_invalid_subcommand(self):
        m = EnergyModule()
        await m.setup(_app())
        ctx = _context()
        await m.handle_command("energy", ["badcmd"], ctx)
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "usage" in text.lower()

    async def test_compare_command(self):
        m = EnergyModule()
        await m.setup(_app(states=[_energy_entity()]))
        ctx = _context()
        await m.handle_command("energy", ["compare"], ctx)
        # 2+ calls: thinking + result
        assert ctx.update.message.reply_text.call_count >= 2
