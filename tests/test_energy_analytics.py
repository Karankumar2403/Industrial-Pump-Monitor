"""Automated tests for energy consumption calculations and cost analytics."""

from datetime import datetime, timedelta
import pandas as pd
import pytest

from src.energy_analytics import EnergyAnalyticsEngine
from src.equipment_simulator import EquipmentConfig


@pytest.fixture
def energy_engine() -> EnergyAnalyticsEngine:
    return EnergyAnalyticsEngine(default_tariff=8.50, currency_symbol="₹")


@pytest.fixture
def pump_config() -> EquipmentConfig:
    return EquipmentConfig(
        equipment_id="P-101",
        name="Boiler Feed Water Pump A",
        equipment_type="Multistage Centrifugal",
        rated_power_kw=75.0,
        rated_flow_m3h=120.0,
        operating_hours_baseline=2000.0,
    )


def test_energy_formula_calculation(energy_engine):
    """Test standard formula: Energy (kWh) = Average Power (kW) × Operating Time (hours)."""
    # 50 kW for 10 hours = 500 kWh
    kwh = energy_engine.calculate_energy(avg_power_kw=50.0, operating_hours=10.0)
    assert kwh == 500.0

    # 72.5 kW for 3.5 hours = 253.75 kWh
    kwh2 = energy_engine.calculate_energy(avg_power_kw=72.5, operating_hours=3.5)
    assert pytest.approx(kwh2, rel=1e-4) == 253.75


def test_energy_cost_calculation(energy_engine):
    """Test standard formula: Cost = Energy (kWh) × Tariff."""
    # 1000 kWh @ ₹8.50/kWh = ₹8,500.00
    cost = energy_engine.calculate_energy_cost(energy_kwh=1000.0)
    assert cost == 8500.0

    # Custom tariff override
    cost_custom = energy_engine.calculate_energy_cost(energy_kwh=1000.0, tariff=10.0)
    assert cost_custom == 10000.0


def test_zero_and_negative_operating_time(energy_engine):
    """Verify that zero or invalid operating time returns 0 without raising errors."""
    assert energy_engine.calculate_energy(avg_power_kw=50.0, operating_hours=0.0) == 0.0
    assert energy_engine.calculate_energy(avg_power_kw=50.0, operating_hours=-5.0) == 0.0
    assert energy_engine.calculate_energy(avg_power_kw=0.0, operating_hours=10.0) == 0.0
    assert energy_engine.calculate_energy_cost(energy_kwh=0.0) == 0.0
    assert energy_engine.calculate_energy_cost(energy_kwh=-10.0) == 0.0


def test_compute_equipment_kpis_with_empty_and_valid_data(energy_engine, pump_config):
    """Test KPI extraction on empty data and populated telemetry."""
    # Empty DataFrame check
    empty_kpi = energy_engine.compute_equipment_kpis(pd.DataFrame(), pump_config)
    assert empty_kpi.total_operating_hours == 0.0
    assert empty_kpi.total_energy_kwh == 0.0
    assert empty_kpi.estimated_cost == 0.0

    # Synthetic populated DataFrame: 24 points at 1 hour each
    now = datetime(2026, 10, 14, 0, 0)
    rows = []
    for i in range(24):
        rows.append({
            "equipment_id": "P-101",
            "operating_status": "Running",
            "power_kw": 70.0,
            "flow_rate_m3h": 120.0,
            "timestamp": now + timedelta(hours=i),
        })
    df_telem = pd.DataFrame(rows)

    kpi = energy_engine.compute_equipment_kpis(df_telem, pump_config)
    assert kpi.total_operating_hours == 24.0
    assert kpi.average_power_kw == 70.0
    # 70 kW * 24 h = 1680 kWh
    assert kpi.total_energy_kwh == 1680.0
    # Cost = 1680 * 8.50 = 14280.0
    assert kpi.estimated_cost == 14280.0
    # Baseline nominal power is 0.90 * 75 kW = 67.5 kW -> 67.5 * 24 = 1620 kWh
    assert kpi.baseline_energy_kwh == 1620.0
    # Excess energy = 1680 - 1620 = 60 kWh
    assert kpi.excess_energy_kwh == 60.0
    assert kpi.excess_cost == 60.0 * 8.50
    assert kpi.is_hypothetical_estimate is True


def test_aggregate_energy_trends(energy_engine):
    """Verify daily aggregation produces resampled energy sums."""
    now = datetime(2026, 10, 14, 0, 0)
    rows = []
    # 48 hours = 2 days
    for i in range(48):
        rows.append({
            "equipment_id": "P-101",
            "operating_status": "Running",
            "power_kw": 50.0,
            "flow_rate_m3h": 100.0,
            "timestamp": now + timedelta(hours=i),
        })
    df = pd.DataFrame(rows)
    df_daily = energy_engine.aggregate_energy_trends(df, freq="1D")

    assert not df_daily.empty
    assert len(df_daily) == 2  # 2 separate days
    assert df_daily.iloc[0]["operating_hours"] == 24
    assert df_daily.iloc[0]["energy_kwh"] == 1200.0
