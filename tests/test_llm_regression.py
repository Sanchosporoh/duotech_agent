import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import llm_regression


class LlmRegressionTest(unittest.TestCase):
    def test_rules_reject_wrong_first_cause_and_wells_outside_register(self):
        hyp={'task':'гипотезы','valid':True,'unknown_wells':[],'key_well_first':True}
        self.assertTrue(llm_regression.passed(hyp))
        self.assertFalse(llm_regression.passed(dict(hyp,key_well_first=False)))
        self.assertFalse(llm_regression.passed({'task':'наборы','valid':True,'outside_register':['W_BEL_22_TLBB']}))
        self.assertFalse(llm_regression.passed({'task':'наборы','valid':True,'error':'timeout'}))
        self.assertFalse(llm_regression.passed(None))


if __name__=='__main__':
    unittest.main()
