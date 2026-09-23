"""Incident-centred view of the hourly monitoring case."""

from __future__ import annotations

from pathlib import Path
import json
import pandas as pd


def separator_history(wells: pd.DataFrame) -> pd.DataFrame:
    """Hourly metering that is actually available to the monitoring agent."""
    return (wells.groupby(["hour", "timestamp"], as_index=False)
            .agg(plan_oil_tpd=("plan_oil_tpd", "sum"),
                 separator_oil_tpd=("actual_oil_tpd", lambda x: x.sum(min_count=len(x))),
                 separator_water_m3d=("water_rate_m3d", lambda x: x.sum(min_count=len(x)))))


def sparse_telemetry(wells: pd.DataFrame) -> pd.DataFrame:
    """Sparse well signals: they help diagnosis but are not well-rate measurements."""
    data = wells.copy()
    # Most wells report every three hours; alarmed wells send an event immediately.
    normal_sample = data["hour"] % 3 == 0
    event_sample = ((data["well_id"] == "W_BEL_27_TLBB") & (data["hour"] >= 4)) | \
                   ((data["well_id"] == "W_BEL_22_TLBB") & (data["hour"] >= 15))
    data = data[normal_sample | event_sample].copy()
    reference_path=Path(__file__).resolve().parents[1]/"data"/"gap_optimization_result_balanced.json"
    reference=json.loads(reference_path.read_text(encoding="utf-8"))
    frequencies={row["well_id"]:row["control_actual"] for row in reference["baseline"]["wells"] if "ESP" in str(row["well_type"])}
    data["frequency_hz"] = data["well_id"].map(frequencies)
    data.loc[(data["well_id"] == "W_BEL_22_TLBB") & (data["hour"] >= 15), "frequency_hz"] = 0.0
    data["sensor_pressure_bar"] = data["fbhp_bara"] - 7.0
    if 'sensor_pressure_bara' in data:
        selected=data.well_id=='W_BEL_27_TLBB'
        data.loc[selected,'sensor_pressure_bar']=data.loc[selected,'sensor_pressure_bara']
    return data[["hour", "timestamp", "well_id", "frequency_hz", "sensor_pressure_bar",
                 "fbhp_bara", "esp_current_a", "vibration_mm_s", "signal"]]


def opened_incidents(separator: pd.DataFrame, hour: int, threshold_pct: float = -5.0) -> pd.DataFrame:
    """Open on first limit crossing and on a new large step while already outside."""
    current = separator[separator["hour"] <= hour].sort_values('hour').reset_index(drop=True).copy()
    # Missing separator fact is neither recovery nor a new production event.
    current = current[current["separator_oil_tpd"].notna()].copy()
    current["deviation_pct"] = ((current["separator_oil_tpd"]-current["plan_oil_tpd"])
                                / current["plan_oil_tpd"]*100)
    outside = current["deviation_pct"] <= threshold_pct
    first_crossing = outside & ~outside.shift(fill_value=False)
    step_pct = current["separator_oil_tpd"].pct_change(fill_method=None) * 100
    additional_drop = outside & (step_pct <= threshold_pct)
    triggers = current[first_crossing | additional_drop]
    rows = []
    for number, (index, point) in enumerate(triggers.iterrows(), 1):
        is_additional = bool(additional_drop.loc[index])
        if is_additional:
            previous = current.loc[:index].iloc[-2]
            loss = float(previous["separator_oil_tpd"] - point["separator_oil_tpd"])
            signal = "Дополнительное резкое снижение нефти на сепараторе"
        else:
            loss = float(point["plan_oil_tpd"] - point["separator_oil_tpd"])
            signal = "Выход добычи нефти на сепараторе за нижнюю границу"
        rows.append({
            "incident_id": f"INC-{number:03d}", "opened_hour": int(point["hour"]),
            "signal": signal, "observed_loss_tpd": round(loss, 2),
            "status": "Ожидает решения",
        })
    return pd.DataFrame(rows, columns=["incident_id","opened_hour","signal","observed_loss_tpd","status"])


def write_initial_measurements(root: Path, folder: Path) -> None:
    """Generate the training day once; afterwards the agent reads only these CSV files."""
    from src import day_case
    wells, _ = day_case.build_hourly_case(root)
    folder.mkdir(parents=True, exist_ok=True)
    separator_history(wells).to_csv(folder / "separator.csv", index=False)
    signals = sparse_telemetry(wells).drop(columns=["fbhp_bara", "signal"])
    for column in ["whp_bara", "water_cut_pct", "gor_m3m3"]:
        signals[column] = float("nan")
    signals.to_csv(folder / "telemetry.csv", index=False)
