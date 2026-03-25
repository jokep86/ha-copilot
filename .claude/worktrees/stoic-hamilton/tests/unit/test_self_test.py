"""
Unit tests for StartupSelfTest.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.degradation import ComponentHealth, DegradationMap
from app.core.self_test import StartupSelfTest


@pytest.fixture
def degradation() -> DegradationMap:
    return DegradationMap()


@pytest.fixture
def ha_client() -> MagicMock:
    client = MagicMock()
    client.get_config = AsyncMock(return_value={"version": "2026.3.4"})
    client.get_states = AsyncMock(
        return_value=[
            {"entity_id": "light.sala", "state": "on"},
            {"entity_id": "light.kitchen", "state": "off"},
            {"entity_id": "sensor.temp", "state": "22.5"},
        ]
    )
    return client


@pytest.fixture
def supervisor_client() -> MagicMock:
    client = MagicMock()
    client.get_info = AsyncMock(return_value={"supervisor": "2025.01.0"})
    return client


@pytest.fixture
def db() -> MagicMock:
    db = MagicMock()
    db.db_path = MagicMock()
    db.get_size_bytes = AsyncMock(return_value=1024 * 1024 * 2)  # 2 MB
    return db


@pytest.fixture
def self_test(config, ha_client, supervisor_client, db, degradation) -> StartupSelfTest:
    return StartupSelfTest(
        config=config,
        ha_client=ha_client,
        supervisor_client=supervisor_client,
        db=db,
        degradation=degradation,
    )


@pytest.mark.asyncio
async def test_run_all_healthy(self_test: StartupSelfTest, degradation: DegradationMap) -> None:
    with patch("anthropic.AsyncAnthropic") as mock_anthropic:
        mock_client = AsyncMock()
        mock_client.models.list = AsyncMock(return_value=[])
        mock_anthropic.return_value = mock_client

        results = await self_test.run()

    assert results["ha_version"] == "2026.3.4"
    assert results["supervisor_version"] == "2025.01.0"
    assert results["websocket_ok"] is True
    assert degradation.is_healthy("ha_api")
    assert degradation.is_healthy("supervisor_api")
    assert degradation.is_healthy("database")


@pytest.mark.asyncio
async def test_ha_api_failure_marks_degraded(
    self_test: StartupSelfTest,
    ha_client: MagicMock,
    degradation: DegradationMap,
) -> None:
    ha_client.get_config = AsyncMock(side_effect=Exception("connection refused"))
    ha_client.get_states = AsyncMock(side_effect=Exception("connection refused"))

    with patch("anthropic.AsyncAnthropic"):
        results = await self_test.run()

    assert results["ha_version"] is None
    assert not degradation.is_healthy("ha_api")


@pytest.mark.asyncio
async def test_supervisor_failure_marks_degraded(
    self_test: StartupSelfTest,
    supervisor_client: MagicMock,
    degradation: DegradationMap,
) -> None:
    supervisor_client.get_info = AsyncMock(side_effect=Exception("timeout"))

    with patch("anthropic.AsyncAnthropic"):
        results = await self_test.run()

    assert results["supervisor_version"] is None
    assert not degradation.is_healthy("supervisor_api")


@pytest.mark.asyncio
async def test_entity_counts_aggregated(self_test: StartupSelfTest) -> None:
    with patch("anthropic.AsyncAnthropic"):
        results = await self_test.run()

    counts = results["entity_counts"]
    assert counts["light"] == 2
    assert counts["sensor"] == 1


def test_format_report_all_healthy(self_test: StartupSelfTest, degradation: DegradationMap) -> None:
    # Set all healthy manually
    for comp in degradation.COMPONENTS:
        degradation.set_healthy(comp)

    results = {
        "ha_version": "2026.3.4",
        "supervisor_version": "2025.01.0",
        "websocket_ok": True,
        "claude_ok": True,
        "db_size": "2.0 MB",
        "entity_counts": {"light": 10, "sensor": 5},
    }
    report = self_test.format_report(results)

    assert "HA Copilot v0.1.0" in report
    assert "HA API" in report
    assert "2026.3.4" in report
    assert "15 entities" in report
    assert "🟢" in report


def test_format_report_degraded_components(
    self_test: StartupSelfTest,
    degradation: DegradationMap,
) -> None:
    degradation.set_healthy("telegram")
    degradation.set_healthy("database")
    degradation.set_healthy("websocket")
    degradation.set_unavailable("ha_api", "connection refused")
    degradation.set_unavailable("supervisor_api", "timeout")
    degradation.set_degraded("claude", "rate limited")

    results = {
        "ha_version": None,
        "supervisor_version": None,
        "websocket_ok": True,
        "claude_ok": False,
        "db_size": "1.0 MB",
        "entity_counts": {},
    }
    report = self_test.format_report(results)
    assert "🔴" in report
    assert "unreachable" in report
