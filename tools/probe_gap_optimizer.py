"""Audit and run the optimiser of the disposable GAP working copy.

The script never saves the model. It records the current controls, constraints,
solver result, and one ``Optimise and Honour Constraints`` result.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "petex_passport_ima"))

import petex_apps  # noqa: E402
from open_server import OpenServer, OpenServerError  # noqa: E402


MODEL = ROOT / "runtime" / "petex_case" / "IM_2022_06" / "BEL_PROD.gap"
OUTPUT = ROOT / "data" / "gap_optimizer_probe.json"


def value(os: OpenServer, expression: str) -> object | None:
    try:
        raw = os.get_value(expression)
        if raw == "":
            return None
        try:
            return float(raw)
        except (TypeError, ValueError):
            return str(raw)
    except (OpenServerError, ValueError, TypeError):
        return None


def array(os: OpenServer, expression: str) -> list[str]:
    try:
        return [str(item) for item in os.get_value_array(expression) if str(item)]
    except (OpenServerError, ValueError, TypeError):
        return []


def snapshot(os: OpenServer) -> dict[str, object]:
    system = "GAP.MOD[{PROD}]"
    totals = f"{system}.SystemTotal[0]"
    wells = []
    for label in array(os, f"{system}.WELL[$].Label"):
        tag = f"{system}.WELL[{{{label}}}]"
        result = f"{tag}.SolverResults[0]"
        wells.append({
            "well_id": label,
            "well_type": value(os, f"{tag}.TypeWell"),
            "enabled": value(os, f"{tag}.MASKFLAG"),
            "alq_control": value(os, f"{tag}.AlqControl"),
            "alq_actual": value(os, f"{tag}.AlqValue"),
            "alq_optimised": value(os, f"{tag}.AlqOptimised"),
            "alq_min": value(os, f"{tag}.AlqValueMin"),
            "alq_max": value(os, f"{tag}.AlqValueMax"),
            "dp_control": value(os, f"{tag}.DPControl"),
            "min_fbhp": value(os, f"{tag}.MINPWF"),
            "min_fbhp_binding": value(os, f"{tag}.MINPWFBINDING"),
            "oil_sm3d": value(os, f"{result}.OilRate"),
            "water_m3d": value(os, f"{result}.WatRate"),
            "fbhp_bar": value(os, f"{result}.FBHP"),
        })

    pipes = []
    for label in array(os, f"{system}.PIPE[$].Label"):
        tag = f"{system}.PIPE[{{{label}}}]"
        result = f"{tag}.SolverResults[0]"
        pipes.append({
            "pipe_id": label,
            "max_pressure": value(os, f"{tag}.MAXPRESSURE"),
            "max_pressure_binding": value(os, f"{tag}.MAXPRESSUREBINDING"),
            "calculated_max_pressure": value(os, f"{result}.MaxPres"),
        })

    violations = []
    count = int(value(os, f"{system}.SolverStatusList[0].ViolatedConstraint.count") or 0)
    for index in range(count):
        tag = f"{system}.SolverStatusList[0].ViolatedConstraint[{index}]"
        violations.append({
            "equipment": value(os, f"{tag}.EquipLabel"),
            "description": value(os, f"{tag}.CnstDesc"),
            "calculated": value(os, f"{tag}.CalcValue"),
            "constraint": value(os, f"{tag}.CnstValue"),
            "binding": value(os, f"{tag}.Binding"),
            "message": value(os, f"{tag}.msg"),
        })

    return {
        "oil_sm3d": value(os, f"{totals}.OilRate"),
        "water_m3d": value(os, f"{totals}.WatRate"),
        "liquid_m3d": value(os, f"{totals}.LiqRate"),
        "solver_status": value(os, f"{system}.SolverStatus"),
        "solver_status_text": value(os, f"{system}.SolverStatusText"),
        "solver_iterations": value(os, f"{system}.SolverStatusList[0].NumIteration"),
        "optimiser_iterations": value(os, f"{system}.SolverStatusList[0].OptNumIteration"),
        "optimiser_best_guess": value(os, f"{system}.SolverStatusList[0].OptBestGuess"),
        "system_max_water": value(os, f"{system}.MAXQWAT"),
        "system_max_water_binding": value(os, f"{system}.MAXQWATBINDING"),
        "violations": violations,
        "wells": wells,
        "pipes": pipes,
    }


def main() -> int:
    if not MODEL.exists():
        raise FileNotFoundError(MODEL)

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
        "calculated_at": datetime.now().isoformat(timespec="seconds"),
        "model": str(MODEL),
        "model_saved": False,
    }
    try:
        with OpenServer() as os:
            os.do_command(f'GAP.OPENFILE("{MODEL}")')
            os.do_command('GAP.SETUNITSYS("Norwegian S.I.")')
            report["settings"] = {
                "objective": value(os, "GAP.MOD[{PROD}].OptMethod"),
                "solver_optimise_mode": value(os, "GAP.MOD[{PROD}].SolverOptimiseMode"),
                "prediction_mode": value(os, "GAP.MOD[{PROD}].PredMode"),
            }

            started = time.perf_counter()
            os.do_command("GAP.SOLVENETWORK(0)")
            report["base_elapsed_s"] = round(time.perf_counter() - started, 3)
            report["base"] = snapshot(os)

            started = time.perf_counter()
            os.do_command("GAP.SOLVENETWORK(1)")
            report["optimised_elapsed_s"] = round(time.perf_counter() - started, 3)
            report["optimised"] = snapshot(os)
            if launched:
                os.do_command("GAP.SHUTDOWN(0)")
    finally:
        petex_apps.close_petex_apps(launched)

    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "output": str(OUTPUT),
        "base_elapsed_s": report.get("base_elapsed_s"),
        "optimised_elapsed_s": report.get("optimised_elapsed_s"),
        "base_oil_sm3d": report.get("base", {}).get("oil_sm3d"),
        "optimised_oil_sm3d": report.get("optimised", {}).get("oil_sm3d"),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
