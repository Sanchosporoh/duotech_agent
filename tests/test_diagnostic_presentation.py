import unittest
from pathlib import Path
from src.incident_view import ranked_hypotheses
from src.potential_register import table

ROOT=Path(__file__).resolve().parents[1]

class DiagnosticPresentationTests(unittest.TestCase):
    def test_first_incident_does_not_claim_ima_calculation_or_probability(self):
        frame=ranked_hypotheses(ROOT,"INC-001")
        self.assertNotIn("score",frame.columns)
        self.assertTrue(frame.predicted_loss_tpd.isna().all())
        self.assertTrue(frame.mismatch_tpd.isna().all())

    def test_register_has_potentials_not_exact_new_rates(self):
        frame=table(ROOT)
        self.assertIn("Оценка потенциала нефти, т/сут",frame.columns)
        self.assertNotIn("Новый дебит, т/сут",frame.columns)
        self.assertNotIn("Решение",frame.columns)

if __name__=="__main__": unittest.main()
