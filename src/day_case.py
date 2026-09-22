"""Transparent 24-hour MVP simulation based on the calculated GAP baseline."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
import json

import pandas as pd


OIL_DENSITY_T_M3 = 0.908
TOLERANCE_PCT = -5.0
CONFIRMATION_HOURS = 1


@dataclass(frozen=True)
class IncidentSpec:
    incident_id: str
    well_id: str
    title: str
    hypothesis: str
    verification: str
    action: str
    gain_fraction: float
    cost_mln_rub: float
    team_hours: float


INCIDENTS = {
    "W_BEL_27_TLBB": IncidentSpec(
        "INC-001", "W_BEL_27_TLBB", "Снижение производительности УЭЦН",
        "Ухудшение работы насосного оборудования",
        "Рост тока и вибрации совпадает со снижением дебита относительно расчётной базовой точки.",
        "Доадаптация модели и расчёт компенсации соседними скважинами", 0.70, 0.8, 6,
    ),
    "W_BEL_22_TLBB": IncidentSpec(
        "INC-002", "W_BEL_22_TLBB", "Остановка добывающей скважины",
        "Остановка УЭЦН или потеря электропитания",
        "Дебит нефти и жидкости одновременно упал до нуля; перед перезапуском требуется подтвердить состояние оборудования.",
        "Диагностика причины остановки и безопасный перезапуск УЭЦН", 0.80, 0.35, 4,
    ),
}


def build_hourly_case(project: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    baseline = pd.read_csv(project / "data" / "petex_baseline.csv")
    baseline = baseline[baseline["oil_rate"].notna()].copy()
    baseline["plan_oil_tpd"] = baseline["oil_rate"] * OIL_DENSITY_T_M3
    start = datetime(2026, 9, 14, 0, 0)
    from src.physical_scenario_validation import validate
    audit=json.loads((project/'data'/'prosper_diagnostic_audit_W27.json').read_text(encoding='utf-8'))
    sensor=json.loads((project/'config'/'diagnostic_sensors.json').read_text(encoding='utf-8'))['W_BEL_27_TLBB']
    verification=validate(audit,sensor['pressure_residual_tolerance_bar'])
    if not verification['ready']:
        raise ValueError('Сценарий W27 не согласован: '+ '; '.join(verification['issues']))
    cases={case['case']:case for case in audit['physical_scenarios']['cases']}
    wc=audit['physical_scenarios']['fixed_conditions']['wc_pct']/100
    baseline.loc[baseline.well_id=='W_BEL_27_TLBB','plan_oil_tpd']=cases['baseline']['liquid_rate_stbd']*.158987294928*(1-wc)*OIL_DENSITY_T_M3
    baseline.loc[baseline.well_id=='W_BEL_27_TLBB','liquid_rate']=cases['baseline']['liquid_rate_stbd']*.158987294928
    baseline.loc[baseline.well_id=='W_BEL_27_TLBB','oil_rate']=cases['baseline']['liquid_rate_stbd']*.158987294928*(1-wc)
    rows: list[dict[str, object]] = []

    for hour in range(24):
        timestamp = start + timedelta(hours=hour)
        for _, well in baseline.iterrows():
            well_id = well["well_id"]
            factor = 1.0
            status = "fact_received"
            signal = "Норма"
            current = 48.0
            vibration = 2.1
            fbhp = float(well["fbhp"])

            if well_id == "W_BEL_27_TLBB":
                # The object first enters an early-warning zone, then crosses
                # the separator-level -5% incident threshold at hour 6.
                label={4:'pump_mild',5:'pump_severe'}.get(hour,'pump_failure' if hour>=6 else 'baseline')
                physical=cases[label]
                factor=physical['liquid_rate_stbd']/cases['baseline']['liquid_rate_stbd']
                fbhp=physical['bottom_pressure_psig']*.0689475729+1.01325
                current = float('nan')
                vibration = 2.1 + max(hour - 3, 0) * 0.18
                if hour >= 4:
                    signal = "Изменение давления приёма и вибрации при неизменной частоте"
            elif well_id == "W_BEL_50_TLBB" and hour >= 15:
                factor = max(0.72, 1.0 - (hour - 14) * 0.055)
                fbhp = max(74.0, float(well["fbhp"]) - (hour - 14) * 1.1)
                signal = "Снижение дебита и FBHP"
            elif well_id == "W_BEL_22_TLBB" and hour in {11, 12}:
                status = "fact_missing"
                signal = "Факт не поступил"
            elif well_id == "W_BEL_22_TLBB" and hour >= 15:
                factor = 0.0
                signal = "Полная остановка: дебит нефти и жидкости равен нулю"

            plan = float(well["plan_oil_tpd"])
            actual = None if status == "fact_missing" else plan * factor
            deviation = None if actual is None else (actual - plan) / plan * 100
            rows.append({
                "timestamp": timestamp, "hour": hour, "well_id": well_id,
                "plan_oil_tpd": round(plan, 3),
                "actual_oil_tpd": None if actual is None else round(actual, 3),
                "water_rate_m3d": None if actual is None else round(
                    float(well["liquid_rate"] - well["oil_rate"]) * factor, 3),
                "deviation_pct": None if deviation is None else round(deviation, 2),
                "fact_status": status, "signal": signal,
                "fbhp_bara": round(fbhp, 2), "esp_current_a": round(current, 2),
                "sensor_pressure_bara": physical['intake_pressure_psig']*.0689475729+1.01325 if well_id=='W_BEL_27_TLBB' else None,
                "vibration_mm_s": round(vibration, 2),
            })

    wells = pd.DataFrame(rows)
    timeline = evaluate_hours(wells)
    return wells, timeline


def evaluate_hours(wells: pd.DataFrame) -> pd.DataFrame:
    records: list[dict[str, object]] = []
    opened: set[str] = set()
    for hour in range(24):
        current = wells[wells["hour"] == hour]
        missing = current[current["fact_status"] == "fact_missing"]["well_id"].tolist()
        watch = current[(current["deviation_pct"] <= -2.0) & (current["deviation_pct"] > TOLERANCE_PCT)]["well_id"].tolist()
        outside: list[str] = []
        triggered: list[str] = []
        for well_id, group in wells[wells["hour"] <= hour].groupby("well_id"):
            last = group.tail(CONFIRMATION_HOURS)
            latest = group.tail(1).iloc[0]
            if pd.notna(latest["deviation_pct"]) and latest["deviation_pct"] <= TOLERANCE_PCT:
                outside.append(well_id)
            if (len(last) == CONFIRMATION_HOURS and last["deviation_pct"].notna().all()
                    and (last["deviation_pct"] <= TOLERANCE_PCT).all()):
                triggered.append(well_id)

        new_incidents = [w for w in triggered if w in INCIDENTS and INCIDENTS[w].incident_id not in opened]
        opened.update(INCIDENTS[w].incident_id for w in new_incidents)
        active = sorted(opened)
        if missing:
            state = "Ожидание/коррекция данных"
            explanation = "Нет свежего факта: отклонение не подтверждаем и оптимизацию по этой скважине не запускаем"
        elif new_incidents:
            state = "Рекомендация готова — ожидает утверждения"
            explanation = ("В одном запуске: обнаружено отклонение → сформированы и проверены гипотезы → "
                           "доадаптирована модель → рассчитаны компенсирующие режимы → выбрана рекомендация")
        elif active:
            state = "Ожидание утверждения"
            explanation = "Новые режимы рассчитаны; требуется решение инженера перед передачей оператору"
        elif outside:
            state = "Наблюдение за отклонением"
            explanation = "Есть выход за допуск, но требуется подтверждение следующим часовым запуском"
        elif watch:
            state = "Ухудшение замечено — пока в допуске"
            explanation = "Тренд ухудшился, но допустимая граница ещё не пересечена; продолжаем почасовой контроль"
        else:
            state = "Штатный мониторинг"
            explanation = "Отклонений, требующих действия, нет"
        records.append({
            "hour": hour, "timestamp": current["timestamp"].iloc[0], "state": state,
            "missing_fact": ", ".join(missing), "outside_tolerance": ", ".join(outside),
            "within_tolerance_watch": ", ".join(watch),
            "new_incidents": ", ".join(INCIDENTS[w].incident_id for w in new_incidents),
            "active_incidents": ", ".join(active),
            "steps_completed": ("качество → отклонение → гипотезы → проверка → доадаптация → "
                                "оптимизация → HITL") if new_incidents else "мониторинг",
            "explanation": explanation,
        })
    return pd.DataFrame(records)


def incident_table(wells: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for spec in INCIDENTS.values():
        data = wells[wells["well_id"] == spec.well_id]
        min_row = data.loc[data["deviation_pct"].idxmin()]
        baseline = float(data["plan_oil_tpd"].iloc[0])
        loss = baseline - float(min_row["actual_oil_tpd"])
        gain = baseline * spec.gain_fraction
        rows.append({
            "Инцидент": spec.incident_id, "Скважина": spec.well_id,
            "Проблема": spec.title, "Мин. отклонение, %": min_row["deviation_pct"],
            "Недобор, т/сут": round(loss, 2), "Гипотеза": spec.hypothesis,
            "Проверка": spec.verification, "Вердикт": "поддержана",
            "Мероприятие": spec.action, "Расчётный эффект, т/сут": round(gain, 2),
            "Стоимость, млн руб": spec.cost_mln_rub, "Бригада, ч": spec.team_hours,
            "Источник эффекта": "реестр возможностей",
        })
    return pd.DataFrame(rows)


def compensation_table(wells: pd.DataFrame) -> pd.DataFrame:
    """Concrete candidate regimes used to compensate the W_BEL_27 shortfall."""
    latest = wells[wells["hour"] == wells["hour"].max()].set_index("well_id")
    candidates = [
        ("W_BEL_31_TLBB", 2.00, "Увеличить частоту УЭЦН на 1 Гц", 0.15, 0.0),
        ("W_BEL_13_TLBB", 1.80, "Увеличить частоту УЭЦН на 1 Гц", 0.15, 0.0),
        ("W_BEL_12_TLBB", 1.80, "Увеличить частоту УЭЦН на 1 Гц", 0.15, 0.0),
        ("W_BEL_25_TLBB", -1.00, "Снизить отбор высокообводнённой скважины", 0.05, 0.0),
    ]
    rows = []
    for well_id, gain, action, cost, hours in candidates:
        current = float(latest.loc[well_id, "actual_oil_tpd"])
        rows.append({
            "Скважина": well_id, "Текущий режим, т/сут": round(current, 2),
            "Изменение режима": action, "Новый дебит, т/сут": round(current + gain, 2),
            "Прирост, т/сут": gain, "Стоимость, млн руб": cost,
            "Работа бригады, ч": hours, "Решение": "рекомендовано",
            "FBHP, бар": round(float(latest.loc[well_id, "fbhp_bara"]), 1),
        })
    return pd.DataFrame(rows)


def opportunity_register(wells: pd.DataFrame) -> pd.DataFrame:
    selected = compensation_table(wells)
    selected["Тип выполнения"] = ["АСУТП", "АСУТП", "АСУТП", "АСУТП"]
    selected["Мобилизация, ч"] = 0.0
    selected["Длительность, ч"] = 0.1
    selected["Изменение воды, м³/сут"] = [0.01, 0.00, 0.00, -0.80]
    extra = pd.DataFrame([
        {"Скважина": "W_BEL_23_TLBB", "Текущий режим, т/сут": 22.38,
         "Изменение режима": "Увеличить частоту УЭЦН на 2 Гц", "Новый дебит, т/сут": 24.48,
         "Прирост, т/сут": 2.10, "Стоимость, млн руб": 0.20,
         "Работа бригады, ч": 0.0, "Решение": "отклонено: ограничение по току", "FBHP, бар": 129.3,
         "Тип выполнения": "АСУТП", "Мобилизация, ч": 0.0, "Длительность, ч": 0.1,
         "Изменение воды, м³/сут": 0.03},
        {"Скважина": "W_BEL_29_TLBB", "Текущий режим, т/сут": 20.50,
         "Изменение режима": "Изменить режим ВШН", "Новый дебит, т/сут": 21.40,
         "Прирост, т/сут": 0.90, "Стоимость, млн руб": 0.35,
         "Работа бригады, ч": 4.0, "Решение": "допустимо, но не выбрано", "FBHP, бар": 123.6,
         "Тип выполнения": "выезд бригады", "Мобилизация, ч": 2.0, "Длительность, ч": 4.0,
         "Изменение воды, м³/сут": 0.10},
        {"Скважина": "W_BEL_55_TLBB", "Текущий режим, т/сут": 17.88,
         "Изменение режима": "Оптимизировать штуцер", "Новый дебит, т/сут": 18.48,
         "Прирост, т/сут": 0.60, "Стоимость, млн руб": 0.08,
         "Работа бригады, ч": 0.0, "Решение": "допустимо, но эффект ниже", "FBHP, бар": 117.4,
         "Тип выполнения": "АСУТП", "Мобилизация, ч": 0.0, "Длительность, ч": 0.1,
         "Изменение воды, м³/сут": 0.01},
        {"Скважина": "W_BEL_27_TLBB", "Текущий режим, т/сут": 26.07,
         "Изменение режима": "Стряхивание насоса", "Новый дебит, т/сут": 29.50,
         "Прирост, т/сут": 3.43, "Стоимость, млн руб": 0.18,
         "Работа бригады, ч": 3.0, "Решение": "резерв: после диагностики", "FBHP, бар": 127.6,
         "Тип выполнения": "выезд бригады", "Мобилизация, ч": 2.0, "Длительность, ч": 1.0,
         "Изменение воды, м³/сут": 0.02},
        {"Скважина": "W_BEL_25_TLBB", "Текущий режим, т/сут": 3.75,
         "Изменение режима": "Промывка скважины", "Новый дебит, т/сут": 5.20,
         "Прирост, т/сут": 1.45, "Стоимость, млн руб": 0.45,
         "Работа бригады, ч": 8.0, "Решение": "планирование за пределами суток", "FBHP, бар": 132.6,
         "Тип выполнения": "выезд бригады", "Мобилизация, ч": 3.0, "Длительность, ч": 5.0,
         "Изменение воды, м³/сут": 1.10},
        {"Скважина": "W_BEL_11_TLBB", "Текущий режим, т/сут": 2.69,
         "Изменение режима": "ГТМ: обработка призабойной зоны", "Новый дебит, т/сут": 7.00,
         "Прирост, т/сут": 4.31, "Стоимость, млн руб": 3.20,
         "Работа бригады, ч": 72.0, "Решение": "долгосрочный кандидат", "FBHP, бар": 90.1,
         "Тип выполнения": "ГТМ", "Мобилизация, ч": 24.0, "Длительность, ч": 48.0,
         "Изменение воды, м³/сут": 2.90},
    ])
    return pd.concat([selected, extra], ignore_index=True)


def apply_approved_actions(wells: pd.DataFrame, approvals: dict[str, object]) -> pd.DataFrame:
    """Apply an approved recommendation from the next simulated hour."""
    result = wells.copy()
    first = approvals.get("INC-001")
    if isinstance(first, dict) and first.get("status") == "Утверждено":
        start = int(first["hour"]) + 1
        changes = {"W_BEL_31_TLBB": (2.0, 0.01), "W_BEL_13_TLBB": (1.8, 0.00),
                   "W_BEL_12_TLBB": (1.8, 0.00), "W_BEL_25_TLBB": (-1.0, -0.80)}
        for well_id, (gain, water_delta) in changes.items():
            mask = (result["hour"] >= start) & (result["well_id"] == well_id)
            result.loc[mask, "actual_oil_tpd"] += gain
            result.loc[mask, "water_rate_m3d"] += water_delta
            result.loc[mask, "signal"] = "Применён утверждённый компенсирующий режим"

    second = approvals.get("INC-002")
    if isinstance(second, dict) and second.get("status") == "Утверждено":
        # Выездное мероприятие: 2 часа мобилизации + 2 часа диагностики/работы.
        # До завершения этих четырёх часов скважина остаётся остановленной.
        start = int(second["hour"]) + 4
        mask = (result["hour"] >= start) & (result["well_id"] == "W_BEL_22_TLBB")
        result.loc[mask, "actual_oil_tpd"] = result.loc[mask, "plan_oil_tpd"] * 0.80
        result.loc[mask, "water_rate_m3d"] = 0.9
        result.loc[mask, "signal"] = "Утверждённый перезапуск: восстановлено 80% режима"

    valid = result["actual_oil_tpd"].notna()
    result.loc[valid, "deviation_pct"] = (
        (result.loc[valid, "actual_oil_tpd"] - result.loc[valid, "plan_oil_tpd"])
        / result.loc[valid, "plan_oil_tpd"] * 100
    ).round(2)
    return result
