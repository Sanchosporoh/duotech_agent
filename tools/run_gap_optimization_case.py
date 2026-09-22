"""Run one transparent constrained optimisation case in a GAP working copy.

No GAP save command is issued. Economic and resource ranking intentionally stays
outside GAP; this script only solves the physical optimisation problem.
"""

from __future__ import annotations

import json
import argparse
import sys
import time
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "petex_passport_ima"))

import petex_apps  # noqa: E402
from open_server import OpenServer, OpenServerError  # noqa: E402


MODEL = ROOT / "runtime" / "petex_case" / "IM_2022_06" / "BEL_PROD.gap"
CASE_FILE = ROOT / "config" / "gap_optimization_case.json"
OUTPUT = ROOT / "data" / "gap_optimization_case_result.json"
UNSET = 1e20


def get(os: OpenServer, expression: str) -> object | None:
    try:
        raw = os.get_value(expression)
        if raw == "":
            return None
        try:
            number = float(raw)
            return None if abs(number) >= UNSET else number
        except (TypeError, ValueError):
            return str(raw)
    except (OpenServerError, ValueError, TypeError):
        return None


def labels(os: OpenServer, expression: str) -> list[str]:
    try:
        return [str(x) for x in os.get_value_array(expression) if str(x)]
    except (OpenServerError, ValueError, TypeError):
        return []


def result(os: OpenServer) -> dict[str, object]:
    mod = "GAP.MOD[{PROD}]"
    rows = []
    for well_id in labels(os, f"{mod}.WELL[$].Label"):
        tag = f"{mod}.WELL[{{{well_id}}}]"
        res = f"{tag}.SolverResults[0]"
        rows.append({
            "well_id": well_id,
            "well_type": get(os, f"{tag}.TypeWell"),
            "oil_sm3d": get(os, f"{res}.OilRate"),
            "water_m3d": get(os, f"{res}.WatRate"),
            "fbhp_bar": get(os, f"{res}.FBHP"),
            "control_mode": get(os, f"{tag}.AlqControl"),
            "control_actual": get(os, f"{tag}.AlqValue"),
            "control_optimised": get(os, f"{tag}.AlqValueOptimised")
                or get(os, f"{tag}.AlqOptimised"),
            "control_min": get(os, f"{tag}.AlqValueMin"),
            "control_max": get(os, f"{tag}.AlqValueMax"),
        })
    total = f"{mod}.SystemTotal[0]"
    status = f"{mod}.SolverStatusList[0]"
    return {
        "oil_sm3d": get(os, f"{total}.OilRate"),
        "water_m3d": get(os, f"{total}.WatRate"),
        "liquid_m3d": get(os, f"{total}.LiqRate"),
        "solver_status": get(os, f"{status}.Status"),
        "solver_status_text": get(os, f"{status}.StatusText"),
        "solver_iterations": get(os, f"{status}.NumIteration"),
        "optimiser_iterations": get(os, f"{status}.OptNumIteration"),
        "objective_value": get(os, f"{status}.OptBestGuess"),
        "wells": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy", choices=["technological", "geological", "balanced"])
    parser.add_argument("--strategy-file", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--keep-open", action="store_true", help="Leave a GAP instance launched by this run open")
    args = parser.parse_args()
    case = json.loads(CASE_FILE.read_text(encoding="utf-8"))
    strategy = None
    output = OUTPUT
    if args.strategy:
        strategy_file = args.strategy_file or (ROOT / "data" / "optimization_strategy_templates_INC-002.json")
        strategy_data = json.loads(strategy_file.read_text(encoding="utf-8"))
        strategy = next(item for item in strategy_data["strategies"] if item["strategy_id"] == args.strategy)
        register_data = json.loads((ROOT / "data" / "opportunity_register_structured.json").read_text(encoding="utf-8"))
        opportunity_by_well = {item["well_id"]: item for item in register_data["opportunities"]}
        case["strategy"] = strategy
        output = args.output or ROOT / "data" / f"gap_optimization_result_{args.strategy}.json"
    cfg = type("PetExConfig", (), {
        "petex_folder": Path(r"C:\Program Files\Petroleum Experts\IPM 12.5"),
        "need_mbal_passport": 0,
        "need_prosper_passport": 0,
        "need_gap_passport": 1,
    })()
    launched = petex_apps.open_petex_apps(cfg)
    if launched is None:
        raise RuntimeError("PetEx installation was not found")

    report: dict[str, object] = {
        "case": case,
        "model": str(MODEL),
        "model_saved": False,
        "calculated_at": datetime.now().isoformat(timespec="seconds"),
    }
    try:
        with OpenServer() as os:
            mod = "GAP.MOD[{PROD}]"
            os.do_command(f'GAP.OPENFILE("{MODEL}")')
            os.do_command('GAP.SETUNITSYS("Norwegian S.I.")')

            os.do_command("GAP.SOLVENETWORK(0)")
            report["baseline"] = result(os)
            baseline_water = float(report["baseline"]["water_m3d"])

            os.set_value(f"{mod}.OptMethod", 0)
            os.set_value(f"{mod}.MAXQWAT", baseline_water)
            os.set_value(f"{mod}.MAXQWATBINDING", 1)

            policy = case["controls"]
            selected_wells = set(strategy["candidate_wells"]) if strategy else None
            configured_controls = []
            for well in report["baseline"]["wells"]:
                well_id = well["well_id"]
                current = well["control_actual"]
                well_type = str(well["well_type"] or "")
                if current is None or not ("ESP" in well_type or "PCP" in well_type):
                    continue
                tag = f"{mod}.WELL[{{{well_id}}}]"
                os.set_value(f"{tag}.MINPWF", case["constraints"]["minimum_fbhp_bar"])
                os.set_value(f"{tag}.MINPWFBINDING", 1)
                if selected_wells is not None and well_id not in selected_wells:
                    os.set_value(f"{tag}.AlqControl", "FIXEDVALUE")
                    continue
                current = float(current)
                strategy_delta = float(strategy["max_change_per_well"]) if strategy else None
                register_delta = float(opportunity_by_well[well_id]["maximum_change"]) if strategy else None
                if "ESP" in well_type:
                    delta = min(float(policy["esp_delta_hz"]), strategy_delta, register_delta) if strategy_delta else float(policy["esp_delta_hz"])
                    minimum = current
                    maximum = min(policy["esp_absolute_max_hz"], current + delta)
                else:
                    delta = min(float(policy["pcp_delta"]), strategy_delta, register_delta) if strategy_delta else float(policy["pcp_delta"])
                    direction = opportunity_by_well[well_id]["direction"] if strategy else "increase"
                    if direction == "decrease":
                        minimum = max(policy["pcp_absolute_min"], current - delta)
                        maximum = current
                    else:
                        minimum = current
                        maximum = min(policy["pcp_absolute_max"], current + delta)
                os.set_value(f"{tag}.AlqValueMin", minimum)
                os.set_value(f"{tag}.AlqValueMax", maximum)
                os.set_value(f"{tag}.AlqControl", "CALCULATED")
                configured_controls.append({
                    "well_id": well_id, "well_type": well_type,
                    "current": current, "minimum": minimum, "maximum": maximum,
                })
            report["configured_controls"] = configured_controls
            report["loaded_constraints"] = {
                "maximum_water_m3d": baseline_water,
                "minimum_fbhp_bar": case["constraints"]["minimum_fbhp_bar"],
            }

            incident_well = case["incident"]["well_id"]
            os.do_command(f"{mod}.WELL[{{{incident_well}}}].DISABLE()")
            os.do_command("GAP.SOLVENETWORK(0)")
            report["incident_state"] = result(os)

            started = time.perf_counter()
            os.do_command("GAP.SOLVENETWORK(1)")
            report["elapsed_s"] = round(time.perf_counter() - started, 3)
            report["optimised"] = result(os)

            # A second physical state is enough for the remainder of this MVP day:
            # the inputs are unchanged within each period, so repeating the same
            # expensive GAP solve every hour would add no information.
            os.do_command(f"{mod}.WELL[{{{incident_well}}}].ENABLE()")
            started = time.perf_counter()
            os.do_command("GAP.SOLVENETWORK(1)")
            report["restored_elapsed_s"] = round(time.perf_counter() - started, 3)
            report["restored_optimised"] = result(os)
            if launched and not args.keep_open:
                os.do_command("GAP.SHUTDOWN(0)")
    finally:
        petex_apps.close_petex_apps([] if args.keep_open else launched)

    base = report["baseline"]
    incident = report["incident_state"]
    optimum = report["optimised"]
    restored = report["restored_optimised"]
    incident_hours = case["incident"]["restored_hour"] - case["incident"]["start_hour"]
    restored_hours = case["incident"]["horizon_end_hour"] - case["incident"]["restored_hour"]
    plan_volume = float(base["oil_sm3d"]) * (incident_hours + restored_hours) / 24
    forecast_volume = (
        float(optimum["oil_sm3d"]) * incident_hours
        + float(restored["oil_sm3d"]) * restored_hours
    ) / 24
    water_tolerance = float(case["constraints"]["water_tolerance_m3d"])
    report["summary"] = {
        "incident_loss_sm3d": round(float(base["oil_sm3d"]) - float(incident["oil_sm3d"]), 6),
        "optimisation_gain_sm3d": round(float(optimum["oil_sm3d"]) - float(incident["oil_sm3d"]), 6),
        "remaining_loss_sm3d": round(float(base["oil_sm3d"]) - float(optimum["oil_sm3d"]), 6),
        "water_limit_met": float(optimum["water_m3d"]) <= float(report["loaded_constraints"]["maximum_water_m3d"]) + water_tolerance,
        "minimum_fbhp_bar": min(
            float(w["fbhp_bar"]) for w in optimum["wells"] if w["fbhp_bar"] is not None
        ),
        "horizon_plan_oil_sm3": round(plan_volume, 6),
        "horizon_forecast_oil_sm3": round(forecast_volume, 6),
        "horizon_balance_sm3": round(forecast_volume - plan_volume, 6),
        "target_met_by_horizon_end": forecast_volume >= plan_volume - 1e-6,
        "restored_optimised_oil_sm3d": restored["oil_sm3d"],
    }
    density = float(case["oil_density_t_m3"])
    report["summary"].update({
        "horizon_plan_oil_t": round(plan_volume * density, 6),
        "horizon_forecast_oil_t": round(forecast_volume * density, 6),
        "horizon_balance_t": round((forecast_volume - plan_volume) * density, 6),
    })
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(output), "elapsed_s": report["elapsed_s"], **report["summary"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
