"""Читает текстовые отчёты PetEx. Исходные модели не изменяет."""
from __future__ import annotations

import csv
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "IM_2022_06"
OUTPUT = ROOT / "data"

WELL_FIELDS = {
    "Fluid": "fluid",
    "PVT Method": "pvt_method",
    "Well Type": "well_type",
    "Artificial Lift": "artificial_lift",
    "Lift Type": "lift_type",
    "Completion": "completion",
    "Inflow Type": "inflow_type",
    "Location": "location",
    "Well": "petex_well_name",
    "Surface Equipment Correlation": "surface_correlation",
    "Vertical Lift Correlation": "vertical_lift_correlation",
    "Rate Type": "rate_type",
    "First Node": "first_node",
    "Last Node": "last_node",
}


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def parse_tpd(path: Path) -> dict:
    text = path.read_text(encoding="latin-1", errors="replace")
    values = {}
    for line in text.splitlines():
        match = re.match(r"^#\s+([^:]+?)\s*:\s*(.*?)\s*$", line)
        if match:
            label, value = match.groups()
            values.setdefault(label.strip(), value.strip())

    stem = path.stem
    files = {suffix: SOURCE / f"{stem}.{suffix}" for suffix in ("Out", "out", "vlp")}
    out_file = files["Out"] if files["Out"].exists() else files["out"]
    row = {
        "well_id": stem,
        "tpd_file": path.name,
        "tpd_size_bytes": path.stat().st_size,
        "out_file": out_file.name if out_file.exists() else "",
        "out_size_bytes": out_file.stat().st_size if out_file.exists() else "",
        "vlp_file": files["vlp"].name if files["vlp"].exists() else "",
        "vlp_size_bytes": files["vlp"].stat().st_size if files["vlp"].exists() else "",
    }
    for source_name, target_name in WELL_FIELDS.items():
        row[target_name] = values.get(source_name, "")
    return row


def build_inventory() -> list[dict]:
    kind_by_suffix = {
        ".gap": "GAP network model",
        ".gaplgs": "GAP calculation log",
        ".gapprs": "GAP auxiliary binary",
        ".mbi": "MBAL model",
        ".out": "PROSPER model",
        ".tpd": "PROSPER text report",
        ".vlp": "PROSPER VLP table",
    }
    rows = []
    for path in sorted(SOURCE.iterdir(), key=lambda item: item.name.lower()):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        rows.append(
            {
                "file_name": path.name,
                "extension": suffix,
                "file_kind": kind_by_suffix.get(suffix, "other"),
                "size_bytes": path.stat().st_size,
                "read_method": "text" if suffix in {".tpd", ".gaplgs"} else "PetEx OpenServer",
                "source_policy": "read_only",
            }
        )
    return rows


def parse_gap_logs() -> list[dict]:
    rows = []
    patterns = {
        "iterations": r"solution reached in (\d+) iterations",
        "max_pressure_drop_difference_bar": r"Max\. Pressure Drop Difference ([\d.]+) bar",
        "max_mass_balance_difference_tpd": r"Max\. Mass Balance Difference ([\d.]+) tonne/day",
        "calculation_time_seconds": r"Time taken\s*:\s*([\d.]+) secs",
    }
    for path in sorted(SOURCE.glob("*.gaplgs")):
        text = path.read_text(encoding="latin-1", errors="replace")
        row = {"log_file": path.name, "solution_reached": "Solver solution reached" in text}
        for field, pattern in patterns.items():
            match = re.search(pattern, text)
            row[field] = match.group(1) if match else ""
        constraints = re.findall(r"(?:Min|Max) .*? constraint\s+limiting\s*:\s*[^\r\n]+", text)
        row["active_constraints"] = " | ".join(constraints)
        rows.append(row)
    return rows


def main() -> None:
    OUTPUT.mkdir(exist_ok=True)
    wells = [parse_tpd(path) for path in sorted(SOURCE.glob("*.tpd"))]
    well_fields = [
        "well_id", "petex_well_name", "location", "well_type", "fluid", "pvt_method",
        "artificial_lift", "lift_type", "completion", "inflow_type", "rate_type",
        "surface_correlation", "vertical_lift_correlation", "first_node", "last_node",
        "tpd_file", "tpd_size_bytes", "out_file", "out_size_bytes", "vlp_file", "vlp_size_bytes",
    ]
    write_csv(OUTPUT / "petex_well_reference.csv", wells, well_fields)
    write_csv(
        OUTPUT / "petex_source_inventory.csv",
        build_inventory(),
        ["file_name", "extension", "file_kind", "size_bytes", "read_method", "source_policy"],
    )
    write_csv(
        OUTPUT / "petex_gap_calculation_logs.csv",
        parse_gap_logs(),
        ["log_file", "solution_reached", "iterations", "max_pressure_drop_difference_bar", "max_mass_balance_difference_tpd", "calculation_time_seconds", "active_constraints"],
    )
    print(f"Извлечено скважин: {len(wells)}")


if __name__ == "__main__":
    main()
