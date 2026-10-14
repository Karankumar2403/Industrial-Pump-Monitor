"""Industrial Pump Health, Energy Monitoring & Predictive Maintenance System.

Engineering dashboard for plant operations, condition monitoring, ISO 10816-3 vibration
diagnostics, energy cost accounting, and maintenance triage.
"""

from datetime import datetime, timedelta
import os
import sys
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.energy_analytics import EnergyAnalyticsEngine, EnergyKPIs
from src.equipment_simulator import (
    DiagnosticStatus,
    EquipmentConfig,
    EquipmentTelemetry,
    FaultScenario,
    MaintenanceStatus,
    OperatingStatus,
    PumpSimulator,
    get_default_fleet_configs,
)
from src.event_logger import EventLogger
from src.health_monitor import (
    AlertSeverity,
    ConditionType,
    DiagnosticAlert,
    HealthMonitoringEngine,
    Thresholds,
)
from src.maintenance_manager import MaintenanceManager, PriorityLevel
from src.reporting import ReportingEngine

# ==========================================
# PAGE CONFIGURATION & THEME STYLING
# ==========================================
st.set_page_config(
    page_title="Industrial Pump Condition & Energy Monitor",
    page_icon="⚙️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom Industrial DCS / Control Room CSS Styling
st.markdown(
    """
    <style>
    /* Global Control Room Typography & Background */
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700&family=Inter:wght@400;500;600;700&display=swap');

    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }

    .metric-card {
        background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
        border: 1px solid #334155;
        border-radius: 10px;
        padding: 16px 20px;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.25);
        margin-bottom: 12px;
    }

    .metric-value {
        font-family: 'JetBrains Mono', monospace;
        font-size: 26px;
        font-weight: 700;
        color: #38bdf8;
    }

    .metric-label {
        font-size: 13px;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        color: #94a3b8;
        font-weight: 600;
        margin-bottom: 4px;
    }

    .status-pill {
        display: inline-block;
        padding: 4px 12px;
        border-radius: 9999px;
        font-size: 12px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }

    .status-running {
        background-color: rgba(34, 197, 94, 0.15);
        color: #4ade80;
        border: 1px solid #22c55e;
    }

    .status-stopped {
        background-color: rgba(239, 68, 68, 0.15);
        color: #f87171;
        border: 1px solid #ef4444;
    }

    .status-warning {
        background-color: rgba(234, 179, 8, 0.15);
        color: #facc15;
        border: 1px solid #eab308;
    }

    .status-critical {
        background-color: rgba(239, 68, 68, 0.2);
        color: #fca5a5;
        border: 1px solid #dc2626;
    }

    .banner-disclaimer {
        background-color: #1e293b;
        border-left: 4px solid #38bdf8;
        padding: 10px 16px;
        font-size: 12px;
        color: #cbd5e1;
        border-radius: 4px;
        margin-bottom: 16px;
    }

    .section-header {
        font-size: 18px;
        font-weight: 700;
        color: #f1f5f9;
        margin-top: 10px;
        margin-bottom: 14px;
        border-bottom: 1px solid #334155;
        padding-bottom: 6px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ==========================================
# SESSION STATE INITIALIZATION
# ==========================================
def init_session_state():
    """Initialize persistent simulation components and data caches."""
    if "fleet_configs" not in st.session_state:
        st.session_state.fleet_configs = get_default_fleet_configs()

    if "event_logger" not in st.session_state:
        st.session_state.event_logger = EventLogger()

    if "thresholds" not in st.session_state:
        st.session_state.thresholds = Thresholds()

    if "health_engine" not in st.session_state:
        st.session_state.health_engine = HealthMonitoringEngine(st.session_state.thresholds)

    if "maintenance_mgr" not in st.session_state:
        st.session_state.maintenance_mgr = MaintenanceManager(st.session_state.event_logger)

    if "tariff_rate" not in st.session_state:
        st.session_state.tariff_rate = 8.50  # INR per kWh illustrative standard

    if "energy_engine" not in st.session_state:
        st.session_state.energy_engine = EnergyAnalyticsEngine(
            default_tariff=st.session_state.tariff_rate, currency_symbol="₹"
        )

    if "simulators" not in st.session_state:
        st.session_state.simulators = {
            eq_id: PumpSimulator(cfg, seed=42 + idx)
            for idx, (eq_id, cfg) in enumerate(st.session_state.fleet_configs.items())
        }

    if "telemetry_history" not in st.session_state:
        # Pre-seed with 48 hours of baseline normal operation history
        history: Dict[str, List[EquipmentTelemetry]] = {}
        start_time = datetime.now() - timedelta(hours=48)
        all_initial_records = []

        for eq_id, sim in st.session_state.simulators.items():
            records = sim.generate_history(
                start_time=start_time, points=48, interval_hours=1.0
            )
            history[eq_id] = records
            all_initial_records.extend(records)

            # Evaluate health alerts for historical points
            vib_hist = []
            for r in records:
                vib_hist.append(r.vibration_mms)
                st.session_state.health_engine.evaluate_telemetry(
                    r, st.session_state.fleet_configs[eq_id], vib_hist
                )

        st.session_state.telemetry_history = history
        st.session_state.event_logger.log_telemetry_batch(all_initial_records)

    if "active_scenarios" not in st.session_state:
        st.session_state.active_scenarios = {
            eq_id: FaultScenario.NORMAL_OPERATION.value
            for eq_id in st.session_state.fleet_configs.keys()
        }

    if "trend_counters" not in st.session_state:
        st.session_state.trend_counters = {
            eq_id: 0 for eq_id in st.session_state.fleet_configs.keys()
        }


init_session_state()

# Helper accessors
fleet_configs: Dict[str, EquipmentConfig] = st.session_state.fleet_configs
telemetry_history: Dict[str, List[EquipmentTelemetry]] = st.session_state.telemetry_history
health_engine: HealthMonitoringEngine = st.session_state.health_engine
maintenance_mgr: MaintenanceManager = st.session_state.maintenance_mgr
energy_engine: EnergyAnalyticsEngine = st.session_state.energy_engine
event_logger: EventLogger = st.session_state.event_logger
reporting_engine = ReportingEngine(event_logger)


# ==========================================
# SIDEBAR NAVIGATION & PLANT CONTROLS
# ==========================================
st.sidebar.image(
    "https://img.icons8.com/fluency/96/water-pump.png",
    width=64,
)
st.sidebar.title("Industrial Pump SCADA")
st.sidebar.caption("Health, Energy & Reliability Monitoring")

navigation_page = st.sidebar.radio(
    "Plant Navigation",
    [
        "🏭 Plant Overview",
        "🔍 Equipment Monitoring",
        "⚡ Energy Analytics",
        "🧪 Fault Simulator",
        "🛠️ Maintenance Centre",
        "📄 Reports & Audit",
    ],
    index=0,
)

st.sidebar.markdown("---")
st.sidebar.subheader("⚡ Utility Tariff Settings")
tariff_input = st.sidebar.number_input(
    "Electricity Tariff (₹/kWh)",
    min_value=1.0,
    max_value=30.0,
    value=float(st.session_state.tariff_rate),
    step=0.25,
    help="Illustrative industrial high-tension (HT) power tariff for cost estimation.",
)
if tariff_input != st.session_state.tariff_rate:
    st.session_state.tariff_rate = tariff_input
    st.session_state.energy_engine = EnergyAnalyticsEngine(
        default_tariff=tariff_input, currency_symbol="₹"
    )

st.sidebar.markdown("---")
st.sidebar.markdown(
    """
    **Simulation Disclaimer**:
    This software runs on a synthetic mathematical pump model. Thresholds adhere to ISO 10816-3 condition monitoring principles for educational demonstration.
    """
)


# ==========================================
# HELPER: GET LATEST SNAPSHOTS
# ==========================================
def get_latest_telemetry_map() -> Dict[str, EquipmentTelemetry]:
    """Retrieve the most recent telemetry point for every pump unit."""
    latest_map = {}
    for eq_id, records in telemetry_history.items():
        if records:
            latest_map[eq_id] = records[-1]
    return latest_map


latest_telemetry = get_latest_telemetry_map()
active_alerts = health_engine.get_active_alerts()


# ==========================================
# PAGE A: PLANT OVERVIEW
# ==========================================
if navigation_page == "🏭 Plant Overview":
    st.title("🏭 Plant Condition & Energy Overview")
    st.markdown(
        """
        <div class="banner-disclaimer">
            <strong>System Status</strong>: Supervisory monitoring active across all continuous process pump units.
            Diagnostic triggers evaluated in real-time according to ISO 10816-3 mechanical vibration standards.
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Compute plant KPIs
    total_units = len(fleet_configs)
    running_count = sum(1 for t in latest_telemetry.values() if t.operating_status == "Running")
    stopped_count = sum(1 for t in latest_telemetry.values() if t.operating_status == "Stopped")
    critical_alerts = [a for a in active_alerts if a.severity == AlertSeverity.CRITICAL]
    warning_alerts = [a for a in active_alerts if a.severity == AlertSeverity.WARNING]

    # Energy totals across history
    df_all_telemetry = pd.DataFrame([r.to_dict() for records in telemetry_history.values() for r in records])
    energy_kpi_list = [
        energy_engine.compute_equipment_kpis(df_all_telemetry, cfg)
        for cfg in fleet_configs.values()
    ]
    total_energy_kwh = sum(k.total_energy_kwh for k in energy_kpi_list)
    total_cost_inr = sum(k.estimated_cost for k in energy_kpi_list)

    # Executive Metric Cards
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-label">Monitored Pumps</div>
                <div class="metric-value">{total_units} <span style="font-size:14px; color:#94a3b8;">Units</span></div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col2:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-label">Operating Status</div>
                <div class="metric-value" style="color:#4ade80;">{running_count} <span style="font-size:14px; color:#94a3b8;">Run / {stopped_count} Stop</span></div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col3:
        alert_color = "#f87171" if critical_alerts else ("#facc15" if warning_alerts else "#4ade80")
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-label">Active Alarms</div>
                <div class="metric-value" style="color:{alert_color};">{len(critical_alerts)} <span style="font-size:14px; color:#94a3b8;">Crit / {len(warning_alerts)} Warn</span></div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col4:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-label">Total Simulated Energy</div>
                <div class="metric-value">{total_energy_kwh:,.0f} <span style="font-size:14px; color:#94a3b8;">kWh</span></div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col5:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-label">Estimated Energy Cost</div>
                <div class="metric-value">₹{total_cost_inr:,.0f} <span style="font-size:14px; color:#94a3b8;">INR</span></div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown('<div class="section-header">Equipment Fleet Live Status Matrix</div>', unsafe_allow_html=True)

    # Equipment Fleet Table
    fleet_rows = []
    for eq_id, cfg in fleet_configs.items():
        telem = latest_telemetry.get(eq_id)
        if telem:
            eq_alerts = [a for a in active_alerts if a.equipment_id == eq_id]
            maint_item = maintenance_mgr.evaluate_priority(cfg, telem, active_alerts)
            fleet_rows.append({
                "Equipment ID": eq_id,
                "Equipment Name": cfg.name,
                "Type": cfg.equipment_type,
                "Status": telem.operating_status,
                "Power (kW)": f"{telem.power_kw:.1f} / {cfg.rated_power_kw:.1f}",
                "Flow (m³/h)": f"{telem.flow_rate_m3h:.1f}",
                "Vibration (mm/s)": f"{telem.vibration_mms:.2f}",
                "Temperature (°C)": f"{telem.temperature_c:.1f}",
                "Operating Hours": f"{telem.operating_hours:.0f} h",
                "Condition": telem.current_diagnostic_status,
                "Priority": maint_item.priority.value,
            })

    df_fleet_matrix = pd.DataFrame(fleet_rows)
    st.dataframe(
        df_fleet_matrix,
        use_container_width=True,
        hide_index=True,
    )

    # Quick Visualizations: Vibration vs Limits & Power Breakdown
    col_v, col_p = st.columns(2)
    with col_v:
        fig_vib = go.Figure()
        eq_names = [f"{cfg.equipment_id} ({cfg.name[:12]}...)" for cfg in fleet_configs.values()]
        vib_vals = [latest_telemetry[eq].vibration_mms for eq in fleet_configs.keys()]
        colors = [
            "#ef4444" if v >= 4.5 else ("#eab308" if v >= 2.8 else "#22c55e")
            for v in vib_vals
        ]

        fig_vib.add_trace(go.Bar(
            x=eq_names,
            y=vib_vals,
            marker_color=colors,
            text=[f"{v:.2f} mm/s" for v in vib_vals],
            textposition="auto",
        ))
        fig_vib.add_hline(y=2.8, line_dash="dash", line_color="#eab308", annotation_text="ISO Zone C (Warning: 2.8 mm/s)")
        fig_vib.add_hline(y=4.5, line_dash="dash", line_color="#ef4444", annotation_text="ISO Zone D (Critical: 4.5 mm/s)")
        fig_vib.update_layout(
            title="Instantaneous Vibration Severity vs ISO 10816-3 Thresholds",
            yaxis_title="Vibration (mm/s RMS)",
            template="plotly_dark",
            height=320,
            margin=dict(l=40, r=40, t=50, b=40),
        )
        st.plotly_chart(fig_vib, use_container_width=True)

    with col_p:
        fig_pwr = go.Figure()
        powers = [latest_telemetry[eq].power_kw for eq in fleet_configs.keys()]
        rated = [fleet_configs[eq].rated_power_kw for eq in fleet_configs.keys()]

        fig_pwr.add_trace(go.Bar(
            name="Actual Power",
            x=[cfg.equipment_id for cfg in fleet_configs.values()],
            y=powers,
            marker_color="#38bdf8",
        ))
        fig_pwr.add_trace(go.Bar(
            name="Rated Design Power",
            x=[cfg.equipment_id for cfg in fleet_configs.values()],
            y=rated,
            marker_color="#64748b",
        ))
        fig_pwr.update_layout(
            title="Active Motor Power vs Rated Design Capacity",
            yaxis_title="Motor Power (kW)",
            barmode="group",
            template="plotly_dark",
            height=320,
            margin=dict(l=40, r=40, t=50, b=40),
        )
        st.plotly_chart(fig_pwr, use_container_width=True)


# ==========================================
# PAGE B: EQUIPMENT MONITORING
# ==========================================
elif navigation_page == "🔍 Equipment Monitoring":
    st.title("🔍 Equipment Telemetry & Condition Monitoring")

    selected_eq = st.selectbox(
        "Select Equipment Asset",
        options=list(fleet_configs.keys()),
        format_func=lambda x: f"{x} - {fleet_configs[x].name} ({fleet_configs[x].equipment_type})",
    )
    cfg = fleet_configs[selected_eq]
    records = telemetry_history.get(selected_eq, [])
    latest = records[-1] if records else None

    if latest:
        # Top KPI bar for chosen asset
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Status", latest.operating_status)
        c2.metric("Motor Power", f"{latest.power_kw:.1f} kW", f"{latest.power_kw - cfg.rated_power_kw:.1f} vs rated")
        c3.metric("Discharge Flow", f"{latest.flow_rate_m3h:.1f} m³/h")
        c4.metric("Bearing Temp", f"{latest.temperature_c:.1f} °C")
        c5.metric("Vibration RMS", f"{latest.vibration_mms:.2f} mm/s")

        # Threshold Configuration Expander
        with st.expander("⚙️ Adjust Diagnostic Thresholds for this Session"):
            th = st.session_state.thresholds
            col_t1, col_t2, col_t3, col_t4 = st.columns(4)
            th.vibration_warning_mms = col_t1.number_input("Vib Warning (mm/s)", value=float(th.vibration_warning_mms), step=0.1)
            th.vibration_critical_mms = col_t2.number_input("Vib Critical (mm/s)", value=float(th.vibration_critical_mms), step=0.1)
            th.temp_warning_c = col_t3.number_input("Temp Warning (°C)", value=float(th.temp_warning_c), step=1.0)
            th.temp_critical_c = col_t4.number_input("Temp Critical (°C)", value=float(th.temp_critical_c), step=1.0)

        # Build Interactive Time-Series Charts
        df_asset = pd.DataFrame([r.to_dict() for r in records])
        df_asset["timestamp"] = pd.to_datetime(df_asset["timestamp"])

        # Chart 1: Vibration Trend with ISO Zones
        fig_vib_trend = go.Figure()
        fig_vib_trend.add_trace(go.Scatter(
            x=df_asset["timestamp"],
            y=df_asset["vibration_mms"],
            mode="lines+markers",
            name="Vibration (mm/s RMS)",
            line=dict(color="#38bdf8", width=2.5),
            marker=dict(size=4),
        ))
        fig_vib_trend.add_hline(
            y=st.session_state.thresholds.vibration_warning_mms,
            line_dash="dash",
            line_color="#eab308",
            annotation_text=f"Warning ({st.session_state.thresholds.vibration_warning_mms} mm/s)",
        )
        fig_vib_trend.add_hline(
            y=st.session_state.thresholds.vibration_critical_mms,
            line_dash="dash",
            line_color="#ef4444",
            annotation_text=f"Critical ({st.session_state.thresholds.vibration_critical_mms} mm/s)",
        )
        fig_vib_trend.update_layout(
            title=f"Vibration Severity Trend (ISO 10816-3) - {cfg.name}",
            xaxis_title="Timestamp",
            yaxis_title="Vibration Velocity (mm/s RMS)",
            template="plotly_dark",
            height=340,
        )
        st.plotly_chart(fig_vib_trend, use_container_width=True)

        # Chart 2: Temperature & Power Trends
        col_c1, col_c2 = st.columns(2)
        with col_c1:
            fig_temp = go.Figure()
            fig_temp.add_trace(go.Scatter(
                x=df_asset["timestamp"],
                y=df_asset["temperature_c"],
                mode="lines",
                name="Temperature (°C)",
                line=dict(color="#f97316", width=2),
            ))
            fig_temp.add_hline(
                y=st.session_state.thresholds.temp_warning_c,
                line_dash="dash",
                line_color="#eab308",
                annotation_text=f"Warning ({st.session_state.thresholds.temp_warning_c}°C)",
            )
            fig_temp.add_hline(
                y=st.session_state.thresholds.temp_critical_c,
                line_dash="dash",
                line_color="#ef4444",
                annotation_text=f"Critical ({st.session_state.thresholds.temp_critical_c}°C)",
            )
            fig_temp.update_layout(
                title="Bearing / Casing Temperature Trend",
                xaxis_title="Timestamp",
                yaxis_title="Temperature (°C)",
                template="plotly_dark",
                height=300,
            )
            st.plotly_chart(fig_temp, use_container_width=True)

        with col_c2:
            fig_p = go.Figure()
            fig_p.add_trace(go.Scatter(
                x=df_asset["timestamp"],
                y=df_asset["power_kw"],
                mode="lines",
                name="Electrical Power (kW)",
                line=dict(color="#a855f7", width=2),
            ))
            fig_p.add_hline(
                y=cfg.rated_power_kw,
                line_dash="dot",
                line_color="#94a3b8",
                annotation_text=f"Rated ({cfg.rated_power_kw} kW)",
            )
            fig_p.update_layout(
                title="Motor Power Demand Trend",
                xaxis_title="Timestamp",
                yaxis_title="Motor Power (kW)",
                template="plotly_dark",
                height=300,
            )
            st.plotly_chart(fig_p, use_container_width=True)


# ==========================================
# PAGE C: ENERGY ANALYTICS
# ==========================================
elif navigation_page == "⚡ Energy Analytics":
    st.title("⚡ Energy Monitoring & Cost Accounting")
    st.markdown(
        """
        <div class="banner-disclaimer">
            <strong>Theoretical Baseline Accounting</strong>:
            Energy is computed via <code>Energy (kWh) = Average Power (kW) × Operating Time (hours)</code>.
            Excess energy consumption measures deviation against manufacturer design baseline.
            All savings calculations are hypothetical engineering estimates.
        </div>
        """,
        unsafe_allow_html=True,
    )

    df_all_telemetry = pd.DataFrame([r.to_dict() for records in telemetry_history.values() for r in records])
    kpi_records = [
        energy_engine.compute_equipment_kpis(df_all_telemetry, cfg)
        for cfg in fleet_configs.values()
    ]
    df_energy_kpis = pd.DataFrame([k.to_dict() for k in kpi_records])

    # Display KPI Metrics
    tot_kwh = sum(k.total_energy_kwh for k in kpi_records)
    tot_cost = sum(k.estimated_cost for k in kpi_records)
    tot_excess_kwh = sum(k.excess_energy_kwh for k in kpi_records)
    tot_excess_cost = sum(k.excess_cost for k in kpi_records)

    ec1, ec2, ec3, ec4 = st.columns(4)
    ec1.metric("Total Simulated Energy", f"{tot_kwh:,.1f} kWh")
    ec2.metric("Total Estimated Cost", f"₹{tot_cost:,.2f}")
    ec3.metric("Excess Energy Overload", f"{tot_excess_kwh:,.1f} kWh", help="Energy above nominal baseline")
    ec4.metric("Excess Cost Penalty", f"₹{tot_excess_cost:,.2f}", help="Estimated financial impact of degradation")

    st.markdown('<div class="section-header">Equipment Energy & Cost Breakdown</div>', unsafe_allow_html=True)
    st.dataframe(
        df_energy_kpis[[
            "equipment_id", "name", "total_operating_hours",
            "average_power_kw", "total_energy_kwh", "baseline_energy_kwh",
            "excess_energy_kwh", "estimated_cost", "excess_cost"
        ]],
        use_container_width=True,
        hide_index=True,
    )

    # Bar chart comparisons: Baseline vs Actual Energy
    col_eb, col_ec = st.columns(2)
    with col_eb:
        fig_en_bar = go.Figure()
        fig_en_bar.add_trace(go.Bar(
            name="Actual Energy Consumed (kWh)",
            x=df_energy_kpis["equipment_id"],
            y=df_energy_kpis["total_energy_kwh"],
            marker_color="#38bdf8",
        ))
        fig_en_bar.add_trace(go.Bar(
            name="Baseline Design Energy (kWh)",
            x=df_energy_kpis["equipment_id"],
            y=df_energy_kpis["baseline_energy_kwh"],
            marker_color="#64748b",
        ))
        fig_en_bar.update_layout(
            title="Actual vs Baseline Energy Consumption (kWh)",
            yaxis_title="Energy (kWh)",
            barmode="group",
            template="plotly_dark",
            height=320,
        )
        st.plotly_chart(fig_en_bar, use_container_width=True)

    with col_ec:
        fig_cost_bar = go.Figure()
        fig_cost_bar.add_trace(go.Bar(
            name="Standard Energy Cost (₹)",
            x=df_energy_kpis["equipment_id"],
            y=df_energy_kpis["estimated_cost"] - df_energy_kpis["excess_cost"],
            marker_color="#22c55e",
        ))
        fig_cost_bar.add_trace(go.Bar(
            name="Excess Penalty Cost (₹)",
            x=df_energy_kpis["equipment_id"],
            y=df_energy_kpis["excess_cost"],
            marker_color="#ef4444",
        ))
        fig_cost_bar.update_layout(
            title="Estimated Electricity Cost & Efficiency Penalty (₹)",
            yaxis_title="Cost in INR (₹)",
            barmode="stack",
            template="plotly_dark",
            height=320,
        )
        st.plotly_chart(fig_cost_bar, use_container_width=True)

    # Daily aggregation trend
    st.markdown('<div class="section-header">Daily Energy Aggregation Trend</div>', unsafe_allow_html=True)
    df_daily = energy_engine.aggregate_energy_trends(df_all_telemetry, freq="1D")
    if not df_daily.empty:
        fig_daily = px.line(
            df_daily,
            x="timestamp",
            y="energy_kwh",
            color="equipment_id",
            markers=True,
            title="Daily Total Energy Consumption Trend by Asset (kWh)",
            template="plotly_dark",
        )
        fig_daily.update_layout(height=320)
        st.plotly_chart(fig_daily, use_container_width=True)


# ==========================================
# PAGE D: FAULT SIMULATOR
# ==========================================
elif navigation_page == "🧪 Fault Simulator":
    st.title("🧪 Industrial Operational & Fault Scenario Simulator")
    st.markdown(
        """
        <div class="banner-disclaimer">
            <strong>Interactive Fault Injection Lab</strong>:
            Select any pump unit, inject an operational abnormality or degradation scenario,
            and observe the automated rule engine detect symptoms, update alarm registries,
            and recommend physical maintenance inspections.
        </div>
        """,
        unsafe_allow_html=True,
    )

    col_sim1, col_sim2 = st.columns([1, 1])

    with col_sim1:
        st.markdown('<div class="section-header">1. Select Target & Fault Scenario</div>', unsafe_allow_html=True)
        target_eq = st.selectbox(
            "Select Target Equipment",
            options=list(fleet_configs.keys()),
            format_func=lambda x: f"{x} - {fleet_configs[x].name}",
        )
        chosen_scenario_name = st.selectbox(
            "Select Operating Scenario",
            options=[s.value for s in FaultScenario],
            index=0,
        )

        st.info(f"**Current Active Scenario on {target_eq}**: {st.session_state.active_scenarios[target_eq]}")

        scol1, scol2, scol3 = st.columns(3)
        with scol1:
            if st.button("🚀 Inject Scenario", type="primary", use_container_width=True):
                st.session_state.active_scenarios[target_eq] = chosen_scenario_name
                st.session_state.trend_counters[target_eq] = 0
                st.success(f"Injected '{chosen_scenario_name}' on {target_eq}!")

        with scol2:
            if st.button("⏩ Advance 1 Hr Tick", use_container_width=True):
                # Generate single step for all pumps
                now_ts = telemetry_history[target_eq][-1].timestamp + timedelta(hours=1.0)
                new_batch = []
                for eq_id, sim in st.session_state.simulators.items():
                    scen_str = st.session_state.active_scenarios[eq_id]
                    scen_enum = FaultScenario(scen_str)
                    st.session_state.trend_counters[eq_id] += 1
                    t_step = st.session_state.trend_counters[eq_id]

                    pt = sim.generate_point(
                        timestamp=now_ts,
                        scenario=scen_enum,
                        delta_hours=1.0,
                        trend_step=t_step,
                    )
                    telemetry_history[eq_id].append(pt)
                    new_batch.append(pt)

                    # Evaluate health
                    vib_hist = [r.vibration_mms for r in telemetry_history[eq_id]]
                    new_alerts = health_engine.evaluate_telemetry(
                        pt, fleet_configs[eq_id], vib_hist
                    )
                    event_logger.log_alerts(new_alerts)

                event_logger.log_telemetry_batch(new_batch)
                st.rerun()

        with scol3:
            if st.button("🔄 Normal Recovery", use_container_width=True):
                st.session_state.active_scenarios[target_eq] = FaultScenario.RETURN_TO_NORMAL_OPERATION.value
                st.session_state.trend_counters[target_eq] = 0
                st.success(f"{target_eq} reset to Normal Operation recovery.")
                st.rerun()

    with col_sim2:
        st.markdown('<div class="section-header">2. Scenario Physics & Diagnostic Profile</div>', unsafe_allow_html=True)
        scenario_profiles = {
            FaultScenario.NORMAL_OPERATION.value: (
                "Normal Operation",
                "Healthy pump operation within ISO 10816-3 Zone A/B (<2.8 mm/s RMS). Nominal bearing temperatures (~60°C) and rated hydraulic flow."
            ),
            FaultScenario.ELEVATED_TEMPERATURE.value: (
                "Elevated Bearing Temperature",
                "Bearing temperature rises to 78-85°C. Caused by lubricant degradation, grease dry-out, or inadequate cooling water flow."
            ),
            FaultScenario.ELEVATED_VIBRATION.value: (
                "Elevated Vibration Severity",
                "Vibration breaches ISO Zone C/D (>4.5 mm/s RMS). Caused by dynamic rotor unbalance, shaft misalignment, or loose foundation anchor bolts."
            ),
            FaultScenario.INCREASING_VIBRATION_TREND.value: (
                "Progressive Degradation Trend",
                "Simulates developing fatigue: vibration increments by +0.22 mm/s per timestep, triggering linear regression trend alarms before catastrophic failure."
            ),
            FaultScenario.EXCESSIVE_OPERATING_HOURS.value: (
                "Operating Hours Overhaul Milestone",
                "Operating hours surpass 4,000h major overhaul interval, requiring scheduled preventive maintenance turnaround."
            ),
            FaultScenario.INCREASED_ENERGY_CONSUMPTION.value: (
                "Excess Power Overload",
                "Electrical power surges +28% above rated baseline due to internal recirculation, impeller fouling, or high-viscosity fluid handling."
            ),
            FaultScenario.REDUCED_SIMULATED_FLOW.value: (
                "Reduced Hydraulic Flow",
                "Discharge flow drops by >55% due to suction strainer blockage or closed discharge throttling, risking pump cavitation."
            ),
            FaultScenario.UNEXPECTED_EQUIPMENT_STOPPAGE.value: (
                "Sudden Trip / Stoppage",
                "Motor trips to STOPPED state while process line is live. Power and flow drop to 0, vibration falls to ambient baseline, triggering emergency lockout alarms."
            ),
            FaultScenario.COMBINED_ABNORMAL_CONDITIONS.value: (
                "Compound Cascade Failure",
                "Simultaneous severe vibration (>4.8 mm/s), high temperature (>82°C), and power overload, triggering highest-priority multi-fault alarm."
            ),
            FaultScenario.RETURN_TO_NORMAL_OPERATION.value: (
                "Post-Maintenance Normalization",
                "Simulates resolved maintenance: physical parameters stabilize back to manufacturer design benchmarks."
            ),
        }
        title_scen, desc_scen = scenario_profiles.get(chosen_scenario_name, ("", ""))
        st.markdown(f"**Scenario**: `{title_scen}`")
        st.write(desc_scen)

    # Diagnostic Response on Target Equipment
    st.markdown('<div class="section-header">Live Telemetry & Diagnostic Status</div>', unsafe_allow_html=True)
    target_latest = telemetry_history[target_eq][-1]
    tc1, tc2, tc3, tc4, tc5 = st.columns(5)
    tc1.metric("Current Status", target_latest.operating_status)
    tc2.metric("Vibration RMS", f"{target_latest.vibration_mms:.2f} mm/s")
    tc3.metric("Temperature", f"{target_latest.temperature_c:.1f} °C")
    tc4.metric("Motor Power", f"{target_latest.power_kw:.1f} kW")
    tc5.metric("Flow Rate", f"{target_latest.flow_rate_m3h:.1f} m³/h")

    target_alerts = [a for a in active_alerts if a.equipment_id == target_eq and a.is_active]
    if target_alerts:
        st.error(f"⚠️ {len(target_alerts)} Active Diagnostic Alert(s) Detected for {target_eq}:")
        for a in target_alerts:
            with st.container():
                st.markdown(f"**[{a.severity.value}] {a.condition.value}** - *{a.timestamp.strftime('%Y-%m-%d %H:%M:%S')}*")
                st.write(f"**Evidence**: {a.evidence}")
                st.write(f"**Possible Causes**: {'; '.join(a.possible_causes)}")
                st.write(f"**Recommended Action**: {' | '.join(a.recommended_inspections)}")
                st.markdown("---")
    else:
        st.success(f"✅ {target_eq} operating within normal industrial operating limits. No active alerts.")


# ==========================================
# PAGE E: MAINTENANCE CENTRE
# ==========================================
elif navigation_page == "🛠️ Maintenance Centre":
    st.title("🛠️ Maintenance Centre & Work-Order Triage")
    st.markdown(
        """
        <div class="banner-disclaimer">
            <strong>Explainable Maintenance Prioritization</strong>:
            Asset inspection priorities are determined using transparent industrial decision logic based on
            ISO 10816-3 severity tiers, active degradation slopes, operating hour thresholds, and thermal limits.
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Prioritize Fleet
    priority_list = maintenance_mgr.prioritize_fleet(
        fleet_configs, latest_telemetry, active_alerts
    )
    df_priority = pd.DataFrame([p.to_dict() for p in priority_list])

    st.markdown('<div class="section-header">Maintenance Prioritization Triage Matrix</div>', unsafe_allow_html=True)
    st.dataframe(
        df_priority[[
            "equipment_id", "name", "priority", "priority_score",
            "active_alerts_count", "maintenance_status", "reasons", "last_maintenance_date"
        ]],
        use_container_width=True,
        hide_index=True,
    )

    st.markdown('<div class="section-header">Work-Order Action & Status Update</div>', unsafe_allow_html=True)
    w_col1, w_col2, w_col3 = st.columns([1, 1, 1])

    with w_col1:
        target_maint_eq = st.selectbox(
            "Select Asset for Action",
            options=list(fleet_configs.keys()),
            format_func=lambda x: f"{x} - {fleet_configs[x].name}",
        )
    with w_col2:
        new_status_val = st.selectbox(
            "Update Maintenance Status",
            options=[
                MaintenanceStatus.NORMAL.value,
                MaintenanceStatus.INSPECTION_REQUIRED.value,
                MaintenanceStatus.WORK_ORDER_ISSUED.value,
                MaintenanceStatus.UNDER_MAINTENANCE.value,
                MaintenanceStatus.RESOLVED.value,
            ],
        )
    with w_col3:
        tech_note = st.text_input("Technician / Engineer Log Note", "Routine inspection completed per checklist.")

    if st.button("📝 Commit Maintenance Log Update", type="primary"):
        maintenance_mgr.update_status(
            equipment_id=target_maint_eq,
            new_status=new_status_val,
            technician_note=tech_note,
        )
        st.success(f"Updated {target_maint_eq} status to '{new_status_val}'!")
        st.rerun()

    # Maintenance Audit Trail
    st.markdown('<div class="section-header">Audit Trail: Logged Maintenance Events</div>', unsafe_allow_html=True)
    df_maint_logs = event_logger.load_maintenance_records()
    if not df_maint_logs.empty:
        st.dataframe(df_maint_logs, use_container_width=True, hide_index=True)
    else:
        st.info("No manual maintenance records committed yet in this session.")


# ==========================================
# PAGE F: REPORTS & AUDIT
# ==========================================
elif navigation_page == "📄 Reports & Audit":
    st.title("📄 Compliance Reports & Data Exports")
    st.markdown(
        """
        <div class="banner-disclaimer">
            <strong>Reliability Audit Center</strong>:
            Download complete historical records for statutory reporting, energy audits,
            and maintenance management system (CMMS) integrations.
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Executive Summary Card
    df_all_telemetry = pd.DataFrame([r.to_dict() for records in telemetry_history.values() for r in records])
    kpi_records = [
        energy_engine.compute_equipment_kpis(df_all_telemetry, cfg)
        for cfg in fleet_configs.values()
    ]
    summary = reporting_engine.compile_plant_summary(
        latest_telemetry, active_alerts, kpi_records
    )

    sc1, sc2, sc3, sc4 = st.columns(4)
    sc1.metric("Pumps in Fleet", summary["total_pumps"])
    sc2.metric("Active Alarms", summary["critical_alerts_count"] + summary["warning_alerts_count"])
    sc3.metric("Simulated Energy", f"{summary['total_energy_kwh']:,.0f} kWh")
    sc4.metric("Estimated Cost", f"₹{summary['total_cost']:,.0f}")

    st.markdown('<div class="section-header">Export Data Files (CSV)</div>', unsafe_allow_html=True)

    c_d1, c_d2 = st.columns(2)
    with c_d1:
        st.subheader("📊 Telemetry History")
        csv_telem = reporting_engine.generate_telemetry_csv()
        st.download_button(
            label="⬇️ Download Telemetry CSV",
            data=csv_telem,
            file_name=f"equipment_telemetry_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
            use_container_width=True,
        )

        st.subheader("⚡ Energy Summary")
        csv_energy = reporting_engine.generate_energy_summary_csv(kpi_records)
        st.download_button(
            label="⬇️ Download Energy Summary CSV",
            data=csv_energy,
            file_name=f"energy_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
            use_container_width=True,
        )

    with c_d2:
        st.subheader("🚨 Alarm History")
        csv_alarms = reporting_engine.generate_alarms_csv()
        st.download_button(
            label="⬇️ Download Alarm History CSV",
            data=csv_alarms,
            file_name=f"alarm_history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
            use_container_width=True,
        )

        st.subheader("🛠️ Maintenance Records")
        csv_maint = reporting_engine.generate_maintenance_csv()
        st.download_button(
            label="⬇️ Download Maintenance CSV",
            data=csv_maint,
            file_name=f"maintenance_records_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
            use_container_width=True,
        )

    st.markdown('<div class="section-header">Database Management</div>', unsafe_allow_html=True)
    with st.expander("⚠️ Reset Simulation Data (Destructive Action)"):
        st.warning("This action clears local persisted telemetry, alarm logs, and maintenance records.")
        confirm_check = st.checkbox("I confirm I wish to reset simulation data")
        if st.button("🗑️ Reset All Local Records", disabled=not confirm_check):
            event_logger.reset_data(confirm=True)
            st.success("All local simulation data reset successfully.")
            st.rerun()
