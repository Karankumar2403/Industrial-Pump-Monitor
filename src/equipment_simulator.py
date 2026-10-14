"""Equipment simulator module for industrial pumps and motors.

Simulates realistic, physically consistent operating data for centrifugal pumps
across normal operation and industrial fault scenarios. Distinguishes synthetic
measurements from real equipment data and supports deterministic random seeds.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
import math
from typing import Dict, List, Optional
import numpy as np


class OperatingStatus(str, Enum):
    """Equipment operating states in industrial DCS/SCADA."""
    RUNNING = "Running"
    STOPPED = "Stopped"
    FAULT = "Fault"


class DiagnosticStatus(str, Enum):
    """Condition monitoring severity levels."""
    NORMAL = "Normal"
    WARNING = "Warning"
    CRITICAL = "Critical"


class MaintenanceStatus(str, Enum):
    """Maintenance management workflow statuses."""
    NORMAL = "Normal"
    INSPECTION_REQUIRED = "Inspection Required"
    WORK_ORDER_ISSUED = "Work Order Issued"
    UNDER_MAINTENANCE = "Under Maintenance"
    RESOLVED = "Resolved"


class FaultScenario(str, Enum):
    """Standard industrial operational and fault scenarios."""
    NORMAL_OPERATION = "Normal Operation"
    ELEVATED_TEMPERATURE = "Elevated Temperature"
    ELEVATED_VIBRATION = "Elevated Vibration"
    INCREASING_VIBRATION_TREND = "Increasing Vibration Trend"
    EXCESSIVE_OPERATING_HOURS = "Excessive Operating Hours"
    INCREASED_ENERGY_CONSUMPTION = "Increased Energy Consumption"
    REDUCED_SIMULATED_FLOW = "Reduced Simulated Flow"
    UNEXPECTED_EQUIPMENT_STOPPAGE = "Unexpected Equipment Stoppage"
    COMBINED_ABNORMAL_CONDITIONS = "Combined Abnormal Conditions"
    RETURN_TO_NORMAL_OPERATION = "Return to Normal Operation"


@dataclass
class EquipmentConfig:
    """Configuration baseline parameters for a simulated pump unit."""
    equipment_id: str
    name: str
    equipment_type: str
    rated_power_kw: float
    rated_flow_m3h: float
    nominal_temp_c: float = 60.0
    nominal_vibration_mms: float = 1.8
    ambient_temp_c: float = 30.0
    operating_hours_baseline: float = 2400.0
    service_interval_hours: float = 4000.0


@dataclass
class EquipmentTelemetry:
    """Snapshot record of equipment operating parameters at a given timestamp."""
    equipment_id: str
    name: str
    equipment_type: str
    operating_status: str
    operating_hours: float
    power_kw: float
    energy_kwh: float
    temperature_c: float
    vibration_mms: float
    flow_rate_m3h: float
    timestamp: datetime
    maintenance_status: str
    current_diagnostic_status: str
    simulation_scenario: str
    is_synthetic: bool = True

    def to_dict(self) -> Dict:
        """Convert telemetry record to serializable dictionary."""
        return {
            "equipment_id": self.equipment_id,
            "name": self.name,
            "equipment_type": self.equipment_type,
            "operating_status": self.operating_status,
            "operating_hours": round(self.operating_hours, 2),
            "power_kw": round(self.power_kw, 2),
            "energy_kwh": round(self.energy_kwh, 2),
            "temperature_c": round(self.temperature_c, 2),
            "vibration_mms": round(self.vibration_mms, 2),
            "flow_rate_m3h": round(self.flow_rate_m3h, 2),
            "timestamp": self.timestamp.isoformat(),
            "maintenance_status": self.maintenance_status,
            "current_diagnostic_status": self.current_diagnostic_status,
            "simulation_scenario": self.simulation_scenario,
            "is_synthetic": self.is_synthetic,
        }


def get_default_fleet_configs() -> Dict[str, EquipmentConfig]:
    """Return standard industrial pump models across process units."""
    return {
        "P-101": EquipmentConfig(
            equipment_id="P-101",
            name="Boiler Feed Water Pump A",
            equipment_type="Multistage Centrifugal",
            rated_power_kw=75.0,
            rated_flow_m3h=120.0,
            nominal_temp_c=65.0,
            nominal_vibration_mms=1.9,
            operating_hours_baseline=3100.0,
            service_interval_hours=4000.0,
        ),
        "P-102": EquipmentConfig(
            equipment_id="P-102",
            name="Cooling Water Circulation Pump B",
            equipment_type="End-Suction Centrifugal",
            rated_power_kw=45.0,
            rated_flow_m3h=180.0,
            nominal_temp_c=58.0,
            nominal_vibration_mms=1.7,
            operating_hours_baseline=2750.0,
            service_interval_hours=4000.0,
        ),
        "P-103": EquipmentConfig(
            equipment_id="P-103",
            name="CDU Naphtha Transfer Pump C",
            equipment_type="API 610 Process Centrifugal",
            rated_power_kw=55.0,
            rated_flow_m3h=95.0,
            nominal_temp_c=62.0,
            nominal_vibration_mms=1.8,
            operating_hours_baseline=3850.0,
            service_interval_hours=4000.0,
        ),
        "P-104": EquipmentConfig(
            equipment_id="P-104",
            name="ETP Effluent Slurry Pump D",
            equipment_type="Heavy-Duty Slurry Centrifugal",
            rated_power_kw=30.0,
            rated_flow_m3h=70.0,
            nominal_temp_c=56.0,
            nominal_vibration_mms=2.1,
            operating_hours_baseline=1900.0,
            service_interval_hours=3500.0,
        ),
    }


class PumpSimulator:
    """Deterministic synthetic data generator for industrial pump telemetry."""

    def __init__(self, config: EquipmentConfig, seed: Optional[int] = None):
        self.config = config
        self.rng = np.random.default_rng(seed)
        self.current_hours = config.operating_hours_baseline
        self.cumulative_energy_kwh = (
            config.operating_hours_baseline * config.rated_power_kw * 0.88
        )
        self.step_counter = 0

    def generate_point(
        self,
        timestamp: datetime,
        scenario: FaultScenario = FaultScenario.NORMAL_OPERATION,
        delta_hours: float = 1.0,
        trend_step: int = 0,
    ) -> EquipmentTelemetry:
        """Generate a single physically consistent telemetry point.

        Args:
            timestamp: Measurement timestamp
            scenario: Operational scenario to simulate
            delta_hours: Elapsed operating interval in hours
            trend_step: Progression counter for trend-based scenarios
        """
        cfg = self.config
        noise_p = self.rng.normal(0, 0.015)
        noise_t = self.rng.normal(0, 0.4)
        noise_v = self.rng.normal(0, 0.08)
        noise_q = self.rng.normal(0, 0.015)

        # Baseline physical defaults
        status = OperatingStatus.RUNNING.value
        maint_status = MaintenanceStatus.NORMAL.value
        diag_status = DiagnosticStatus.NORMAL.value

        power = cfg.rated_power_kw * (0.92 + noise_p)
        flow = cfg.rated_flow_m3h * (1.00 + noise_q)
        temp = cfg.nominal_temp_c + noise_t
        vib = max(0.2, cfg.nominal_vibration_mms + noise_v)

        # Apply specific scenario modifications
        if scenario == FaultScenario.NORMAL_OPERATION:
            pass

        elif scenario == FaultScenario.ELEVATED_TEMPERATURE:
            temp = cfg.nominal_temp_c + 18.0 + noise_t  # e.g., 78-85°C
            vib = cfg.nominal_vibration_mms + 0.6 + noise_v
            diag_status = DiagnosticStatus.WARNING.value
            maint_status = MaintenanceStatus.INSPECTION_REQUIRED.value

        elif scenario == FaultScenario.ELEVATED_VIBRATION:
            vib = cfg.nominal_vibration_mms + 2.8 + noise_v  # ISO Zone C/D ~4.6 mm/s
            temp = cfg.nominal_temp_c + 4.0 + noise_t
            diag_status = DiagnosticStatus.CRITICAL.value
            maint_status = MaintenanceStatus.INSPECTION_REQUIRED.value

        elif scenario == FaultScenario.INCREASING_VIBRATION_TREND:
            # Progressive degradation over sequential steps
            ramp = min(4.2, max(0.0, trend_step * 0.22))
            vib = cfg.nominal_vibration_mms + ramp + noise_v
            temp = cfg.nominal_temp_c + (ramp * 1.5) + noise_t
            if vib >= 4.5:
                diag_status = DiagnosticStatus.CRITICAL.value
                maint_status = MaintenanceStatus.INSPECTION_REQUIRED.value
            elif vib >= 2.8:
                diag_status = DiagnosticStatus.WARNING.value
                maint_status = MaintenanceStatus.INSPECTION_REQUIRED.value

        elif scenario == FaultScenario.EXCESSIVE_OPERATING_HOURS:
            # Drive cumulative hours above recommended service interval
            self.current_hours = max(
                self.current_hours, cfg.service_interval_hours + 185.0
            )
            diag_status = DiagnosticStatus.WARNING.value
            maint_status = MaintenanceStatus.INSPECTION_REQUIRED.value

        elif scenario == FaultScenario.INCREASED_ENERGY_CONSUMPTION:
            # Internal hydraulic recirculation / impeller fouling
            power = cfg.rated_power_kw * (1.28 + noise_p)  # 28% overload
            flow = cfg.rated_flow_m3h * (0.88 + noise_q)   # Reduced output
            temp = cfg.nominal_temp_c + 7.5 + noise_t
            diag_status = DiagnosticStatus.WARNING.value
            maint_status = MaintenanceStatus.INSPECTION_REQUIRED.value

        elif scenario == FaultScenario.REDUCED_SIMULATED_FLOW:
            # Suction strainer blockage / throttling
            flow = cfg.rated_flow_m3h * (0.42 + noise_q)
            power = cfg.rated_power_kw * (0.75 + noise_p)  # Low load
            vib = cfg.nominal_vibration_mms + 1.2 + noise_v  # Cavitation onset
            diag_status = DiagnosticStatus.WARNING.value
            maint_status = MaintenanceStatus.INSPECTION_REQUIRED.value

        elif scenario == FaultScenario.UNEXPECTED_EQUIPMENT_STOPPAGE:
            status = OperatingStatus.STOPPED.value
            power = 0.0
            flow = 0.0
            # Ambient vibration floor & exponential temperature decay towards ambient
            vib = max(0.05, 0.15 + (noise_v * 0.2))
            temp = cfg.ambient_temp_c + 4.0 + (noise_t * 0.2)
            diag_status = DiagnosticStatus.CRITICAL.value
            maint_status = MaintenanceStatus.WORK_ORDER_ISSUED.value

        elif scenario == FaultScenario.COMBINED_ABNORMAL_CONDITIONS:
            # Multi-parameter cascade: vibration + temp + power surge
            power = cfg.rated_power_kw * (1.24 + noise_p)
            flow = cfg.rated_flow_m3h * (0.65 + noise_q)
            vib = cfg.nominal_vibration_mms + 3.1 + noise_v  # ~5.0 mm/s
            temp = cfg.nominal_temp_c + 22.0 + noise_t       # ~84-88°C
            diag_status = DiagnosticStatus.CRITICAL.value
            maint_status = MaintenanceStatus.WORK_ORDER_ISSUED.value

        elif scenario == FaultScenario.RETURN_TO_NORMAL_OPERATION:
            diag_status = DiagnosticStatus.NORMAL.value
            maint_status = MaintenanceStatus.RESOLVED.value

        # Enforce physical constraints for stopped equipment
        if status == OperatingStatus.STOPPED.value:
            power = 0.0
            flow = 0.0
            interval_energy = 0.0
        else:
            self.current_hours += delta_hours
            interval_energy = max(0.0, power * delta_hours)
            self.cumulative_energy_kwh += interval_energy

        return EquipmentTelemetry(
            equipment_id=cfg.equipment_id,
            name=cfg.name,
            equipment_type=cfg.equipment_type,
            operating_status=status,
            operating_hours=self.current_hours,
            power_kw=max(0.0, power),
            energy_kwh=self.cumulative_energy_kwh,
            temperature_c=temp,
            vibration_mms=max(0.05, vib),
            flow_rate_m3h=max(0.0, flow),
            timestamp=timestamp,
            maintenance_status=maint_status,
            current_diagnostic_status=diag_status,
            simulation_scenario=scenario.value,
            is_synthetic=True,
        )

    def generate_history(
        self,
        start_time: datetime,
        points: int = 48,
        interval_hours: float = 1.0,
        scenario: FaultScenario = FaultScenario.NORMAL_OPERATION,
        fault_injection_idx: Optional[int] = None,
    ) -> List[EquipmentTelemetry]:
        """Generate historical sequence of telemetry records.

        Args:
            start_time: Initial timestamp
            points: Number of consecutive intervals
            interval_hours: Hours between each telemetry point
            scenario: Target operational scenario
            fault_injection_idx: Index at which the fault scenario begins
        """
        records: List[EquipmentTelemetry] = []
        for i in range(points):
            current_ts = start_time + timedelta(hours=i * interval_hours)
            active_scen = FaultScenario.NORMAL_OPERATION
            trend_step = 0

            if fault_injection_idx is not None and i >= fault_injection_idx:
                active_scen = scenario
                trend_step = i - fault_injection_idx

            point = self.generate_point(
                timestamp=current_ts,
                scenario=active_scen,
                delta_hours=interval_hours,
                trend_step=trend_step,
            )
            records.append(point)
        return records
