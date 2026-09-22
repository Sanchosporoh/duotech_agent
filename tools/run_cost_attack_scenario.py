"""Воспроизводит зацикливание без реальных вызовов Codex и GAP."""

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.iteration_guard import IterationGuard


def run() -> dict:
    limits = json.loads((ROOT / "config" / "agent_budget.json").read_text(encoding="utf-8"))
    guard = IterationGuard(limits)
    events = []
    stop_reason = None

    # Синтетический "атакующий" генератор каждый раз меняет пояснение,
    # но фактически предлагает один и тот же набор скважин и тот же диапазон.
    for attempt in range(1, 1000):
        stop_reason = guard.before_iteration()
        if stop_reason:
            break
        guard.iterations += 1
        guard.llm_calls += 1
        strategy = {
            "candidate_wells": ["W_BEL_12_TLBB", "W_BEL_13_TLBB"],
            "max_change_per_well": 2.0,
            "explanation": f"Новая формулировка номер {attempt}",
        }
        stop_reason = guard.register_strategy(strategy)
        if stop_reason:
            events.append({"iteration": attempt, "stage": "strategy_validation", "result": stop_reason})
            break

        guard.gap_runs += 1
        balance_t = -2.40  # цель заведомо недостижима данным набором
        events.append({"iteration": attempt, "stage": "gap_check", "balance_t": balance_t})
        stop_reason = guard.register_result(balance_t)
        if stop_reason:
            break

    result = {
        "scenario": "cost_attack_repeated_strategy",
        "target": "balance_t >= 0",
        "status": "stopped_safely",
        "stop_reason": stop_reason,
        "counters": {
            "iterations": guard.iterations,
            "llm_calls": guard.llm_calls,
            "gap_runs": guard.gap_runs,
        },
        "limits": limits,
        "events": events,
        "explanation": "LLM маскировала повтор изменением текста, но существенные параметры стратегии не изменились.",
    }
    output = ROOT / "data" / "cost_attack_scenario_result.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
