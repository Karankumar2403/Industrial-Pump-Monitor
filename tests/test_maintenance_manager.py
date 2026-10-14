"""Automated tests for maintenance triage, priority rules, and work-order management."""

from datetime import datetime
import pytest

from src.equipment_simulator import EquipmentConfig, EquipmentTelemetry, MaintenanceStatus, OperatingStatus
from src.event_logger import EventLogger
from src.health_monitor import AlertSeverity, ConditionType, DiagnosticAlert
from src.maintenance_manager import MaintenanceManager, PriorityLevel


@pytest.fixture
def temp_logger(tmp_path) -> EventLogger:
    return EventLogger(data_dir=tmp_path)


@pytest.fixture
def maint_mgr(temp_logger) -> MaintenanceManager:
    return MaintenanceManager(logger=temp_logger)


@pytest.fixture
def pump_config() -> EquipmentConfig:
    return EquipmentConfig(
        equipment_id="P-101",
        name="Boiler Feed Water Pump A",
        equipment_type="Multistage Centrifugal",
        rated_power_kw=75.0,
        rated_flow_m3h=120.0,
        operating_hours_baseline=2500.0,
        service_interval_hours=4000.0,
    )


def create_telemetry_stub(config: EquipmentConfig, hours: float = 2500.0) -> EquipmentTelemetry:
    return EquipmentTelemetry(
        equipment_id=config.equipment_id,
        name=config.name,
        equipment_type=config.equipment_type,
        operating_status=OperatingStatus.RUNNING.value,
        operating_hours=hours,
        power_kw=68.0,
        energy_kwh=10000.0,
        temperature_c=62.0,
        vibration_mms=1.8,
        flow_rate_m3h=120.0,
        timestamp=datetime.now(),
        maintenance_status=MaintenanceStatus.NORMAL.value,
        current_diagnostic_status="Normal",
        simulation_scenario="Normal Operation",
    )


def test_low_priority_under_healthy_conditions(maint_mgr, pump_config):
    """Verify healthy pump receives Low maintenance priority."""
    telem = create_telemetry_stub(pump_config)
    item = maint_mgr.evaluate_priority(pump_config, telem, active_alerts=[])

    assert item.priority == PriorityLevel.LOW
    assert item.priority_score <= 25.0
    assert "normal iso tolerances" in item.reasons[0].lower()


def test_critical_priority_with_critical_alert(maint_mgr, pump_config):
    """Verify critical alert drives priority to Critical immediately."""
    telem = create_telemetry_stub(pump_config)
    crit_alert = DiagnosticAlert(
        alert_id="ALT-CRIT-1",
        equipment_id="P-101",
        condition=ConditionType.HIGH_VIBRATION,
        severity=AlertSeverity.CRITICAL,
        timestamp=datetime.now(),
        evidence="Vibration 5.4 mm/s RMS (ISO Zone D)",
        possible_causes=["Severe dynamic unbalance"],
        recommended_inspections=["Emergency LOTO and inspect rotor"],
        is_active=True,
    )

    item = maint_mgr.evaluate_priority(pump_config, telem, active_alerts=[crit_alert])
    assert item.priority == PriorityLevel.CRITICAL
    assert item.priority_score >= 60.0
    assert "IMMEDIATE TRIP/LOCKOUT" in item.recommended_action


def test_high_priority_with_degradation_trend_or_multiple_warnings(maint_mgr, pump_config):
    """Verify upward trend or multiple warnings triggers High priority."""
    telem = create_telemetry_stub(pump_config)
    trend_alert = DiagnosticAlert(
        alert_id="ALT-TREND-1",
        equipment_id="P-101",
        condition=ConditionType.VIBRATION_TREND_UPWARD,
        severity=AlertSeverity.WARNING,
        timestamp=datetime.now(),
        evidence="Slope +0.22 mm/s per step",
        possible_causes=["Incipient bearing wear"],
        recommended_inspections=["Laser alignment and oil sample"],
        is_active=True,
    )

    item = maint_mgr.evaluate_priority(pump_config, telem, active_alerts=[trend_alert])
    assert item.priority == PriorityLevel.HIGH
    assert 50.0 <= item.priority_score <= 90.0


def test_medium_priority_with_single_warning(maint_mgr, pump_config):
    """Verify single isolated warning triggers Medium priority."""
    telem = create_telemetry_stub(pump_config)
    warn_alert = DiagnosticAlert(
        alert_id="ALT-WARN-1",
        equipment_id="P-101",
        condition=ConditionType.HIGH_TEMPERATURE,
        severity=AlertSeverity.WARNING,
        timestamp=datetime.now(),
        evidence="Temperature 78.5°C",
        possible_causes=["Mild lubrication deficit"],
        recommended_inspections=["Replenish grease"],
        is_active=True,
    )

    item = maint_mgr.evaluate_priority(pump_config, telem, active_alerts=[warn_alert])
    assert item.priority == PriorityLevel.MEDIUM
    assert 30.0 <= item.priority_score <= 60.0


def test_maintenance_status_update_and_audit(maint_mgr, pump_config, temp_logger):
    """Verify status updates log to audit file and update last maintenance date."""
    assert maint_mgr.get_status("P-101") == MaintenanceStatus.NORMAL.value

    maint_mgr.update_status("P-101", "Inspected", technician_note="Alignment verified within 0.03mm.")
    assert maint_mgr.get_status("P-101") == "Inspected"
    assert "P-101" in maint_mgr.last_maintenance_dates

    # Check persistence
    df_records = temp_logger.load_maintenance_records("P-101")
    assert not df_records.empty
    assert df_records.iloc[0]["equipment_id"] == "P-101"
    assert "Alignment verified" in df_records.iloc[0]["technician_note"]
