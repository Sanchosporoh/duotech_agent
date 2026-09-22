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
