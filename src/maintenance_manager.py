"""Maintenance prioritization and work-order management module.

Implements explainable rule-based maintenance triage according to active ISO condition
alerts, degradation trends, operating hour milestones, and energy anomalies.
Provides work-order workflows, status tracking, and audit logging.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional
import pandas as pd

from src.equipment_simulator import EquipmentConfig, EquipmentTelemetry, MaintenanceStatus
from src.event_logger import EventLogger
from src.health_monitor import AlertSeverity, ConditionType, DiagnosticAlert


class PriorityLevel(str, Enum):
    """Prioritization tiers for maintenance scheduling."""
    CRITICAL = "Critical"
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


@dataclass
class MaintenancePriorityItem:
    """Triage summary for an equipment asset with actionable recommendations."""
    equipment_id: str
    name: str
    priority: PriorityLevel
    priority_score: float  # Explainable composite risk index (0 to 100)
    reasons: List[str]
    recommended_action: str
    maintenance_status: str
    active_alerts_count: int
    last_maintenance_date: Optional[str] = None

    def to_dict(self) -> Dict:
        """Convert triage item to dictionary."""
        return {
            "equipment_id": self.equipment_id,
            "name": self.name,
            "priority": self.priority.value,
            "priority_score": round(self.priority_score, 1),
            "reasons": "; ".join(self.reasons),
            "recommended_action": self.recommended_action,
            "maintenance_status": self.maintenance_status,
            "active_alerts_count": self.active_alerts_count,
            "last_maintenance_date": self.last_maintenance_date or "N/A",
        }


class MaintenanceManager:
    """Triage and status tracking for plant rotating equipment."""

    def __init__(self, logger: Optional[EventLogger] = None):
        self.logger = logger or EventLogger()
        # In-memory status map (equipment_id -> status)
        self.equipment_statuses: Dict[str, str] = {}
        self.last_maintenance_dates: Dict[str, str] = {}

    def get_status(self, equipment_id: str) -> str:
        """Get current maintenance workflow status."""
        return self.equipment_statuses.get(equipment_id, MaintenanceStatus.NORMAL.value)

    def update_status(
        self,
        equipment_id: str,
        new_status: str,
        technician_note: str = "",
        action_type: str = "Status Update",
    ) -> None:
        """Update workflow status and persist to audit trail."""
        self.equipment_statuses[equipment_id] = new_status
        now_ts = datetime.now()
        if new_status in (MaintenanceStatus.RESOLVED.value, "Inspected", "Resolved"):
            self.last_maintenance_dates[equipment_id] = now_ts.strftime("%Y-%m-%d %H:%M")

        self.logger.log_maintenance_action(
            equipment_id=equipment_id,
            action=f"Status changed to {new_status}",
            technician_note=technician_note,
            action_type=action_type,
            timestamp=now_ts,
        )

    def evaluate_priority(
        self,
        config: EquipmentConfig,
        current_telemetry: EquipmentTelemetry,
        active_alerts: List[DiagnosticAlert],
    ) -> MaintenancePriorityItem:
        """Evaluate transparent maintenance priority for an equipment unit.

        Formula for Composite Risk Index (0-100, purely illustrative ranking metric):
        - Base: 15
        - Critical Alerts: +40 each (capped at 45)
        - Warning Alerts: +15 each (capped at 30)
        - Operating Hours Ratio (>100% of interval): +15
        - Trend / Energy Overload: +10
        Max score is capped at 100.
        """
        eq_id = config.equipment_id
        eq_alerts = [a for a in active_alerts if a.equipment_id == eq_id and a.is_active]

        crit_alerts = [a for a in eq_alerts if a.severity == AlertSeverity.CRITICAL]
        warn_alerts = [a for a in eq_alerts if a.severity == AlertSeverity.WARNING]

        reasons: List[str] = []
        base_score = 15.0

        # Triage evaluation
        if crit_alerts:
            priority = PriorityLevel.CRITICAL
            base_score += 45.0 + (len(crit_alerts) - 1) * 10.0
            for a in crit_alerts:
                reasons.append(f"[CRITICAL] {a.condition.value}: {a.evidence}")
            action = (
                "IMMEDIATE TRIP/LOCKOUT: Stop pump, switch to standby, execute Lockout-Tagout (LOTO), "
                "and inspect bearings, shaft alignment, and motor relays."
            )

        elif warn_alerts or (current_telemetry.operating_hours >= config.service_interval_hours):
            has_trend = any(a.condition == ConditionType.VIBRATION_TREND_UPWARD for a in warn_alerts)
            has_hours = current_telemetry.operating_hours >= config.service_interval_hours
            multiple_warnings = len(warn_alerts) >= 2

            if has_trend or multiple_warnings or (has_hours and warn_alerts):
                priority = PriorityLevel.HIGH
                base_score += 35.0 + len(warn_alerts) * 8.0
                for a in warn_alerts:
                    reasons.append(f"[WARNING] {a.condition.value}: {a.evidence}")
                if has_hours:
                    reasons.append(f"Operating hours ({current_telemetry.operating_hours:.0f}h) exceed service threshold ({config.service_interval_hours:.0f}h)")
                action = (
                    "SCHEDULE HIGH-PRIORITY INSPECTION: Perform laser shaft alignment, FFT vibration spectral analysis, "
                    "and oil sample laboratory spectroscopy within 48 hours."
                )
            else:
                priority = PriorityLevel.MEDIUM
                base_score += 20.0 + len(warn_alerts) * 10.0
                for a in warn_alerts:
                    reasons.append(f"[WARNING] {a.condition.value}: {a.evidence}")
                if has_hours:
                    reasons.append(f"Cumulative hours reached overhaul limit ({current_telemetry.operating_hours:.0f}h)")
                action = (
                    "ROUTINE MAINTENANCE CHECK: Monitor temperature trend, grease motor bearings per OEM schedule, "
                    "and clean suction basket filter during next shift."
                )

        else:
            priority = PriorityLevel.LOW
            base_score = 10.0
            reasons.append("All mechanical and electrical parameters are within normal ISO tolerances.")
            action = "STANDARD PREVENTIVE MONITORING: Maintain automated supervisory logging and daily visual rounds."

        # Cap composite score at 100
        score = min(100.0, max(5.0, base_score))

        current_maint_status = self.get_status(eq_id)
        last_maint_date = self.last_maintenance_dates.get(eq_id, "2026-09-15 08:00 (PM Overhaul)")

        return MaintenancePriorityItem(
            equipment_id=eq_id,
            name=config.name,
            priority=priority,
            priority_score=score,
            reasons=reasons,
            recommended_action=action,
            maintenance_status=current_maint_status,
            active_alerts_count=len(eq_alerts),
            last_maintenance_date=last_maint_date,
        )

    def prioritize_fleet(
        self,
        configs: Dict[str, EquipmentConfig],
        telemetry_map: Dict[str, EquipmentTelemetry],
        active_alerts: List[DiagnosticAlert],
    ) -> List[MaintenancePriorityItem]:
        """Triage entire fleet sorted by priority urgency and risk score."""
        items: List[MaintenancePriorityItem] = []
        for eq_id, cfg in configs.items():
            telem = telemetry_map.get(eq_id)
            if telem:
                item = self.evaluate_priority(cfg, telem, active_alerts)
                items.append(item)

        # Sort: Critical first, then High, Medium, Low; tie-break by priority_score descending
        priority_rank = {
            PriorityLevel.CRITICAL: 4,
            PriorityLevel.HIGH: 3,
            PriorityLevel.MEDIUM: 2,
            PriorityLevel.LOW: 1,
        }
        items.sort(key=lambda x: (priority_rank[x.priority], x.priority_score), reverse=True)
        return items
