# Verification & Test Plan: Industrial Pump Health & Energy Monitor

This document specifies the verification strategy, test cases, inputs, expected results, actual execution outputs, and pass/fail statuses for the Industrial Pump Health, Energy Monitoring & Predictive Maintenance System.

---

## 1. Automated Test Suite Execution Summary

- **Test Framework**: `pytest 9.1.1` on `Python 3.14.6` (Windows x64)
- **Total Test Cases**: 28 automated test cases
- **Passed**: 28
- **Failed**: 0
- **Execution Time**: ~0.87 seconds
- **Deterministic Test Data**: Seeded random numbers (`seed=42`, `seed=12345`) ensuring 100% reproducibility across environments.

---

## 2. Test Matrix & Detailed Results

| Test ID | Module | Scenario / Feature | Inputs | Expected Output | Actual Output | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **TC-SIM-01** | `equipment_simulator` | Seed Determinism | Two instances seeded with `12345` | Identical power, flow, temp, and vibration readings | Identical telemetry generated | **PASS** |
| **TC-SIM-02** | `equipment_simulator` | Normal Operation Physics | 50 kW pump running normally, `delta_hours=1.0` | Power $\in [40, 55]$ kW, Temp $\in [55, 65]^\circ\text{C}$, Vib $\in [1.4, 2.2]$ mm/s | Power 46.1 kW, Temp 59.8°C, Vib 1.82 mm/s | **PASS** |
| **TC-SIM-03** | `equipment_simulator` | Stoppage Physics & Constraints | Scenario = Unexpected Stoppage | Power = 0 kW, Flow = 0 m³/h, Vib < 0.5 mm/s, Temp decays | Power 0.0 kW, Flow 0.0 m³/h, Vib 0.14 mm/s | **PASS** |
| **TC-SIM-04** | `equipment_simulator` | Zero Operating Time | `delta_hours = 0.0` | Operating hours and cumulative energy remain unchanged | Unchanged hours and energy values | **PASS** |
| **TC-SIM-05** | `equipment_simulator` | Energy Accumulation | Running at rated load for 2.0 hours | $\Delta \text{Energy} = \text{Power} \times 2.0$ | Cumulative energy increment matches $\text{kW} \times 2.0$ exactly | **PASS** |
| **TC-SIM-06** | `equipment_simulator` | Increasing Trend Progression | Trend steps 0, 5, 15 | Monotonically increasing vibration breaching Zone D (4.5 mm/s) | Step 0: 1.8 mm/s $\to$ Step 15: 4.9 mm/s | **PASS** |
| **TC-SIM-07** | `equipment_simulator` | Fleet Initialization | `get_default_fleet_configs()` | 4 industrial pumps (P-101 to P-104) initialized | 4 distinct pump configs returned | **PASS** |
| **TC-MON-01** | `health_monitor` | Temperature Warning Limit | Temperature = 78.0°C (Warning limit = 75°C) | Warning alert raised with lubrication advice | Alert `High Bearing/Casing Temperature` (Warning) | **PASS** |
| **TC-MON-02** | `health_monitor` | Temperature Critical Limit | Temperature = 88.0°C (Critical limit = 85°C) | Critical alert raised recommending thermal imaging / trip | Alert `High Bearing/Casing Temperature` (Critical) | **PASS** |
| **TC-MON-03** | `health_monitor` | Vibration Warning Limit | Vibration = 3.50 mm/s (ISO Zone C limit = 2.80 mm/s) | Warning alert raised with alignment recommendation | Alert `High Vibration Severity` (Warning) | **PASS** |
| **TC-MON-04** | `health_monitor` | Vibration Critical Limit | Vibration = 5.20 mm/s (ISO Zone D limit = 4.50 mm/s) | Critical alert raised recommending emergency trip / LOTO | Alert `High Vibration Severity` (Critical) | **PASS** |
| **TC-MON-05** | `health_monitor` | Upward Trend Regression | History: `[2.0, 2.3, 2.6, 2.9, 3.2]` mm/s | Trend detected; slope calculated $\ge 0.12$ mm/s/step | Slope = +0.30 mm/s/step, Warning alert raised | **PASS** |
| **TC-MON-06** | `health_monitor` | Flat Trend No-False-Alarm | History: `[1.80, 1.85, 1.79, 1.82, 1.81]` mm/s | No trend alarm triggered | No trend alarm triggered (is_trending=False) | **PASS** |
| **TC-MON-07** | `health_monitor` | Operating Hours Milestone | Operating hours = 4150h (Service limit = 4000h) | Warning alert raised for scheduled major overhaul | Alert `Operating Hours Service Threshold Exceeded` | **PASS** |
| **TC-MON-08** | `health_monitor` | Power Overload Alert | Motor draw 92 kW on 75 kW pump (> 15% rated) | Power overload alert raised | Alert `Abnormal Power Overload` (Warning) | **PASS** |
| **TC-MON-09** | `health_monitor` | Unexpected Stoppage Alert | Status = Stopped while under process load | Critical alert raised for motor trip / interlock | Alert `Unexpected Equipment Stoppage` (Critical) | **PASS** |
| **TC-MON-10** | `health_monitor` | Alarm Deduplication | Repeated evaluation of identical fault condition | Single active alert updated, no duplicate entries in log | Active alert updated in place; alert count = 1 | **PASS** |
| **TC-MON-11** | `health_monitor` | Fault Recovery & Clearance | Parameter normalizes from 80°C to 62°C | Active alert removed from active registry, resolved timestamp set | Active alert cleared (`is_active = False`) | **PASS** |
| **TC-NRG-01** | `energy_analytics` | Standard Energy Formula | 50.0 kW power for 10.0 hours | $\text{Energy} = 50.0 \times 10.0 = 500.0\text{ kWh}$ | Energy = 500.0 kWh | **PASS** |
| **TC-NRG-02** | `energy_analytics` | Fractional Energy Formula | 72.5 kW power for 3.5 hours | $\text{Energy} = 72.5 \times 3.5 = 253.75\text{ kWh}$ | Energy = 253.75 kWh | **PASS** |
| **TC-NRG-03** | `energy_analytics` | Standard Cost Formula | 1000.0 kWh @ ₹8.50/kWh tariff | $\text{Cost} = 1000.0 \times 8.50 = ₹8,500.00$ | Cost = ₹8,500.00 | **PASS** |
| **TC-NRG-04** | `energy_analytics` | Tariff Override | 1000.0 kWh @ ₹10.00/kWh | $\text{Cost} = 1000.0 \times 10.00 = ₹10,000.00$ | Cost = ₹10,000.00 | **PASS** |
| **TC-NRG-05** | `energy_analytics` | Zero & Negative Guard | Zero power, negative hours, or zero tariff | Returns 0.0 without division errors or exceptions | Returned 0.0 cleanly | **PASS** |
| **TC-NRG-06** | `energy_analytics` | Baseline Variance & Excess | Actual 70 kW vs Baseline 67.5 kW for 24h | Total 1680 kWh, Baseline 1620 kWh, Excess 60 kWh | Excess 60.0 kWh, Excess cost ₹510.00 | **PASS** |
| **TC-NRG-07** | `energy_analytics` | Daily Trend Aggregation | 48 hourly readings across 2 calendar days | 2 resampled daily records with 24 hours each | 2 resampled day buckets, 1200 kWh/day | **PASS** |
| **TC-MNT-01** | `maintenance_mgr` | Healthy Low Priority | All readings within ISO normal limits | Priority = Low, Score $\le 25.0$ | Priority = Low, Score = 10.0 | **PASS** |
| **TC-MNT-02** | `maintenance_mgr` | Emergency Critical Priority | Active Critical alert (Zone D vibration) | Priority = Critical, Score $\ge 60.0$, Immediate LOTO action | Priority = Critical, Score = 60.0, LOTO action | **PASS** |
| **TC-MNT-03** | `maintenance_mgr` | High Priority Escalation | Active progressive trend or multiple warnings | Priority = High, Score $\in [50, 90]$ | Priority = High, Score = 58.0 | **PASS** |
| **TC-MNT-04** | `maintenance_mgr` | Medium Priority Triage | Single warning alert | Priority = Medium, Score $\in [30, 60]$ | Priority = Medium, Score = 45.0 | **PASS** |
| **TC-MNT-05** | `maintenance_mgr` | Workflow Audit Logging | Status transition to 'Inspected' | Audit record appended to CSV, last maintenance date set | Status updated, CSV entry verified | **PASS** |
| **TC-REP-01** | `reporting` | Empty CSV Exports | Zero records in database | Valid CSV header returned without crashing | Valid headers generated for all 4 tables | **PASS** |
| **TC-REP-02** | `reporting` | CSV Export Formatting | Database with telemetry & alarms | Valid RFC-4180 CSV with equipment ID, timestamp, values | Correct CSV text format produced | **PASS** |
| **TC-REP-03** | `reporting` | Executive Plant Rollup | Multi-pump status and energy KPIs | Accurate count of running/stopped units and cost sums | Summary totals matched input data | **PASS** |
| **TC-REP-04** | `reporting` | Safe Data Reset | Reset call with confirm=False vs True | False leaves files intact; True safely unlinks files | Files untouched on False, deleted on True | **PASS** |

---

## 3. UI and Demonstration Verification Check

In addition to the 28 automated tests, the following manual verification checks were verified against the Streamlit interface:
1. **Plant Overview**: Real-time fleet KPI metrics render with status pills, dynamic Plotly bar charts, and ISO 10816-3 threshold lines.
2. **Equipment Monitoring**: Selector accurately updates time-series graphs for Vibration (with Zone C and D lines), Temperature, and Electrical Power.
3. **Energy Analytics**: Multi-pump comparison bars properly separate design baseline consumption from excess energy overload penalties.
4. **Fault Simulator**: Injecting each of the 10 scenarios updates the target pump's telemetry immediately, generates explainable alarms, and clicking *Normal Recovery* restores nominal conditions.
5. **Maintenance Centre**: Work-order triage table prioritizes units by severity; technician notes commit directly to the persistent audit log.
6. **Reports & Audit**: Download buttons for Telemetry, Alarms, Energy, and Maintenance CSVs export clean, parseable data.
