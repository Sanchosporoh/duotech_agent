import unittest

from src.iteration_guard import IterationGuard


LIMITS = {
    "max_iterations": 3,
    "max_llm_calls": 2,
    "max_gap_runs": 3,
    "incident_timeout_seconds": 300,
    "minimum_improvement_t": 0.1,
    "max_no_progress_iterations": 2,
}


class IterationGuardTests(unittest.TestCase):
    def test_repeat_is_detected_despite_changed_explanation(self):
        guard = IterationGuard(LIMITS)
        first = {"candidate_wells": ["W2", "W1"], "max_change_per_well": 2, "explanation": "a"}
        repeat = {"candidate_wells": ["W1", "W2"], "max_change_per_well": 2, "explanation": "b"}
        self.assertIsNone(guard.register_strategy(first))
        self.assertEqual(guard.register_strategy(repeat), "repeated_strategy")

    def test_iteration_budget_stops_loop(self):
        guard = IterationGuard(LIMITS)
        guard.iterations = 3
        self.assertEqual(guard.before_iteration(), "max_iterations")

    def test_two_weak_results_stop_no_progress(self):
        guard = IterationGuard(LIMITS)
        self.assertIsNone(guard.register_result(-2.0))
        self.assertIsNone(guard.register_result(-1.98))
        self.assertEqual(guard.register_result(-1.97), "no_progress")


if __name__ == "__main__":
    unittest.main()
