"""Automated tests for health monitoring engine and diagnostic rule checks."""

from datetime import datetime
import pytest

from src.equipment_simulator import (
    DiagnosticStatus,
    EquipmentConfig,
    EquipmentTelemetry,
    FaultScenario,
    OperatingStatus,
)
from src.health_monitor import (
    AlertSeverity,
    ConditionType,
    HealthMonitoringEngine,
    Thresholds,
)


@pytest.fixture
def pump_config() -> EquipmentConfig:
    return EquipmentConfig(
        equipment_id="P-101",
        name="Boiler Feed Water Pump A",
        equipment_type="Multistage Centrifugal",
        rated_power_kw=75.0,
        rated_flow_m3h=120.0,
        nominal_temp_c=65.0,
        nominal_vibration_mms=1.9,
        operating_hours_baseline=3000.0,
        service_interval_hours=4000.0,
    )


@pytest.fixture
def health_engine() -> HealthMonitoringEngine:
    th = Thresholds(
        vibration_warning_mms=2.80,
        vibration_critical_mms=4.50,
        temp_warning_c=75.0,
        temp_critical_c=85.0,
        power_overload_ratio=1.15,
        hours_service_limit=4000.0,
        trend_min_points=4,
        trend_slope_threshold=0.10,
    )
    return HealthMonitoringEngine(th)


def create_telemetry(
    config: EquipmentConfig,
    status: str = OperatingStatus.RUNNING.value,
    temp_c: float = 62.0,
    vib_mms: float = 1.8,
    power_kw: float = 68.0,
    hours: float = 3200.0,
    scenario: str = "Normal Operation",
    diag_status: str = "Normal",
    timestamp: datetime = datetime(2026, 10, 14, 10, 0),
) -> EquipmentTelemetry:
    return EquipmentTelemetry(
        equipment_id=config.equipment_id,
        name=config.name,
        equipment_type=config.equipment_type,
        operating_status=status,
        operating_hours=hours,
        power_kw=power_kw,
        energy_kwh=10000.0,
        temperature_c=temp_c,
        vibration_mms=vib_mms,
        flow_rate_m3h=118.0,
        timestamp=timestamp,
        maintenance_status="Normal",
        current_diagnostic_status=diag_status,
        simulation_scenario=scenario,
    )


def test_temperature_warning_and_critical_limits(pump_config, health_engine):
    """Verify temperature alerts trigger precisely at warning and critical limits."""
    # Normal temp
    t_normal = create_telemetry(pump_config, temp_c=72.0)
    alerts = health_engine.evaluate_telemetry(t_normal, pump_config)
    assert not any(a.condition == ConditionType.HIGH_TEMPERATURE for a in alerts)

    # Warning temp (78°C >= 75°C)
    t_warn = create_telemetry(pump_config, temp_c=78.0)
    alerts_w = health_engine.evaluate_telemetry(t_warn, pump_config)
    temp_warns = [a for a in alerts_w if a.condition == ConditionType.HIGH_TEMPERATURE]
    assert len(temp_warns) == 1
    assert temp_warns[0].severity == AlertSeverity.WARNING

    # Critical temp (88°C >= 85°C)
    t_crit = create_telemetry(pump_config, temp_c=88.0)
    alerts_c = health_engine.evaluate_telemetry(t_crit, pump_config)
    temp_crits = [a for a in alerts_c if a.condition == ConditionType.HIGH_TEMPERATURE]
    assert len(temp_crits) == 1
    assert temp_crits[0].severity == AlertSeverity.CRITICAL


def test_vibration_iso_warning_and_critical_limits(pump_config, health_engine):
    """Verify vibration triggers ISO Zone C (warning) and Zone D (critical) alerts."""
    # Zone A/B Normal (< 2.80 mm/s)
    t_normal = create_telemetry(pump_config, vib_mms=2.10)
    alerts_n = health_engine.evaluate_telemetry(t_normal, pump_config)
    assert not any(a.condition == ConditionType.HIGH_VIBRATION for a in alerts_n)

    # Zone C Warning (3.50 mm/s)
    t_warn = create_telemetry(pump_config, vib_mms=3.50)
    alerts_w = health_engine.evaluate_telemetry(t_warn, pump_config)
    vib_warns = [a for a in alerts_w if a.condition == ConditionType.HIGH_VIBRATION]
    assert len(vib_warns) == 1
    assert vib_warns[0].severity == AlertSeverity.WARNING

    # Zone D Critical (5.20 mm/s)
    t_crit = create_telemetry(pump_config, vib_mms=5.20)
    alerts_c = health_engine.evaluate_telemetry(t_crit, pump_config)
    vib_crits = [a for a in alerts_c if a.condition == ConditionType.HIGH_VIBRATION]
    assert len(vib_crits) == 1
    assert vib_crits[0].severity == AlertSeverity.CRITICAL


def test_increasing_vibration_trend_detection(pump_config, health_engine):
    """Verify linear regression slope detects progressive vibration degradation."""
    # Steady sequence: no trend
    flat_history = [1.8, 1.85, 1.79, 1.82, 1.81]
    is_trending, slope = health_engine.detect_vibration_trend(flat_history)
    assert is_trending is False

    # Rapid upward degradation: +0.25 mm/s each step
    rising_history = [2.0, 2.3, 2.6, 2.9, 3.2]
    is_trending_up, slope_up = health_engine.detect_vibration_trend(rising_history)
    assert is_trending_up is True
    assert slope_up >= 0.20

    t_trend = create_telemetry(pump_config, vib_mms=3.2)
    alerts = health_engine.evaluate_telemetry(t_trend, pump_config, vibration_history=rising_history)
    trend_alerts = [a for a in alerts if a.condition == ConditionType.VIBRATION_TREND_UPWARD]
    assert len(trend_alerts) == 1
    assert trend_alerts[0].severity == AlertSeverity.WARNING


def test_excessive_operating_hours(pump_config, health_engine):
    """Verify alert when operating hours exceed major service overhaul interval."""
    t_under = create_telemetry(pump_config, hours=3900.0)
    alerts_under = health_engine.evaluate_telemetry(t_under, pump_config)
    assert not any(a.condition == ConditionType.EXCESSIVE_OPERATING_HOURS for a in alerts_under)

    t_over = create_telemetry(pump_config, hours=4150.0)
    alerts_over = health_engine.evaluate_telemetry(t_over, pump_config)
    hours_alerts = [a for a in alerts_over if a.condition == ConditionType.EXCESSIVE_OPERATING_HOURS]
    assert len(hours_alerts) == 1


def test_abnormal_energy_overload(pump_config, health_engine):
    """Verify alert when power draw exceeds baseline ratio threshold (15% overload)."""
    # Rated 75 kW * 1.15 = 86.25 kW threshold
    t_normal_pwr = create_telemetry(pump_config, power_kw=72.0)
    alerts_n = health_engine.evaluate_telemetry(t_normal_pwr, pump_config)
    assert not any(a.condition == ConditionType.ABNORMAL_ENERGY for a in alerts_n)

    t_overload = create_telemetry(pump_config, power_kw=92.0)
    alerts_ov = health_engine.evaluate_telemetry(t_overload, pump_config)
    pwr_alerts = [a for a in alerts_ov if a.condition == ConditionType.ABNORMAL_ENERGY]
    assert len(pwr_alerts) == 1


def test_unexpected_stoppage_detection(pump_config, health_engine):
    """Verify unexpected stoppage triggers critical alarm with root causes."""
    t_stopped = create_telemetry(
        pump_config,
        status=OperatingStatus.STOPPED.value,
        power_kw=0.0,
        scenario="Unexpected Equipment Stoppage",
        diag_status="Critical",
    )
    alerts = health_engine.evaluate_telemetry(t_stopped, pump_config)
    stop_alerts = [a for a in alerts if a.condition == ConditionType.UNEXPECTED_STOPPAGE]
    assert len(stop_alerts) == 1
    assert stop_alerts[0].severity == AlertSeverity.CRITICAL


def test_alert_deduplication_and_recovery(pump_config, health_engine):
    """Verify engine does not produce duplicate alerts and clears them on recovery."""
    ts1 = datetime(2026, 10, 14, 10, 0)
    ts2 = datetime(2026, 10, 14, 11, 0)
    ts3 = datetime(2026, 10, 14, 12, 0)

    # 1. Trigger high temperature
    t_fault1 = create_telemetry(pump_config, temp_c=80.0, timestamp=ts1)
    health_engine.evaluate_telemetry(t_fault1, pump_config)
    assert len(health_engine.get_active_alerts("P-101")) == 1
    first_alert_id = health_engine.get_active_alerts("P-101")[0].alert_id

    # 2. Re-evaluate same condition (should update, not create duplicate)
    t_fault2 = create_telemetry(pump_config, temp_c=81.0, timestamp=ts2)
    health_engine.evaluate_telemetry(t_fault2, pump_config)
    assert len(health_engine.get_active_alerts("P-101")) == 1
    assert health_engine.get_active_alerts("P-101")[0].alert_id == first_alert_id

    # 3. Parameter returns to normal (recovery check)
    t_healthy = create_telemetry(pump_config, temp_c=62.0, timestamp=ts3)
    health_engine.evaluate_telemetry(t_healthy, pump_config)
    assert len(health_engine.get_active_alerts("P-101")) == 0
