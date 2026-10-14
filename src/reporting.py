"""Reporting and audit export module for pump health and energy records.

Generates standardized CSV audit exports, executive KPI summaries, and historical
reporting packages for process plant reliability teams and management.
"""

from datetime import datetime
from io import BytesIO, StringIO
from typing import Dict, List, Optional
import pandas as pd

from src.energy_analytics import EnergyKPIs
from src.event_logger import EventLogger
from src.health_monitor import DiagnosticAlert
from src.maintenance_manager import MaintenancePriorityItem


class ReportingEngine:
    """Produces exportable CSV reports and plant summary rollups."""

    def __init__(self, logger: Optional[EventLogger] = None):
        self.logger = logger or EventLogger()

    def generate_telemetry_csv(self, equipment_id: Optional[str] = None) -> str:
        """Export telemetry time-series records as formatted CSV string."""
        df = self.logger.load_telemetry(equipment_id=equipment_id)
        if df.empty:
            return "equipment_id,timestamp,operating_status,power_kw,flow_rate_m3h,temperature_c,vibration_mms,operating_hours,energy_kwh\n"
        return df.to_csv(index=False)

    def generate_alarms_csv(self, equipment_id: Optional[str] = None) -> str:
        """Export alarm event log as formatted CSV string."""
        df = self.logger.load_alarms(equipment_id=equipment_id)
        if df.empty:
            return "alert_id,equipment_id,condition,severity,timestamp,evidence,possible_causes,recommended_inspections,is_active\n"
        return df.to_csv(index=False)

    def generate_maintenance_csv(self, equipment_id: Optional[str] = None) -> str:
        """Export maintenance records and audit actions as CSV string."""
        df = self.logger.load_maintenance_records(equipment_id=equipment_id)
        if df.empty:
            return "record_id,equipment_id,action_type,action,technician_note,timestamp\n"
        return df.to_csv(index=False)

    def generate_energy_summary_csv(self, kpi_list: List[EnergyKPIs]) -> str:
        """Export multi-equipment energy accounting summary as CSV string."""
        if not kpi_list:
            return "equipment_id,name,total_operating_hours,total_energy_kwh,average_power_kw,baseline_energy_kwh,excess_energy_kwh,estimated_cost,excess_cost\n"
        rows = [k.to_dict() for k in kpi_list]
        df = pd.DataFrame(rows)
        return df.to_csv(index=False)

    def generate_priority_csv(self, priority_items: List[MaintenancePriorityItem]) -> str:
        """Export current maintenance prioritization triage table as CSV string."""
        if not priority_items:
            return "equipment_id,name,priority,priority_score,reasons,recommended_action,maintenance_status\n"
        rows = [p.to_dict() for p in priority_items]
        df = pd.DataFrame(rows)
        return df.to_csv(index=False)

    def compile_plant_summary(
        self,
        telemetry_map: Dict,
        active_alerts: List[DiagnosticAlert],
        energy_kpis: List[EnergyKPIs],
    ) -> Dict:
        """Produce executive plant snapshot dictionary."""
        total_pumps = len(telemetry_map)
        running = sum(1 for t in telemetry_map.values() if t.operating_status == "Running")
        stopped = sum(1 for t in telemetry_map.values() if t.operating_status == "Stopped")
        fault = sum(1 for t in telemetry_map.values() if t.operating_status == "Fault")

        critical_alerts = sum(1 for a in active_alerts if a.severity.value == "Critical" and a.is_active)
        warning_alerts = sum(1 for a in active_alerts if a.severity.value == "Warning" and a.is_active)

        total_energy_kwh = sum(k.total_energy_kwh for k in energy_kpis)
        total_cost = sum(k.estimated_cost for k in energy_kpis)
        excess_energy_kwh = sum(k.excess_energy_kwh for k in energy_kpis)
        excess_cost = sum(k.excess_cost for k in energy_kpis)

        return {
            "total_pumps": total_pumps,
            "running_count": running,
            "stopped_count": stopped,
            "fault_count": fault,
            "critical_alerts_count": critical_alerts,
            "warning_alerts_count": warning_alerts,
            "total_energy_kwh": round(total_energy_kwh, 2),
            "total_cost": round(total_cost, 2),
            "excess_energy_kwh": round(excess_energy_kwh, 2),
            "excess_cost": round(excess_cost, 2),
            "report_generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
