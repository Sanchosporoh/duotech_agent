"""Простые предохранители итерационного цикла LLM -> GAP -> проверка."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import time


@dataclass
class IterationGuard:
    limits: dict
    started_at: float = field(default_factory=time.monotonic)
    iterations: int = 0
    llm_calls: int = 0
    gap_runs: int = 0
    no_progress: int = 0
    best_balance_t: float | None = None
    fingerprints: set[str] = field(default_factory=set)

    def _expired(self) -> bool:
        return time.monotonic() - self.started_at >= self.limits["incident_timeout_seconds"]

    def before_iteration(self) -> str | None:
        if self._expired():
            return "incident_timeout"
        if self.iterations >= self.limits["max_iterations"]:
            return "max_iterations"
        if self.llm_calls >= self.limits["max_llm_calls"]:
            return "max_llm_calls"
        if self.gap_runs >= self.limits["max_gap_runs"]:
            return "max_gap_runs"
        return None

    def register_strategy(self, strategy: dict) -> str | None:
        """Сравнивает только существенные параметры, а не текст пояснения LLM."""
        material = {
            "candidate_wells": sorted(strategy.get("candidate_wells", [])),
            "max_change_per_well": strategy.get("max_change_per_well"),
        }
        fingerprint = hashlib.sha256(
            json.dumps(material, sort_keys=True).encode("utf-8")
        ).hexdigest()
        if fingerprint in self.fingerprints:
            return "repeated_strategy"
        self.fingerprints.add(fingerprint)
        return None

    def register_result(self, balance_t: float) -> str | None:
        improvement = None if self.best_balance_t is None else balance_t - self.best_balance_t
        if self.best_balance_t is None or balance_t > self.best_balance_t:
            self.best_balance_t = balance_t
        if improvement is not None and improvement < self.limits["minimum_improvement_t"]:
            self.no_progress += 1
        else:
            self.no_progress = 0
        if self.no_progress >= self.limits["max_no_progress_iterations"]:
            return "no_progress"
        return None

