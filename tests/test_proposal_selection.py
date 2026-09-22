import unittest
from src.proposal_selection import select


class SelectionTests(unittest.TestCase):
    def test_calculation_success_without_feasible_option_is_not_a_decision(self):
        context={'separator':[{'hour':6,'plan_oil_tpd':240,'separator_oil_tpd':200}]}
        plan={'need':{'ready':True,'remaining_hours':17,'net_deficit_t':1},
              'network':{'alternatives':[
                  {'status':'conditional_calculated','water_limit_met':False,'fbhp_limit_met':True},
                  {'status':'conditional_calculated','water_limit_met':True,'fbhp_limit_met':False}]}}
        self.assertFalse(select(context,plan)['ready'])

    def test_remaining_deficit_does_not_block_recommendation(self):
        context={'separator':[{'hour':6,'plan_oil_tpd':240,'separator_oil_tpd':200}]}
        def alternative(title,gain,allowed=True):
            return {'title':title,'status':'conditional_calculated','water_limit_met':allowed,'fbhp_limit_met':True,
                    'current':{'oil_sm3d':220,'water_m3d':20},
                    'optimised':{'oil_sm3d':220+gain/.908,'water_m3d':20,'wells':[]}}
        plan={'need':{'ready':True,'remaining_hours':12,'net_deficit_t':1},
              'network':{'alternatives':[alternative('Small',10),alternative('Best',20),alternative('Invalid',50,False)]}}
        result=select(context,plan)
        self.assertTrue(result['ready'])
        self.assertEqual(result['selected']['title'],'Best')
        self.assertAlmostEqual(result['selected']['expected_deficit_t'],11)
        self.assertFalse(result['selected']['approved_for_execution'])
