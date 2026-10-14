"""Automated tests for equipment simulator and physical constraints."""

from datetime import datetime
import pytest

from src.equipment_simulator import (
    EquipmentConfig,
    FaultScenario,
    OperatingStatus,
    PumpSimulator,
    get_default_fleet_configs,
)


@pytest.fixture
def base_config() -> EquipmentConfig:
    return EquipmentConfig(
        equipment_id="P-TEST",
        name="Test Centrifugal Pump",
        equipment_type="End-Suction Centrifugal",
        rated_power_kw=50.0,
        rated_flow_m3h=100.0,
        nominal_temp_c=60.0,
        nominal_vibration_mms=1.8,
        ambient_temp_c=28.0,
        operating_hours_baseline=1000.0,
        service_interval_hours=4000.0,
    )


def test_deterministic_reproducible_seed(base_config):
    """Verify that identical random seeds produce identical telemetry."""
    sim1 = PumpSimulator(base_config, seed=12345)
    sim2 = PumpSimulator(base_config, seed=12345)
    ts = datetime(2026, 10, 14, 12, 0)

    pt1 = sim1.generate_point(ts, FaultScenario.NORMAL_OPERATION)
    pt2 = sim2.generate_point(ts, FaultScenario.NORMAL_OPERATION)

    assert pt1.power_kw == pt2.power_kw
    assert pt1.vibration_mms == pt2.vibration_mms
    assert pt1.temperature_c == pt2.temperature_c
    assert pt1.flow_rate_m3h == pt2.flow_rate_m3h


def test_normal_operation_physics(base_config):
    """Test that normal operation stays within expected design envelopes."""
    sim = PumpSimulator(base_config, seed=42)
    ts = datetime(2026, 10, 14, 12, 0)
    pt = sim.generate_point(ts, FaultScenario.NORMAL_OPERATION, delta_hours=1.0)

    assert pt.operating_status == OperatingStatus.RUNNING.value
    assert 40.0 <= pt.power_kw <= 55.0
    assert 90.0 <= pt.flow_rate_m3h <= 110.0
    assert 55.0 <= pt.temperature_c <= 65.0
    assert 1.4 <= pt.vibration_mms <= 2.2
    assert pt.is_synthetic is True


def test_unexpected_stoppage_constraints(base_config):
    """Verify that stopped equipment enforces power=0, flow=0, and ambient decay."""
    sim = PumpSimulator(base_config, seed=42)
    ts = datetime(2026, 10, 14, 12, 0)
    pt = sim.generate_point(ts, FaultScenario.UNEXPECTED_EQUIPMENT_STOPPAGE, delta_hours=1.0)

    assert pt.operating_status == OperatingStatus.STOPPED.value
    assert pt.power_kw == 0.0
    assert pt.flow_rate_m3h == 0.0
    assert pt.vibration_mms < 0.5  # Ambient vibration baseline only
    assert pt.temperature_c < 36.0 # Near ambient temperature


def test_zero_operating_time_delta(base_config):
    """Verify that a zero delta interval does not accumulate operating hours."""
    sim = PumpSimulator(base_config, seed=42)
    initial_hours = sim.current_hours
    initial_energy = sim.cumulative_energy_kwh

    ts = datetime(2026, 10, 14, 12, 0)
    pt = sim.generate_point(ts, FaultScenario.NORMAL_OPERATION, delta_hours=0.0)

    assert pt.operating_hours == initial_hours
    assert pt.energy_kwh == initial_energy


def test_cumulative_energy_accumulation(base_config):
    """Verify energy accumulates in accordance with power and time."""
    sim = PumpSimulator(base_config, seed=42)
    initial_energy = sim.cumulative_energy_kwh
    ts = datetime(2026, 10, 14, 12, 0)

    pt1 = sim.generate_point(ts, FaultScenario.NORMAL_OPERATION, delta_hours=2.0)
    expected_added = pt1.power_kw * 2.0
    assert pytest.approx(pt1.energy_kwh, rel=1e-3) == initial_energy + expected_added


def test_increasing_vibration_trend_scenario(base_config):
    """Verify that trend progression increments vibration value sequentially."""
    sim = PumpSimulator(base_config, seed=42)
    ts = datetime(2026, 10, 14, 12, 0)

    p0 = sim.generate_point(ts, FaultScenario.INCREASING_VIBRATION_TREND, trend_step=0)
    p5 = sim.generate_point(ts, FaultScenario.INCREASING_VIBRATION_TREND, trend_step=5)
    p15 = sim.generate_point(ts, FaultScenario.INCREASING_VIBRATION_TREND, trend_step=15)

    assert p5.vibration_mms > p0.vibration_mms
    assert p15.vibration_mms > p5.vibration_mms
    assert p15.vibration_mms >= 4.5  # Reaches critical severity tier


def test_fleet_generation():
    """Verify default fleet configs instantiate all required pumps."""
    fleet = get_default_fleet_configs()
    assert "P-101" in fleet
    assert "P-102" in fleet
    assert "P-103" in fleet
    assert "P-104" in fleet
    assert len(fleet) == 4
