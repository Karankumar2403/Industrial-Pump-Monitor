"""Rule-based industrial health monitor for pump and motor condition monitoring.

Evaluates multi-variable telemetry against ISO 10816-3 vibration standards,
bearing temperature limits, energy consumption overloads, and trend regressions.
Provides explainable diagnostic rationale, root-cause hypotheses, and actionable
maintenance inspection recommendations.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Tuple
import numpy as np

from src.equipment_simulator import EquipmentConfig, EquipmentTelemetry, OperatingStatus


class AlertSeverity(str, Enum):
    """Industrial alarm severity levels."""
    INFO = "Info"
    WARNING = "Warning"
    CRITICAL = "Critical"


class ConditionType(str, Enum):
    """Categorized diagnostic failure modes."""
    NORMAL = "Normal Operation"
    HIGH_TEMPERATURE = "High Bearing/Casing Temperature"
    HIGH_VIBRATION = "High Vibration Severity (ISO 10816-3)"
    VIBRATION_TREND_UPWARD = "Sustained Upward Vibration Trend"
    EXCESSIVE_OPERATING_HOURS = "Operating Hours Service Threshold Exceeded"
    ABNORMAL_ENERGY = "Abnormal Power Overload"
    UNEXPECTED_STOPPAGE = "Unexpected Equipment Stoppage"
    MULTIPLE_FAULTS = "Compound Multi-Parameter Abnormality"


@dataclass
class Thresholds:
    """Configurable industrial monitoring thresholds (ISO 10816-3 Class II/III)."""
    vibration_warning_mms: float = 2.80  # Zone C boundary
    vibration_critical_mms: float = 4.50 # Zone D boundary
    temp_warning_c: float = 75.0         # Alarm limit for standard grease
    temp_critical_c: float = 85.0        # Trip limit for anti-friction bearings
    power_overload_ratio: float = 1.15   # 15% above rated motor power
    hours_service_limit: float = 4000.0  # Recommended major maintenance interval
    trend_min_points: int = 4
    trend_slope_threshold: float = 0.12  # mm/s per timestep


@dataclass
class DiagnosticAlert:
    """Structured diagnostic alert with engineering context."""
    alert_id: str
    equipment_id: str
    condition: ConditionType
    severity: AlertSeverity
    timestamp: datetime
    evidence: str
    possible_causes: List[str]
    recommended_inspections: List[str]
    is_active: bool = True
    resolved_at: Optional[datetime] = None

    def to_dict(self) -> Dict:
        """Convert alert to serializable dictionary."""
        return {
            "alert_id": self.alert_id,
            "equipment_id": self.equipment_id,
            "condition": self.condition.value,
            "severity": self.severity.value,
            "timestamp": self.timestamp.isoformat(),
            "evidence": self.evidence,
            "possible_causes": "; ".join(self.possible_causes),
            "recommended_inspections": " | ".join(self.recommended_inspections),
            "is_active": self.is_active,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else "",
        }


class HealthMonitoringEngine:
    """Industrial rule engine for pump and motor condition diagnostics."""

    def __init__(self, thresholds: Optional[Thresholds] = None):
        self.thresholds = thresholds or Thresholds()
        # Active alert registry keyed by (equipment_id, condition_type)
        self.active_alerts: Dict[Tuple[str, str], DiagnosticAlert] = {}
        self.alert_history: List[DiagnosticAlert] = []

    def detect_vibration_trend(
        self, vibration_series: List[float]
    ) -> Tuple[bool, float]:
        """Compute linear trend slope across rolling historical vibration window."""
        if len(vibration_series) < self.thresholds.trend_min_points:
            return False, 0.0

        # Recent slice
        recent = vibration_series[-self.thresholds.trend_min_points:]
        x = np.arange(len(recent), dtype=float)
        y = np.array(recent, dtype=float)

        # Linear regression slope: (N*sum(xy) - sum(x)*sum(y)) / (N*sum(x^2) - (sum(x))^2)
        n = len(x)
        denom = n * np.sum(x**2) - (np.sum(x))**2
        if denom == 0:
            return False, 0.0
        slope = float((n * np.sum(x * y) - np.sum(x) * np.sum(y)) / denom)

        # Flag if slope exceeds configured threshold and recent values are rising
        is_trending = (
            slope >= self.thresholds.trend_slope_threshold
            and recent[-1] > recent[0]
        )
        return is_trending, slope

    def evaluate_telemetry(
        self,
        current: EquipmentTelemetry,
        config: EquipmentConfig,
        vibration_history: Optional[List[float]] = None,
    ) -> List[DiagnosticAlert]:
        """Evaluate single equipment telemetry snapshot and update alert states.

        Returns list of newly triggered or updated alerts for this evaluation cycle.
        """
        th = self.thresholds
        detected_conditions: List[Tuple[ConditionType, AlertSeverity, str, List[str], List[str]]] = []

        # 1. Unexpected stoppage check
        if current.operating_status == OperatingStatus.STOPPED.value:
            if current.simulation_scenario == "Unexpected Equipment Stoppage" or current.current_diagnostic_status == "Critical":
                detected_conditions.append((
                    ConditionType.UNEXPECTED_STOPPAGE,
                    AlertSeverity.CRITICAL,
                    f"Equipment is in STOPPED status under active process demand (Power: {current.power_kw:.1f} kW, Flow: {current.flow_rate_m3h:.1f} m³/h).",
                    [
                        "Motor thermal overload relay tripped",
                        "Emergency shutdown (ESD) interlock trip",
                        "Mechanical seizure / bearing catastrophic lockup",
                    ],
                    [
                        "Check MCC switchgear relay trip codes",
                        "Perform motor insulation resistance (megger) test",
                        "Inspect pump shaft for free manual rotation",
                    ],
                ))

        # 2. Temperature monitoring (if running)
        if current.operating_status == OperatingStatus.RUNNING.value:
            if current.temperature_c >= th.temp_critical_c:
                detected_conditions.append((
                    ConditionType.HIGH_TEMPERATURE,
                    AlertSeverity.CRITICAL,
                    f"Bearing/Casing temperature is {current.temperature_c:.1f}°C, exceeding critical limit {th.temp_critical_c:.1f}°C.",
                    [
                        "Severe loss of lubrication or grease degradation",
                        "Bearing fatigue spalling / cage failure",
                        "Excessive axial thrust load or misalignment",
                    ],
                    [
                        "Immediate thermal imaging / thermography scan",
                        "Inspect lubricant level, color, and contamination",
                        "Check cooling water circulation jacket",
                    ],
                ))
            elif current.temperature_c >= th.temp_warning_c:
                detected_conditions.append((
                    ConditionType.HIGH_TEMPERATURE,
                    AlertSeverity.WARNING,
                    f"Temperature is {current.temperature_c:.1f}°C, exceeding warning threshold {th.temp_warning_c:.1f}°C.",
                    [
                        "Incipient bearing wear",
                        "High ambient temperature or restricted motor cooling fins",
                        "Mild lubrication deficit",
                    ],
                    [
                        "Replenish manufacturer specified grease grade",
                        "Clean motor cooling fan shroud and casing fins",
                        "Trend bearing temperature over subsequent 24 hours",
                    ],
                ))

        # 3. Vibration monitoring (ISO 10816-3) (if running)
        if current.operating_status == OperatingStatus.RUNNING.value:
            if current.vibration_mms >= th.vibration_critical_mms:
                detected_conditions.append((
                    ConditionType.HIGH_VIBRATION,
                    AlertSeverity.CRITICAL,
                    f"Vibration is {current.vibration_mms:.2f} mm/s RMS (ISO Zone D - Critical), exceeding limit {th.vibration_critical_mms:.2f} mm/s.",
                    [
                        "Severe rotor dynamic unbalance or impeller vane damage",
                        "Significant shaft angular/parallel misalignment",
                        "Structural looseness in baseplate / foundation anchor bolts",
                    ],
                    [
                        "Conduct FFT spectral vibration analysis (1X, 2X harmonic peaks)",
                        "Inspect flexible coupling elements and torque bolts",
                        "Check pump-to-baseplate hold-down bolt torque",
                    ],
                ))
            elif current.vibration_mms >= th.vibration_warning_mms:
                detected_conditions.append((
                    ConditionType.HIGH_VIBRATION,
                    AlertSeverity.WARNING,
                    f"Vibration is {current.vibration_mms:.2f} mm/s RMS (ISO Zone C - Warning), exceeding threshold {th.vibration_warning_mms:.2f} mm/s.",
                    [
                        "Minor coupling wear or shaft misalignment",
                        "Hydraulic turbulence or operation off Best Efficiency Point (BEP)",
                        "Pipe strain transmitting forces to pump nozzles",
                    ],
                    [
                        "Check operating point on pump performance curve",
                        "Verify pipe support integrity and strain",
                        "Schedule laser shaft alignment check during next window",
                    ],
                ))

        # 4. Vibration trend analysis
        if vibration_history and current.operating_status == OperatingStatus.RUNNING.value:
            is_trending, slope = self.detect_vibration_trend(vibration_history)
            if is_trending:
                detected_conditions.append((
                    ConditionType.VIBRATION_TREND_UPWARD,
                    AlertSeverity.WARNING,
                    f"Sustained upward vibration degradation trend (+{slope:.3f} mm/s per interval over past {len(vibration_history[-th.trend_min_points:])} points).",
                    [
                        "Progressive bearing raceway micro-pitting",
                        "Accelerating erosion or debris deposition on impeller",
                        "Developing foundation resonance or bolt relaxation",
                    ],
                    [
                        "Collect high-frequency acoustic emission / demodulation readings",
                        "Increase vibration logging frequency from daily to hourly",
                        "Prepare standby pump unit for immediate changeover",
                    ],
                ))

        # 5. Operating hours threshold
        if current.operating_hours >= config.service_interval_hours:
            detected_conditions.append((
                ConditionType.EXCESSIVE_OPERATING_HOURS,
                AlertSeverity.WARNING,
                f"Operating hours reached {current.operating_hours:.1f} hrs, exceeding overhaul limit {config.service_interval_hours:.1f} hrs.",
                [
                    "Mechanical seal face wear and elastomeric aging",
                    "Bearing L10 fatigue life threshold approaching",
                    "Coupling insert wear",
                ],
                [
                    "Schedule planned preventive maintenance (PM) turnaround",
                    "Perform lubrication change-out and seal leak inspection",
                    "Inspect impeller clearance and wear rings",
                ],
            ))

        # 6. Abnormal power overload
        max_power_baseline = config.rated_power_kw * th.power_overload_ratio
        if current.operating_status == OperatingStatus.RUNNING.value and current.power_kw >= max_power_baseline:
            detected_conditions.append((
                ConditionType.ABNORMAL_ENERGY,
                AlertSeverity.WARNING,
                f"Motor drawing {current.power_kw:.1f} kW, which is {(current.power_kw/config.rated_power_kw - 1)*100:.1f}% above rated {config.rated_power_kw:.1f} kW baseline.",
                [
                    "Internal hydraulic recirculation or impeller rubbing",
                    "High process fluid viscosity or specific gravity change",
                    "Over-pumping / operating beyond runout capacity on pump curve",
                ],
                [
                    "Throttle discharge control valve to check amp draw response",
                    "Sample process fluid density and viscosity in lab",
                    "Inspect internal casing wear rings for contact marks",
                ],
            ))

        # 7. Compound multi-fault detection
        active_conditions_count = len(detected_conditions)
        if active_conditions_count >= 2:
            detected_conditions.append((
                ConditionType.MULTIPLE_FAULTS,
                AlertSeverity.CRITICAL,
                f"Multiple concurrent anomalies detected ({active_conditions_count} simultaneous fault indicators).",
                [
                    "Cascading failure mode (e.g. vibration causing seal friction and thermal runaway)",
                    "Severe process upset or severe cavitation destroying hydraulic internals",
                ],
                [
                    "Immediate supervisory engineering review",
                    "Initiate controlled changeover to redundant spare pump",
                    "Isolate unit for complete mechanical inspection",
                ],
            ))

        # Update Alert Registry and eliminate duplicate alert spam
        current_active_keys = set()
        newly_raised_or_active_alerts: List[DiagnosticAlert] = []

        for cond, sev, evidence, causes, inspections in detected_conditions:
            key = (current.equipment_id, cond.value)
            current_active_keys.add(key)

            if key not in self.active_alerts:
                alert_id = f"ALT-{current.equipment_id}-{int(current.timestamp.timestamp())}-{len(self.alert_history)+1}"
                alert = DiagnosticAlert(
                    alert_id=alert_id,
                    equipment_id=current.equipment_id,
                    condition=cond,
                    severity=sev,
                    timestamp=current.timestamp,
                    evidence=evidence,
                    possible_causes=causes,
                    recommended_inspections=inspections,
                    is_active=True,
                )
                self.active_alerts[key] = alert
                self.alert_history.append(alert)
                newly_raised_or_active_alerts.append(alert)
            else:
                # Update existing alert severity or evidence if changed
                existing = self.active_alerts[key]
                existing.evidence = evidence
                existing.severity = sev
                newly_raised_or_active_alerts.append(existing)

        # Handle alert clearance/recovery
        all_tracked_keys = list(self.active_alerts.keys())
        for key in all_tracked_keys:
            eq_id, cond_name = key
            if eq_id == current.equipment_id and key not in current_active_keys:
                resolved_alert = self.active_alerts.pop(key)
                resolved_alert.is_active = False
                resolved_alert.resolved_at = current.timestamp

        return newly_raised_or_active_alerts

    def get_active_alerts(self, equipment_id: Optional[str] = None) -> List[DiagnosticAlert]:
        """Return active alerts, optionally filtered by equipment ID."""
        alerts = list(self.active_alerts.values())
        if equipment_id:
            alerts = [a for a in alerts if a.equipment_id == equipment_id]
        return alerts

    def get_all_alerts(self, equipment_id: Optional[str] = None) -> List[DiagnosticAlert]:
        """Return all historical alerts, optionally filtered by equipment ID."""
        alerts = self.alert_history
        if equipment_id:
            alerts = [a for a in alerts if a.equipment_id == equipment_id]
        return alerts
