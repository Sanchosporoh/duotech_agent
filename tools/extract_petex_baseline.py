"""Calculate and extract a GAP baseline from a disposable working copy.

The source model in IM_2022_06 is never opened by this script. No GAP save command
is issued. PetEx is closed only when this script launched it itself.
"""

from __future__ import annotations

import csv
import json
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PASSPORT = ROOT / "petex_passport_ima"
sys.path.insert(0, str(PASSPORT))

import petex_apps  # noqa: E402
from open_server import OpenServer, OpenServerError  # noqa: E402


MODEL = ROOT / "runtime" / "petex_case" / "IM_2022_06" / "BEL_PROD.gap"
OUT_CSV = ROOT / "data" / "petex_baseline.csv"
OUT_JSON = ROOT / "data" / "petex_baseline_summary.json"
SYSTEM_CODES = {
    "PRODUCTION": "PROD",
    "WATERINJECTION": "WINJ",
    "GASINJECTION": "GINJ",
}


def read(_os: OpenServer, expression: str) -> str | None:
    try:
        return str(_os.get_value(expression)).strip()
    except (OpenServerError, ValueError):
        return None


def read_float(_os: OpenServer, expression: str) -> float | None:
    value = read(_os, expression)
    try:
        return float(value) if value not in (None, "") else None
    except ValueError:
        return None


def main() -> int:
    if not MODEL.exists():
        raise FileNotFoundError(f"Рабочая копия GAP не найдена: {MODEL}")

    cfg = type(
        "PetExConfig",
        (),
        {
            "petex_folder": Path(r"C:\Program Files\Petroleum Experts\IPM 12.5"),
            "need_mbal_passport": 0,
            "need_prosper_passport": 0,
            "need_gap_passport": 1,
        },
    )()
    launched = petex_apps.open_petex_apps(cfg)
    if launched is None:
        raise RuntimeError("Каталог PetEx не найден")

    rows: list[dict[str, object]] = []
    summary: dict[str, object] = {"model": str(MODEL), "source_is_working_copy": True}
    try:
        with OpenServer() as _os:
            print(f"Открываю рабочую копию: {MODEL.name}", flush=True)
            _os.do_command(f'GAP.OPENFILE("{MODEL}")')
            system_type = read(_os, "GAP.MOD.SysType")
            system_code = SYSTEM_CODES.get(system_type or "", system_type or "PROD")
            summary.update({"system_type": system_type, "system_code": system_code})

            print("Выполняю GAP.SOLVENETWORK(0)...", flush=True)
            _os.do_command("GAP.SOLVENETWORK(0)")
            summary["iterations"] = read_float(_os, "GAP.MOD.SolverStatusList[0].NumIteration")
            summary["well_count"] = int(read_float(_os, f"GAP.MOD[{{{system_code}}}].WELL.count") or 0)

            # Norwegian S.I. provides oil volume in metric surface units. We keep
            # the unit reported by PetEx instead of guessing that it is tonnes.
            _os.do_command('GAP.SETUNITSYS("Norwegian S.I.")')
            labels = _os.get_value_array(f"GAP.MOD[{{{system_code}}}].WELL[$].Label")
            for label in labels:
                base = f"GAP.MOD[{{{system_code}}}].WELL[{{{label}}}].SolverResults[0]"
                oil_expr = f"{base}.OilRate"
                row = {
                    "well_id": label,
                    "oil_rate": read_float(_os, oil_expr),
                    "oil_rate_unit": read(_os, oil_expr + ".Unitname"),
                    "liquid_rate": read_float(_os, f"{base}.LiqRate"),
                    "liquid_rate_unit": read(_os, f"{base}.LiqRate.Unitname"),
                    "watercut_pct": read_float(_os, f"{base}.WCT"),
                    "fbhp": read_float(_os, f"{base}.FBHP"),
                    "fbhp_unit": read(_os, f"{base}.FBHP.Unitname"),
                    "sog": read_float(_os, f"{base}.SOG"),
                    "sog_unit": read(_os, f"{base}.SOG.Unitname"),
                }
                rows.append(row)

            system_base = f"GAP.MOD[{{{system_code}}}].SystemTotal[0]"
            for key, variable in (
                ("total_oil_rate", "OilRate"),
                ("total_liquid_rate", "LiqRate"),
                ("total_mass_rate", "TotMassRate"),
            ):
                expr = f"{system_base}.{variable}"
                summary[key] = read_float(_os, expr)
                summary[key + "_unit"] = read(_os, expr + ".Unitname")
    finally:
        petex_apps.close_petex_apps(launched)

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    summary["wells_with_oil_rate"] = sum(row["oil_rate"] is not None for row in rows)
    oil_mass = [
        float(row["oil_rate"]) * float(row["sog"]) / 1000
        for row in rows
        if row["oil_rate"] is not None and row["sog"] is not None
    ]
    summary["calculated_oil_mass_tpd"] = round(sum(oil_mass), 6)
    summary["calculated_at"] = datetime.now().isoformat(timespec="seconds")
    summary["constraints"] = {
        "maximum_water_m3d": round(sum(
            float(row["liquid_rate"]) - float(row["oil_rate"])
            for row in rows
            if row["liquid_rate"] is not None and row["oil_rate"] is not None
        ), 6),
        "minimum_fbhp_bar": 80.0,
        "fbhp_violations": [
            row["well_id"] for row in rows
            if row["fbhp"] is not None and float(row["fbhp"]) < 80.0
        ],
    }
    OUT_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
