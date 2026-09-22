import unittest
from src.restoration_forecast import horizon


class RestorationTests(unittest.TestCase):
    def setUp(self):
        self.measure={'phases':[{'name':'Выезд','hours':1,'well_state':'degraded'},
                                {'name':'Промывка','hours':2,'well_state':'stopped'},
                                {'name':'Контроль','hours':1,'well_state':'stopped'}]}

    def test_four_hours_before_recovery(self):
        result=horizon(self.measure,6,{'degraded':240,'stopped':216,'restored':288},240,1)
        self.assertAlmostEqual(result['expected_production_t'],61)
        self.assertAlmostEqual(result['expected_horizon_balance_t'],0)
        self.assertFalse(result['approved_for_execution'])
        self.assertEqual(result['timeline'][-1]['forecast_hours'],2)

    def test_no_recovery_beyond_horizon(self):
        result=horizon(self.measure,2,{'degraded':240,'stopped':216,'restored':1000},240,0)
        self.assertAlmostEqual(result['expected_production_t'],19)
        self.assertFalse(result['expected_target_met'])
        self.assertEqual(len(result['timeline']),2)
