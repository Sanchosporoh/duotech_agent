"""Visible constraints, well trust (model KPI × data KPI) and compulsory constraint correction."""
import json
import os
import tempfile
import unittest
from unittest.mock import patch
import pandas as pd
from src import cycle_service, live_planning, well_trust
from tests.support import FIRST, make_project


class TrustTests(unittest.TestCase):
    def test_trust_combines_model_kpi_and_data_age(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root=make_project(directory)
            path=root/'config/well_trust.json'
            policy=json.loads(path.read_text(encoding='utf-8'));policy['wells']={'B':0.4}
            path.write_text(json.dumps(policy),encoding='utf-8')
            telemetry=pd.DataFrame([{'hour':6,'well_id':'A'},{'hour':6,'well_id':'B'},{'hour':1,'well_id':'C'},{'hour':0,'well_id':'D'}])
            trust=well_trust.compute(root,telemetry,6)
            self.assertEqual((trust['A']['trust'],trust['A']['level']),(0.8,'high'))
            self.assertEqual(trust['B']['level'],'low')          # low model KPI
            self.assertEqual((trust['C']['data_kpi'],trust['C']['level']),(0.5,'low'))   # 5 h old: 0.8 × 0.5
            self.assertEqual(well_trust.compute(root,telemetry,7)['D']['data_kpi'],0.)   # 7 h old

    def test_low_trust_well_is_not_offered_for_regulation(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory, patch.dict(os.environ,{'AGENT_TOOL_BACKEND':'stub'}):
            root=make_project(directory)
            path=root/'config/well_trust.json'
            policy=json.loads(path.read_text(encoding='utf-8'));policy['wells']={'W_BEL_13_TLBB':0.3}
            path.write_text(json.dumps(policy),encoding='utf-8')
            for _ in range(7):run=cycle_service.tick(root)
            separator,telemetry,_=cycle_service.load_measurements(root)
            from src import autonomous_cycle, incident_view
            state=autonomous_cycle.read_states(root,separator,telemetry,6,incident_view.opened_incidents(separator,6))[FIRST]
            excluded={e['well_id']:e['reason'] for e in state['plan']['input']['excluded']}
            self.assertIn('Низкое доверие',excluded['W_BEL_13_TLBB'])
            for alternative in state['plan']['proposal']['alternatives']:
                self.assertNotIn('W_BEL_13_TLBB',alternative['selected_wells'])


class ConstraintTests(unittest.TestCase):
    def test_violator_is_found_only_when_some_set_lacks_it(self):
        plan={'network':{'alternatives':[{'current':{'wells':[{'well_id':'V','fbhp_bar':79.5,'oil_sm3d':3},{'well_id':'S','fbhp_bar':70,'oil_sm3d':0}]}}]},
              'proposal':{'alternatives':[{'selected_wells':['A']},{'selected_wells':['A','V']}]}}
        found=live_planning.violators(plan,[{'well_id':'V'},{'well_id':'A'},{'well_id':'S'}],{'minimum_fbhp_bar':80.})
        self.assertEqual([f['well_id'] for f in found],['V'])   # S is stopped (no oil)
        plan['proposal']['alternatives'][0]['selected_wells'].append('V')
        self.assertEqual(live_planning.violators(plan,[{'well_id':'V'}],{'minimum_fbhp_bar':80.}),[])

    def test_gap_request_uses_configured_limits(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory, patch.dict(os.environ,{'AGENT_TOOL_BACKEND':'stub'}):
            root=make_project(directory)
            path=root/'config/network_constraints.json'
            limits=json.loads(path.read_text(encoding='utf-8'));limits.update(minimum_fbhp_bar=75.,water_margin_m3d=2.)
            path.write_text(json.dumps(limits),encoding='utf-8')
            for _ in range(7):cycle_service.tick(root)
            request=json.loads(next((root/'data/live/network').rglob('request.json')).read_text(encoding='utf-8'))
            separator=pd.read_csv(root/'data/live/separator.csv')
            self.assertEqual(request['minimum_fbhp_bar'],75.)
            self.assertAlmostEqual(request['maximum_water_m3d'],float(separator.loc[separator.hour==6,'separator_water_m3d'].iloc[0])+2.)


if __name__=='__main__':
    unittest.main()
