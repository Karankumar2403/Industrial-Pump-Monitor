"""Automated tests for reporting engine, CSV exports, plant rollups, and data safety."""

from datetime import datetime
import pandas as pd
import pytest

from src.energy_analytics import EnergyKPIs
from src.equipment_simulator import (
    EquipmentConfig,
    EquipmentTelemetry,
    MaintenanceStatus,
    OperatingStatus,
)
from src.event_logger import EventLogger
from src.health_monitor import AlertSeverity, ConditionType, DiagnosticAlert
from src.reporting import ReportingEngine


@pytest.fixture
def temp_logger(tmp_path) -> EventLogger:
    return EventLogger(data_dir=tmp_path)


@pytest.fixture
def reporting_engine(temp_logger) -> ReportingEngine:
    return ReportingEngine(logger=temp_logger)


def test_empty_csv_exports(reporting_engine):
    """Verify CSV generators return valid CSV headers even when logs are empty."""
    telem_csv = reporting_engine.generate_telemetry_csv()
    assert "equipment_id,timestamp" in telem_csv

    alarms_csv = reporting_engine.generate_alarms_csv()
    assert "alert_id,equipment_id,condition" in alarms_csv

    maint_csv = reporting_engine.generate_maintenance_csv()
    assert "record_id,equipment_id,action_type" in maint_csv

    energy_csv = reporting_engine.generate_energy_summary_csv([])
    assert "total_operating_hours,total_energy_kwh" in energy_csv


def test_telemetry_and_alarm_csv_export(reporting_engine, temp_logger):
    """Verify populated logs export cleanly to CSV string."""
    # Log telemetry record
    telem = EquipmentTelemetry(
        equipment_id="P-101",
        name="Boiler Feed Water Pump A",
        equipment_type="Multistage Centrifugal",
        operating_status="Running",
        operating_hours=1250.0,
        power_kw=68.5,
        energy_kwh=85000.0,
        temperature_c=64.2,
        vibration_mms=1.85,
        flow_rate_m3h=118.0,
        timestamp=datetime(2026, 10, 14, 12, 0),
        maintenance_status="Normal",
        current_diagnostic_status="Normal",
        simulation_scenario="Normal Operation",
    )
    temp_logger.log_telemetry_batch([telem])

    # Log alarm record
    alert = DiagnosticAlert(
        alert_id="ALT-101",
        equipment_id="P-101",
        condition=ConditionType.HIGH_TEMPERATURE,
        severity=AlertSeverity.WARNING,
        timestamp=datetime(2026, 10, 14, 12, 0),
        evidence="Temperature 78.2°C",
        possible_causes=["Low oil"],
        recommended_inspections=["Top up oil"],
    )
    temp_logger.log_alerts([alert])

    telem_csv = reporting_engine.generate_telemetry_csv()
    assert "P-101" in telem_csv
    assert "68.5" in telem_csv

    alarm_csv = reporting_engine.generate_alarms_csv()
    assert "ALT-101" in alarm_csv
    assert "High Bearing/Casing Temperature" in alarm_csv


def test_compile_plant_summary(reporting_engine):
    """Verify executive summary calculates counts and energy rollups correctly."""
    telem_map = {
        "P-101": EquipmentTelemetry(
            equipment_id="P-101",
            name="Pump 1",
            equipment_type="Centrifugal",
            operating_status="Running",
            operating_hours=100.0,
            power_kw=50.0,
            energy_kwh=5000.0,
            temperature_c=60.0,
            vibration_mms=1.8,
            flow_rate_m3h=100.0,
            timestamp=datetime.now(),
            maintenance_status="Normal",
            current_diagnostic_status="Normal",
            simulation_scenario="Normal Operation",
        ),
        "P-102": EquipmentTelemetry(
            equipment_id="P-102",
            name="Pump 2",
            equipment_type="Centrifugal",
            operating_status="Stopped",
            operating_hours=80.0,
            power_kw=0.0,
            energy_kwh=3200.0,
            temperature_c=30.0,
            vibration_mms=0.1,
            flow_rate_m3h=0.0,
            timestamp=datetime.now(),
            maintenance_status="Work Order Issued",
            current_diagnostic_status="Critical",
            simulation_scenario="Unexpected Stoppage",
        ),
    }

    active_alerts = [
        DiagnosticAlert(
            alert_id="ALT-1",
            equipment_id="P-102",
            condition=ConditionType.UNEXPECTED_STOPPAGE,
            severity=AlertSeverity.CRITICAL,
            timestamp=datetime.now(),
            evidence="Stopped under load",
            possible_causes=["Relay tripped"],
            recommended_inspections=["Check relay"],
            is_active=True,
        )
    ]

    kpis = [
        EnergyKPIs(
            equipment_id="P-101",
            name="Pump 1",
            total_operating_hours=100.0,
            total_energy_kwh=5000.0,
            average_power_kw=50.0,
            baseline_energy_kwh=4500.0,
            excess_energy_kwh=500.0,
            estimated_cost=42500.0,
            excess_cost=4250.0,
        )
    ]

    summary = reporting_engine.compile_plant_summary(telem_map, active_alerts, kpis)
    assert summary["total_pumps"] == 2
    assert summary["running_count"] == 1
    assert summary["stopped_count"] == 1
    assert summary["critical_alerts_count"] == 1
    assert summary["warning_alerts_count"] == 0
    assert summary["total_energy_kwh"] == 5000.0
    assert summary["total_cost"] == 42500.0


def test_safe_reset_handling(temp_logger):
    """Verify reset function requires explicit confirmation."""
    # Write sample record
    temp_logger.log_maintenance_action("P-101", "Check", "Verified")
    assert temp_logger.maintenance_file.exists()

    # Reset with confirm=False should do nothing
    res_false = temp_logger.reset_data(confirm=False)
    assert res_false is False
    assert temp_logger.maintenance_file.exists()

    # Reset with confirm=True should unlink files
    res_true = temp_logger.reset_data(confirm=True)
    assert res_true is True
    assert not temp_logger.maintenance_file.exists()
