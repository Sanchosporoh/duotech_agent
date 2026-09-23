import unittest
from pathlib import Path
from src.potential_register import table

ROOT=Path(__file__).resolve().parents[1]

class DiagnosticPresentationTests(unittest.TestCase):
    def test_register_has_potentials_not_exact_new_rates(self):
        frame=table(ROOT)
        self.assertIn("Оценка потенциала нефти, т/сут",frame.columns)
        self.assertNotIn("Новый дебит, т/сут",frame.columns)
        self.assertNotIn("Решение",frame.columns)

if __name__=="__main__": unittest.main()
