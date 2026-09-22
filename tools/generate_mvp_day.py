"""Generate a reproducible 24-hour dataset for the diagnostic MVP."""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
import csv
import random

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "mvp_day"
DENSITY = 0.908
SEED = 20260914


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    rng = random.Random(SEED)
    base = pd.read_csv(ROOT / "data" / "petex_baseline.csv")
    base["oil_tpd"] = base["oil_rate"] * DENSITY
    plan_oil = float(base.oil_tpd.sum())
    plan_water = float((base.liquid_rate - base.oil_rate).sum())
    start = datetime(2026, 9, 14)
    sep, signals, events = [], [], []

    # Ground truth is deliberately stored outside the agent input tables.
    truth = [
        {"incident_id":"INC-001","start_hour":6,"end_hour":9,"true_cause":"degraded_esp",
         "true_wells":"W_BEL_27_TLBB","physical_loss_tpd":4.60},
        {"incident_id":"INC-002","start_hour":11,"end_hour":13,"true_cause":"gathering_backpressure",
         "true_wells":"W_BEL_23_TLBB; W_BEL_24_TLBB; W_BEL_29_TLBB","physical_loss_tpd":10.80},
        {"incident_id":"INC-003","start_hour":15,"end_hour":18,"true_cause":"well_shutdown_power",
         "true_wells":"W_BEL_22_TLBB","physical_loss_tpd":29.61},
        {"incident_id":"INC-004","start_hour":21,"end_hour":22,"true_cause":"separator_meter_bias",
         "true_wells":"","physical_loss_tpd":0.00},
    ]

    for hour in range(24):
        ts = start + timedelta(hours=hour)
        physical_loss = 0.0
        meter_bias = 0.0
        if 4 <= hour <= 5: physical_loss += {4:1.2, 5:2.7}[hour]  # early warning, still in tolerance
        if 6 <= hour <= 9: physical_loss += 4.60
        if 11 <= hour <= 13: physical_loss += 10.80
        if 15 <= hour <= 18: physical_loss += 29.61
        if 21 <= hour <= 22: meter_bias = -11.50
        noise = rng.uniform(-0.18, 0.18)
        measured_oil = plan_oil - physical_loss + meter_bias + noise
        measured_water = plan_water + (1.4 if 11 <= hour <= 13 else 0) + rng.uniform(-0.08, .08)
        sep.append({
            "timestamp":ts.isoformat(), "hour":hour, "plan_oil_tpd":round(plan_oil,3),
            "separator_oil_tpd":round(measured_oil,3), "separator_water_m3d":round(measured_water,3),
            "separator_pressure_bar":round(9.8 + (1.7 if 11 <= hour <= 13 else 0) + rng.uniform(-.08,.08),2),
            "separator_level_pct":round(52 + rng.uniform(-1.2,1.2),1),
            "oil_meter_quality":"suspect" if 21 <= hour <= 22 else "good"
        })

        for _, well in base.iterrows():
            wid = well.well_id
            # Routine telemetry arrives every 3 hours; alarm changes arrive immediately.
            alarm = ((wid=="W_BEL_27_TLBB" and 4<=hour<=9) or
                     (wid in {"W_BEL_23_TLBB","W_BEL_24_TLBB","W_BEL_29_TLBB"} and 11<=hour<=13) or
                     (wid=="W_BEL_22_TLBB" and 15<=hour<=18))
            if hour % 3 != 0 and not alarm: continue
            frequency, current, vibration = 50.0, 48.0+rng.uniform(-.5,.5), 2.1+rng.uniform(-.08,.08)
            bhp = float(well.fbhp) + rng.uniform(-.25,.25)
            line_pressure = 18.0 + rng.uniform(-.15,.15)
            status = "running"
            if wid=="W_BEL_27_TLBB" and 4<=hour<=9:
                current += (hour-3)*1.2; vibration += (hour-3)*.25; bhp -= (hour-3)*1.1
            if wid in {"W_BEL_23_TLBB","W_BEL_24_TLBB","W_BEL_29_TLBB"} and 11<=hour<=13:
                line_pressure += 4.5; bhp += 2.2
            if wid=="W_BEL_22_TLBB" and 15<=hour<=18:
                frequency=0.0; current=0.0; vibration=0.0; status="stopped"
            signals.append({
                "timestamp":ts.isoformat(),"hour":hour,"well_id":wid,"esp_frequency_hz":round(frequency,1),
                "esp_current_a":round(current,2),"vibration_mm_s":round(vibration,2),
                "sensor_pressure_bar":round(bhp-7,2),"calculated_fbhp_bar":round(bhp,2),
                "wellhead_pressure_bar":round(line_pressure+2.5,2),"line_pressure_bar":round(line_pressure,2),
                "valve_open_pct":100,"well_status":status,"data_quality":"good"
            })

    events.extend([
        {"timestamp":(start+timedelta(hours=15)).isoformat(),"source":"VSD_W_BEL_22","event":"frequency_zero","quality":"confirmed"},
        {"timestamp":(start+timedelta(hours=15)).isoformat(),"source":"POWER_W_BEL_22","event":"undervoltage_trip","quality":"confirmed"},
        {"timestamp":(start+timedelta(hours=21)).isoformat(),"source":"SEP_OIL_METER","event":"diagnostic_drift","quality":"suspect"},
    ])
    write_csv(DATA / "separator_hourly.csv", sep)
    write_csv(DATA / "well_signals_sparse.csv", signals)
    write_csv(DATA / "event_log.csv", events)
    write_csv(DATA / "scenario_truth_for_evaluation_only.csv", truth)
    print(f"Created {len(sep)} separator rows, {len(signals)} sparse signals, {len(events)} events")


if __name__ == "__main__":
    main()
