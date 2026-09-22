"""Обработчик доработки: комментарий инженера -> Codex -> GAP -> версия."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import incident_lifecycle
from src.optimization_strategies import generate, save


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--incident", default="INC-002")
    args = parser.parse_args()
    lifecycle_path = ROOT / "data" / "incident_lifecycle.json"
    incident = incident_lifecycle.load(lifecycle_path)["incidents"][args.incident]
    current = incident["versions"][-1]
    if current["stage"] != "awaiting_revision_calculation":
        raise RuntimeError("Текущая версия не ожидает доработки")

    version = int(current["version"])
    folder = ROOT / "data" / "revisions" / args.incident / f"v{version}"
    strategies = generate(ROOT, args.incident, current["human_comment"], version)
    strategies_file = save(ROOT, strategies, folder / "strategies.json")

    result_files = {}
    summaries = []
    for strategy in ("technological", "geological", "balanced"):
        output = folder / f"gap_{strategy}.json"
        command = [sys.executable, str(ROOT / "tools" / "run_gap_optimization_case.py"),
                   "--strategy", strategy, "--strategy-file", str(strategies_file),
                   "--output", str(output)]
        completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True,
                                   encoding="utf-8", errors="replace", check=False)
        if completed.returncode != 0:
            raise RuntimeError(f"GAP {strategy}: {(completed.stderr or completed.stdout)[-2000:]}")
        result_files[strategy] = output
        payload = json.loads(output.read_text(encoding="utf-8"))
        summary = payload["summary"]
        summaries.append((strategy, summary))

    feasible = [(name, s) for name, s in summaries
                if s["water_limit_met"] and s["minimum_fbhp_bar"] >= 79.99]
    pool = feasible or summaries
    selected, summary = max(pool, key=lambda item: item[1]["horizon_balance_t"])
    result_text = (f"Баланс к 24:00 {summary['horizon_balance_t']:+.2f} т; "
                   f"вода {'в норме' if summary['water_limit_met'] else 'нарушена'}; "
                   f"мин. Pзаб {summary['minimum_fbhp_bar']:.2f} бар")
    incident_lifecycle.complete_revision(lifecycle_path, args.incident, strategies_file,
                                         result_files, selected, result_text)
    print(json.dumps({"incident": args.incident, "version": version,
                      "selected_strategy": selected, "result": result_text},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
