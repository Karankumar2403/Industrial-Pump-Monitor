"""Energy analytics and cost accounting module for industrial pump drives.

Computes energy consumption (kWh = kW × hours), electricity expenditure based on
configurable industrial tariffs, daily/weekly aggregations, and transparent
baseline variance analysis. Clearly demarcates theoretical baseline estimates
from actual plant measurements.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional
import numpy as np
import pandas as pd

from src.equipment_simulator import EquipmentConfig


@dataclass
class EnergyKPIs:
    """Consolidated energy and cost indicators for an equipment unit."""
    equipment_id: str
    name: str
    total_operating_hours: float
    total_energy_kwh: float
    average_power_kw: float
    baseline_energy_kwh: float
    excess_energy_kwh: float
    estimated_cost: float
    excess_cost: float
    currency_symbol: str = "₹"
    is_hypothetical_estimate: bool = True

    def to_dict(self) -> Dict:
        """Convert KPIs to dictionary."""
        return {
            "equipment_id": self.equipment_id,
            "name": self.name,
            "total_operating_hours": round(self.total_operating_hours, 2),
            "total_energy_kwh": round(self.total_energy_kwh, 2),
            "average_power_kw": round(self.average_power_kw, 2),
            "baseline_energy_kwh": round(self.baseline_energy_kwh, 2),
            "excess_energy_kwh": round(self.excess_energy_kwh, 2),
            "estimated_cost": round(self.estimated_cost, 2),
            "excess_cost": round(self.excess_cost, 2),
            "currency_symbol": self.currency_symbol,
            "is_hypothetical_estimate": self.is_hypothetical_estimate,
        }


class EnergyAnalyticsEngine:
    """Calculates electrical consumption, utility tariffs, and baseline variance."""

    def __init__(self, default_tariff: float = 8.50, currency_symbol: str = "₹"):
        """Initialize engine with configurable tariff rate (default ₹8.50/kWh)."""
        self.tariff_per_kwh = max(0.0, float(default_tariff))
        self.currency_symbol = currency_symbol

    def calculate_energy(self, avg_power_kw: float, operating_hours: float) -> float:
        """Calculate electrical energy in kilowatt-hours.

        Formula: Energy (kWh) = Average Power (kW) × Operating Time (hours)
        Handles zero or negative operating time safely.
        """
        if operating_hours <= 0.0 or avg_power_kw <= 0.0:
            return 0.0
        return float(avg_power_kw * operating_hours)

    def calculate_energy_cost(self, energy_kwh: float, tariff: Optional[float] = None) -> float:
        """Calculate estimated electricity cost for given energy consumption.

        Formula: Estimated Energy Cost = Energy Consumed (kWh) × Electricity Tariff (currency/kWh)
        """
        active_tariff = self.tariff_per_kwh if tariff is None else max(0.0, float(tariff))
        if energy_kwh <= 0.0 or active_tariff <= 0.0:
            return 0.0
        return float(energy_kwh * active_tariff)

    def compute_equipment_kpis(
        self,
        df_telemetry: pd.DataFrame,
        config: EquipmentConfig,
        tariff: Optional[float] = None,
    ) -> EnergyKPIs:
        """Compute holistic energy KPIs for an equipment unit from telemetry data."""
        active_tariff = self.tariff_per_kwh if tariff is None else max(0.0, float(tariff))

        if df_telemetry.empty or "equipment_id" not in df_telemetry.columns:
            return EnergyKPIs(
                equipment_id=config.equipment_id,
                name=config.name,
                total_operating_hours=0.0,
                total_energy_kwh=0.0,
                average_power_kw=0.0,
                baseline_energy_kwh=0.0,
                excess_energy_kwh=0.0,
                estimated_cost=0.0,
                excess_cost=0.0,
                currency_symbol=self.currency_symbol,
            )

        df_eq = df_telemetry[df_telemetry["equipment_id"] == config.equipment_id].copy()
        if df_eq.empty:
            return EnergyKPIs(
                equipment_id=config.equipment_id,
                name=config.name,
                total_operating_hours=0.0,
                total_energy_kwh=0.0,
                average_power_kw=0.0,
                baseline_energy_kwh=0.0,
                excess_energy_kwh=0.0,
                estimated_cost=0.0,
                excess_cost=0.0,
                currency_symbol=self.currency_symbol,
            )

        # Filter running points for active operating calculation
        running_mask = (df_eq["operating_status"] == "Running") & (df_eq["power_kw"] > 0)
        df_running = df_eq[running_mask]

        # Calculate time span and operating intervals
        total_pts = len(df_eq)
        running_pts = len(df_running)

        # Assuming 1-hour interval per point if timestamps are consecutive hours
        operating_hours = float(running_pts * 1.0)
        avg_power = float(df_running["power_kw"].mean()) if not df_running.empty else 0.0
        if np.isnan(avg_power):
            avg_power = 0.0

        total_energy = self.calculate_energy(avg_power, operating_hours)

        # Baseline calculation: nominal design power (0.90 * rated_power_kw)
        nominal_design_power = config.rated_power_kw * 0.90
        baseline_energy = self.calculate_energy(nominal_design_power, operating_hours)

        # Excess energy from mechanical degradation or hydraulic fouling
        excess_energy = max(0.0, total_energy - baseline_energy)

        total_cost = self.calculate_energy_cost(total_energy, active_tariff)
        excess_cost = self.calculate_energy_cost(excess_energy, active_tariff)

        return EnergyKPIs(
            equipment_id=config.equipment_id,
            name=config.name,
            total_operating_hours=operating_hours,
            total_energy_kwh=total_energy,
            average_power_kw=avg_power,
            baseline_energy_kwh=baseline_energy,
            excess_energy_kwh=excess_energy,
            estimated_cost=total_cost,
            excess_cost=excess_cost,
            currency_symbol=self.currency_symbol,
            is_hypothetical_estimate=True,
        )

    def aggregate_energy_trends(
        self, df_telemetry: pd.DataFrame, freq: str = "1D"
    ) -> pd.DataFrame:
        """Aggregate energy and power trends by day or week for all equipment."""
        if df_telemetry.empty or "timestamp" not in df_telemetry.columns:
            return pd.DataFrame()

        df = df_telemetry.copy()
        if not pd.api.types.is_datetime64_any_dtype(df["timestamp"]):
            df["timestamp"] = pd.to_datetime(df["timestamp"])

        df.set_index("timestamp", inplace=True)

        # Resample power and sum energy per equipment
        records = []
        for eq_id, group in df.groupby("equipment_id"):
            resampled = group.resample(freq).agg({
                "power_kw": "mean",
                "flow_rate_m3h": "mean",
                "operating_status": lambda s: (s == "Running").sum(),
            }).reset_index()

            resampled["equipment_id"] = eq_id
            # Energy for period = mean running power * running hours in interval
            resampled["operating_hours"] = resampled["operating_status"]
            resampled["energy_kwh"] = resampled["power_kw"].fillna(0) * resampled["operating_hours"]
            resampled["estimated_cost"] = resampled["energy_kwh"] * self.tariff_per_kwh
            records.append(resampled)

        if not records:
            return pd.DataFrame()

        return pd.concat(records, ignore_index=True)
