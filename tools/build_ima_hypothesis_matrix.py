"""Build separator responses for single-well shutdown hypotheses in GAP."""

from __future__ import annotations

import csv
import json
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "petex_passport_ima"))

import petex_apps  # noqa: E402
from open_server import OpenServer  # noqa: E402


MODEL = ROOT / "runtime" / "petex_case" / "IM_2022_06" / "BEL_PROD.gap"
OUTPUT = ROOT / "data" / "ima_shutdown_matrix.csv"
SUMMARY = ROOT / "data" / "ima_shutdown_matrix_summary.json"


def number(_os: OpenServer, expression: str) -> float:
    return float(_os.get_value(expression))


def main() -> int:
    cfg = type("C", (), {
        "petex_folder": Path(r"C:\Program Files\Petroleum Experts\IPM 12.5"),
        "need_mbal_passport": 0, "need_prosper_passport": 0, "need_gap_passport": 1,
    })()
    launched = petex_apps.open_petex_apps(cfg)
    if launched is None:
        raise RuntimeError("Не удалось запустить ИМА")
    rows: list[dict[str, object]] = []
    try:
        with OpenServer() as _os:
            _os.do_command(f'GAP.OPENFILE("{MODEL}")')
            _os.do_command('GAP.SETUNITSYS("Norwegian S.I.")')
            _os.do_command("GAP.SOLVENETWORK(0)")
            labels = _os.get_value_array("GAP.MOD[{PROD}].WELL[$].Label")
            total_expr = "GAP.MOD[{PROD}].SystemTotal[0].OilRate"
            water_expr = "GAP.MOD[{PROD}].SystemTotal[0].WatRate"
            baseline_oil = number(_os, total_expr)
            baseline_water = number(_os, water_expr)
            for index, well_id in enumerate(labels, 1):
                print(f"[{index}/{len(labels)}] Остановка {well_id}", flush=True)
                tag = f"GAP.MOD[{{PROD}}].WELL[{{{well_id}}}]"
                _os.do_command(f"{tag}.DISABLE()")
                try:
                    _os.do_command("GAP.SOLVENETWORK(0)")
                    oil = number(_os, total_expr)
                    water = number(_os, water_expr)
                    rows.append({
                        "hypothesis": f"Остановка {well_id}", "well_id": well_id,
                        "separator_oil_sm3d": round(oil, 6),
                        "predicted_oil_loss_sm3d": round(baseline_oil - oil, 6),
                        "separator_water_m3d": round(water, 6),
                        "water_change_m3d": round(water - baseline_water, 6),
                    })
                finally:
                    _os.do_command(f"{tag}.ENABLE()")
                    _os.do_command("GAP.SOLVENETWORK(0)")
    finally:
        petex_apps.close_petex_apps(launched)

    with OUTPUT.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    SUMMARY.write_text(json.dumps({
        "calculated_at": datetime.now().isoformat(timespec="seconds"),
        "model": str(MODEL), "baseline_oil_sm3d": baseline_oil,
        "baseline_water_m3d": baseline_water, "hypotheses": len(rows),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Матрица записана: {OUTPUT}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
