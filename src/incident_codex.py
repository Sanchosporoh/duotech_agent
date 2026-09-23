"""Codex CLI as a hypothesis generator; calculations remain outside the LLM."""
from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
from .codex_cli import ask_codex
from .live_reasoning import SCHEMA


def generate(project: Path, incident_id: str) -> dict:
    matrix = pd.read_csv(project / "data" / "ima_shutdown_matrix.csv")
    matrix["loss_tpd"] = (matrix["predicted_oil_loss_sm3d"] * .908).round(2)
    incident = {
        "INC-001": {"hour": 6, "separator_loss_tpd": 15.33,
                    "signals": "частота W_BEL_27 неизменна; ток и вибрация растут; давление датчика снижается"},
        "INC-002": {"hour": 15, "separator_loss_tpd": 29.61,
                    "signals": "частота W_BEL_22 стала 0 Гц; остальные скважинные сигналы редкие"},
    }[incident_id]
    payload = {
        "incident_id": incident_id, **incident,
        "available_wells": matrix.well_id.tolist(),
        "ima_shutdown_scenarios": matrix[["well_id", "loss_tpd"]].to_dict("records"),
        "limitations": ["нет почасовых замеров дебита по скважинам", "есть почасовой общий замер сепаратора"]
    }
    prompt = """Ты помощник инженера по интегрированному моделированию. Сформируй 4–6 конкурирующих инженерных гипотез причины снижения добычи. Не объявляй гипотезу доказанной. Не выдумывай измерения. Обязательно включи альтернативы: оборудование/энергоснабжение, приток или давление, система сбора, качество измерения — где они физически уместны. Привязывай скважины только к списку available_wells. Для каждой гипотезы дай конкретную проверку и явно укажи недостающие данные. Значения loss_tpd — уже рассчитанные сценарии ИМА, не пересчитывай и не заменяй их своими числами. Не запускай команды и не меняй файлы. Верни только JSON по схеме. Вход:\n""" + json.dumps(payload, ensure_ascii=False)
    result = ask_codex(prompt, SCHEMA, project)
    result["incident_id"] = incident_id
    result["generator"] = "Codex CLI"
    return result

def cache_path(project: Path, incident_id: str) -> Path:
    return project / "data" / f"codex_hypotheses_{incident_id}.json"

def save(project: Path, incident_id: str, result: dict) -> Path:
    path = cache_path(project, incident_id)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
