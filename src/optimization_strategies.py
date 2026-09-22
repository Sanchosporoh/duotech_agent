"""Use Codex to turn engineering preferences into GAP strategy envelopes."""

from __future__ import annotations

import json
from pathlib import Path

from .codex_cli import ask_codex


SCHEMA = {
    "type": "object",
    "properties": {
        "assessment": {"type": "string"},
        "strategies": {
            "type": "array", "minItems": 3, "maxItems": 3,
            "items": {
                "type": "object",
                "properties": {
                    "strategy_id": {"type": "string", "enum": ["technological", "geological", "balanced"]},
                    "title": {"type": "string"},
                    "candidate_wells": {"type": "array", "minItems": 1, "items": {"type": "string"}},
                    "max_change_per_well": {"type": "number", "exclusiveMinimum": 0},
                    "engineering_rationale": {"type": "string"},
                    "tradeoff": {"type": "string"}
                },
                "required": ["strategy_id", "title", "candidate_wells", "max_change_per_well", "engineering_rationale", "tradeoff"],
                "additionalProperties": False
            }
        }
    },
    "required": ["assessment", "strategies"],
    "additionalProperties": False
}


def generate(project: Path, incident_id: str = "INC-002", human_comment: str = "", revision: int = 1) -> dict:
    register = json.loads((project / "data" / "opportunity_register_structured.json").read_text(encoding="utf-8"))
    payload = {
        "incident_id": incident_id,
        "incident": "W_BEL_22_TLBB остановлена в 15:00, ожидаемое восстановление в 19:00",
        "goal": "устранить накопленный недобор к 24:00",
        "opportunity_register": register["opportunities"],
        "physical_constraints_in_ima": ["вода объекта не выше базового уровня", "Pзаб каждой работающей скважины не ниже 80 бар"],
        "revision": revision,
        "engineer_comment": human_comment,
    }
    prompt = """Ты помощник инженера по интегрированному моделированию. Сформируй ровно три постановки для проверки в ИМА: technological — минимальное число изменяемых скважин и допустимы большие изменения; geological — распределить воздействие между большим числом скважин малыми шагами; balanced — компромисс. Комментарий инженера обязателен к учёту как новое ограничение версии. Выбирай скважины только из opportunity_register. max_change_per_well не может превышать maximum_change ни одного выбранного мероприятия. Не рассчитывай точные частоты, дебиты, давления и эффект интерференции: это сделает GAP. Не объявляй цель достигнутой до расчёта GAP. Верни только JSON по схеме. Вход:\n""" + json.dumps(payload, ensure_ascii=False)
    answer = ask_codex(prompt, SCHEMA, project)
    allowed = {item["well_id"]: item for item in register["opportunities"]}
    ids = {item["strategy_id"] for item in answer["strategies"]}
    if ids != {"technological", "geological", "balanced"}:
        raise ValueError("Codex did not return the three required strategy types")
    for strategy in answer["strategies"]:
        unknown = set(strategy["candidate_wells"]) - set(allowed)
        if unknown:
            raise ValueError(f"Unknown wells in strategy: {sorted(unknown)}")
        maximum = min(float(allowed[w]["maximum_change"]) for w in strategy["candidate_wells"])
        if float(strategy["max_change_per_well"]) > maximum:
            raise ValueError(f"Strategy {strategy['strategy_id']} exceeds register envelope")
    answer.update({"incident_id": incident_id, "revision": revision,
                   "engineer_comment": human_comment, "generator": "Codex CLI"})
    return answer


def save(project: Path, result: dict, path: Path | None = None) -> Path:
    path = path or project / "data" / f"codex_optimization_strategies_{result['incident_id']}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
