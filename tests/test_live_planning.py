import unittest
from src.live_planning import forecast_need, evaluate_horizon


class LivePlanningTests(unittest.TestCase):
    def test_conditional_balance_does_not_authorize_execution(self):
        plan={'need':{'ready':True,'required_extra_oil_tpd':20,'remaining_hours':12},'network':{'alternatives':[{'gain_oil_tpd':24}]}}
        result=evaluate_horizon(plan)['network']['alternatives'][0]
        self.assertEqual(result['conditional_horizon_balance_t'],2)
        self.assertTrue(result['conditional_target_met'])
        self.assertFalse(result['approved_for_execution'])
    def test_accumulated_loss_changes_required_compensation(self):
        context={'hour':1,'separator':[{'hour':0,'plan_oil_tpd':240,'separator_oil_tpd':216},{'hour':1,'plan_oil_tpd':240,'separator_oil_tpd':216}]}
        result=forecast_need(context)
        self.assertEqual(result['net_deficit_t'],2)
        self.assertAlmostEqual(result['required_extra_oil_tpd'],24+48/22)
        self.assertEqual(result['completed_deficit_t'],1)
        self.assertEqual(result['response_delay_deficit_t'],1)
        self.assertEqual(result['effect_start_hour'],2)

    def test_missing_fact_blocks_forecast(self):
        self.assertFalse(forecast_need({'hour':0,'separator':[{'hour':0,'plan_oil_tpd':100,'separator_oil_tpd':None}]})['ready'])

    def test_past_gap_is_estimated_as_range_with_worse_bound_in_need(self):
        rows=[{'hour':0,'plan_oil_tpd':240,'separator_oil_tpd':240},  # loss 0
              {'hour':1,'plan_oil_tpd':240,'separator_oil_tpd':None},
              # hour 2 is absent entirely
              {'hour':3,'plan_oil_tpd':240,'separator_oil_tpd':192}]  # loss 48
        result=forecast_need({'hour':3,'separator':rows})
        self.assertTrue(result['ready'])
        self.assertEqual(result['estimated_hours'],[1,2])
        # Hours 1-2 lie between losses 0 and 48 t/d: 0-4 t together.
        self.assertEqual(result['net_deficit_range_t'],[2.,6.])
        self.assertEqual(result['net_deficit_t'],6.)
        self.assertIn('01:00, 02:00',result['assumption'])

    def test_missing_current_hour_still_blocks_forecast(self):
        rows=[{'hour':0,'plan_oil_tpd':240,'separator_oil_tpd':240},{'hour':1,'plan_oil_tpd':240,'separator_oil_tpd':None}]
        self.assertFalse(forecast_need({'hour':1,'separator':rows})['ready'])

