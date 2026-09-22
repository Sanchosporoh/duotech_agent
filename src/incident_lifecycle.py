"""Хранение версий решения и переходов HITL для каждого инцидента."""

from __future__ import annotations

from datetime import datetime
from contextlib import contextmanager
import json
from pathlib import Path
import time
from src.live_reasoning import save as atomic_save
from src.cycle_lock import acquire


def _empty() -> dict:
    return {"incidents": {}}


def load(path: Path) -> dict:
    if not path.exists():
        return _empty()
    return json.loads(path.read_text(encoding="utf-8"))


def save(path: Path, data: dict) -> None:
    atomic_save(path, data)


def _project_root(path: Path) -> Path:
    """Use the real project root, while keeping standalone tests self-contained."""
    if path.parent.name == "live" and path.parent.parent.name == "data":
        return path.parents[2]
    return path.parent


@contextmanager
def _locked(path: Path):
    # A Streamlit rerun can overlap the preceding rerun for a fraction of a
    # second. Wait for that small write instead of exposing a technical error.
    for attempt in range(20):
        guard = acquire(_project_root(path), "lifecycle.lock")
        locked = guard.__enter__()
        if locked:
            try:
                yield
            finally:
                guard.__exit__(None, None, None)
            return
        guard.__exit__(None, None, None)
        time.sleep(0.05 * (attempt + 1))
    raise RuntimeError("Реестр инцидентов занят другим процессом более 10 секунд")


def ensure_incident(path: Path, incident_id: str, working_hypothesis: str) -> dict:
    with _locked(path):
        data = load(path)
        incident = data["incidents"].get(incident_id)
        if incident is not None:
            return incident
        incident = {
            "incident_id": incident_id,
            "stage": "awaiting_human_decision",
            "working_hypothesis": working_hypothesis,
            "versions": [{
                "version": 1,
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "reason": "Первичная постановка по результатам ранжирования гипотез",
                "human_comment": "",
                "strategy": None,
                "gap_result": "Результаты исходного расчёта готовы",
                "decision": "Ожидает решения",
                "stage": "awaiting_human_decision",
            }],
        }
        data["incidents"][incident_id] = incident
        save(path, data)
        return incident


def record_decision(path: Path, incident_id: str, decision: str, comment: str,
                    strategy: str | None, gap_result: str) -> dict:
    with _locked(path):
        data = load(path)
        incident = data["incidents"][incident_id]
        current = incident["versions"][-1]
        current.update({"strategy": strategy, "gap_result": gap_result,
                        "decision": decision, "decided_at": datetime.now().isoformat(timespec="seconds")})

        if decision == "На доработке":
            next_version = current["version"] + 1
            incident["versions"].append({
                "version": next_version,
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "reason": "Комментарий инженера изменил постановку задачи",
                "human_comment": comment,
                "strategy": None,
                "gap_result": "Не рассчитан",
                "decision": "Требуется доработка",
                "stage": "awaiting_revision_calculation",
            })
            incident["stage"] = "awaiting_revision_calculation"
        elif decision == "Утверждено":
            incident["stage"] = "approved_for_execution"
        else:
            incident["stage"] = "closed_rejected"
        save(path, data)
        return incident


def version_rows(incident: dict) -> list[dict]:
    return [{
        "Версия": row["version"],
        "Причина версии": row["reason"],
        "Комментарий инженера": row.get("human_comment", ""),
        "Стратегия": row.get("strategy") or "—",
        "Результат GAP": row.get("gap_result", "—"),
        "Решение": row.get("decision", "—"),
    } for row in incident["versions"]]


def complete_revision(path: Path, incident_id: str, strategies_file: Path,
                      result_files: dict[str, Path], selected_strategy: str,
                      gap_result: str) -> dict:
    with _locked(path):
        data = load(path)
        incident = data["incidents"][incident_id]
        current = incident["versions"][-1]
        current.update({
            "strategies_file": str(strategies_file),
            "result_files": {key: str(value) for key, value in result_files.items()},
            "strategy": selected_strategy,
            "gap_result": gap_result,
            "decision": "Ожидает решения",
            "stage": "awaiting_human_decision",
            "calculated_at": datetime.now().isoformat(timespec="seconds"),
        })
        incident["stage"] = "awaiting_human_decision"
        save(path, data)
        return incident
