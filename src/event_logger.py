"""Local event, alarm, and telemetry persistence engine.

Provides transactional local CSV persistence, idempotency de-duplication,
graceful handling of empty or missing files, and safe reset capabilities.
"""

from datetime import datetime
import json
import os
from pathlib import Path
from typing import Dict, List, Optional
import pandas as pd

from src.equipment_simulator import EquipmentTelemetry
from src.health_monitor import DiagnosticAlert


class EventLogger:
    """Manages persistent CSV logs for telemetry, alarms, and maintenance actions."""

    def __init__(self, data_dir: Optional[Path] = None):
        if data_dir is None:
            # Default to project data directory
            self.data_dir = Path(__file__).resolve().parent.parent / "data"
        else:
            self.data_dir = Path(data_dir)

        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.telemetry_file = self.data_dir / "equipment_telemetry.csv"
        self.alarm_file = self.data_dir / "alarm_history.csv"
        self.maintenance_file = self.data_dir / "maintenance_records.csv"

        self._logged_alarm_ids = set()
        self._load_existing_alarm_ids()

    def _load_existing_alarm_ids(self) -> None:
        """Cache existing alarm IDs to guarantee idempotent deduplication."""
        if self.alarm_file.exists() and self.alarm_file.stat().st_size > 0:
            try:
                df = pd.read_csv(self.alarm_file)
                if "alert_id" in df.columns:
                    self._logged_alarm_ids = set(df["alert_id"].dropna().astype(str).tolist())
            except Exception:
                self._logged_alarm_ids = set()

    def log_telemetry_batch(self, records: List[EquipmentTelemetry]) -> None:
        """Append a batch of telemetry records to the telemetry CSV log."""
        if not records:
            return

        rows = [r.to_dict() for r in records]
        df_new = pd.DataFrame(rows)

        if not self.telemetry_file.exists() or self.telemetry_file.stat().st_size == 0:
            df_new.to_csv(self.telemetry_file, index=False)
        else:
            # Read existing to ensure header consistency
            try:
                df_existing = pd.read_csv(self.telemetry_file)
                # Deduplicate by equipment_id and timestamp
                df_combined = pd.concat([df_existing, df_new], ignore_index=True)
                df_combined.drop_duplicates(subset=["equipment_id", "timestamp"], keep="last", inplace=True)
                df_combined.to_csv(self.telemetry_file, index=False)
            except Exception:
                df_new.to_csv(self.telemetry_file, mode="a", header=False, index=False)

    def log_alerts(self, alerts: List[DiagnosticAlert]) -> int:
        """Append newly detected alerts to the alarm log, skipping duplicates.

        Returns:
            Number of new alerts successfully logged.
        """
        new_alerts = [a for a in alerts if a.alert_id not in self._logged_alarm_ids]
        if not new_alerts:
            return 0

        rows = [a.to_dict() for a in new_alerts]
        df_new = pd.DataFrame(rows)

        if not self.alarm_file.exists() or self.alarm_file.stat().st_size == 0:
            df_new.to_csv(self.alarm_file, index=False)
        else:
            df_new.to_csv(self.alarm_file, mode="a", header=False, index=False)

        for a in new_alerts:
            self._logged_alarm_ids.add(a.alert_id)

        return len(new_alerts)

    def log_maintenance_action(
        self,
        equipment_id: str,
        action: str,
        technician_note: str,
        action_type: str = "Inspection",
        timestamp: Optional[datetime] = None,
    ) -> Dict:
        """Record a completed or scheduled maintenance action."""
        ts = timestamp or datetime.now()
        record = {
            "record_id": f"MNT-{equipment_id}-{int(ts.timestamp())}",
            "equipment_id": equipment_id,
            "action_type": action_type,
            "action": action,
            "technician_note": technician_note,
            "timestamp": ts.isoformat(),
        }
        df_new = pd.DataFrame([record])

        if not self.maintenance_file.exists() or self.maintenance_file.stat().st_size == 0:
            df_new.to_csv(self.maintenance_file, index=False)
        else:
            df_new.to_csv(self.maintenance_file, mode="a", header=False, index=False)

        return record

    def load_telemetry(self, equipment_id: Optional[str] = None) -> pd.DataFrame:
        """Load telemetry history from CSV into a DataFrame."""
        if not self.telemetry_file.exists() or self.telemetry_file.stat().st_size == 0:
            return pd.DataFrame()
        try:
            df = pd.read_csv(self.telemetry_file)
            if "timestamp" in df.columns:
                df["timestamp"] = pd.to_datetime(df["timestamp"])
            if equipment_id and not df.empty and "equipment_id" in df.columns:
                df = df[df["equipment_id"] == equipment_id]
            return df
        except Exception:
            return pd.DataFrame()

    def load_alarms(self, equipment_id: Optional[str] = None) -> pd.DataFrame:
        """Load alarm log into a DataFrame."""
        if not self.alarm_file.exists() or self.alarm_file.stat().st_size == 0:
            return pd.DataFrame()
        try:
            df = pd.read_csv(self.alarm_file)
            if "timestamp" in df.columns:
                df["timestamp"] = pd.to_datetime(df["timestamp"])
            if equipment_id and not df.empty and "equipment_id" in df.columns:
                df = df[df["equipment_id"] == equipment_id]
            return df
        except Exception:
            return pd.DataFrame()

    def load_maintenance_records(self, equipment_id: Optional[str] = None) -> pd.DataFrame:
        """Load maintenance history into a DataFrame."""
        if not self.maintenance_file.exists() or self.maintenance_file.stat().st_size == 0:
            return pd.DataFrame()
        try:
            df = pd.read_csv(self.maintenance_file)
            if "timestamp" in df.columns:
                df["timestamp"] = pd.to_datetime(df["timestamp"])
            if equipment_id and not df.empty and "equipment_id" in df.columns:
                df = df[df["equipment_id"] == equipment_id]
            return df
        except Exception:
            return pd.DataFrame()

    def reset_data(self, confirm: bool = False) -> bool:
        """Safely reset generated data files when explicitly confirmed."""
        if not confirm:
            return False

        files = [self.telemetry_file, self.alarm_file, self.maintenance_file]
        for f in files:
            if f.exists():
                try:
                    f.unlink()
                except Exception:
                    pass

        self._logged_alarm_ids.clear()
        return True
