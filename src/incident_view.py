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


def ranked_hypotheses(project: Path, incident_id: str) -> pd.DataFrame:
    if incident_id == "INC-002":
        matrix = pd.read_csv(project / "data" / "ima_shutdown_matrix.csv")
        matrix["predicted_loss_tpd"] = matrix["predicted_oil_loss_sm3d"] * 0.908
        observed = 29.61
        matrix["mismatch_tpd"] = (matrix["predicted_loss_tpd"] - observed).abs()
        matrix["score"] = (100 - matrix["mismatch_tpd"] / observed * 100).clip(lower=0)
        ranked = matrix.sort_values("mismatch_tpd").head(6).copy()
        ranked["hypothesis"] = "Остановка " + ranked["well_id"]
        ranked["evidence"] = "GAP: расчёт полного отключения одной скважины. Близость потери не подтверждает локализацию."
    else:
        ranked = pd.DataFrame([
            {"hypothesis": "Снижение эффективности УЭЦН W_BEL_27_TLBB", "well_id": "W_BEL_27_TLBB", "predicted_loss_tpd": 15.33, "mismatch_tpd": 0.00, "score": 92, "evidence": "Ток и вибрация растут при неизменной частоте; потеря половины режима воспроизведена"},
            {"hypothesis": "Снижение притока W_BEL_27_TLBB", "well_id": "W_BEL_27_TLBB", "predicted_loss_tpd": 14.70, "mismatch_tpd": .63, "score": 71, "evidence": "Объясняет баланс, но хуже согласуется с телеметрией УЭЦН"},
            {"hypothesis": "Ограничение ветви системы сбора", "well_id": "W_BEL_23_TLBB", "predicted_loss_tpd": 13.90, "mismatch_tpd": 1.43, "score": 46, "evidence": "Близкий порядок потери, но группового роста линейного давления нет"},
            {"hypothesis": "Ошибка расходомера сепаратора", "well_id": "—", "predicted_loss_tpd": 0.0, "mismatch_tpd": 15.33, "score": 18, "evidence": "Резервная гипотеза; независимые давления показывают реальное изменение"},
        ])
    ranked.insert(0, "rank", range(1, len(ranked) + 1))
    if incident_id != "INC-002":
        ranked["predicted_loss_tpd"] = float("nan")
        ranked["mismatch_tpd"] = float("nan")
        ranked["evidence"] = [
            "Телеметрия W27: рост давления приёма и вибрации при неизменной частоте. Ток пока недоступен. Это признаки, не подтверждение причины.",
            "Альтернативная версия W27. Для различения нужна текущая точка Q–Pзаб и сопоставление с прежней IPR.",
            "Альтернативная групповая причина. Нужны устьевые и линейные давления; расчёт не выполнен.",
            "Альтернативная причина сигнала. Нужна независимая проверка измерения сепаратора.",
        ]
    ranked["check_source"] = "GAP: полное отключение" if incident_id == "INC-002" else "Телеметрия; расчёт PROSPER не выполнен"
    ranked["missing_data"] = "Статус оборудования и дополнительные сигналы для локализации" if incident_id == "INC-002" else "Текущий дебит или его диапазон, приведённое Pзаб, устьевое давление, актуальные ГФ и обводнённость"
    return ranked[["rank", "hypothesis", "well_id", "predicted_loss_tpd", "mismatch_tpd", "evidence", "check_source", "missing_data"]]
