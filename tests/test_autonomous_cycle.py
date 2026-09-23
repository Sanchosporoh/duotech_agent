import tempfile
import unittest
import json
from pathlib import Path
from unittest.mock import patch
import pandas as pd
from src.autonomous_cycle import run


class AutonomousCycleTests(unittest.TestCase):
    @patch('src.autonomous_cycle.live_adaptation.prepare_lifts',return_value={'ready':False,'reason':'test'})
    @patch('src.autonomous_cycle.live_adaptation.run',return_value=[])
    @patch('src.autonomous_cycle.live_planning.prepare',return_value={'stage':'awaiting_model_state'})
    @patch('src.autonomous_cycle.live_checks.execute',return_value=[])
    @patch('src.autonomous_cycle.live_reasoning.generate')
    def test_runs_all_incidents_and_reuses_same_snapshot(self,generate,checks,planning,adaptation,lifts):
        generate.side_effect=lambda root,context,key:{'fingerprint':key,'answer':{'hypotheses':[]}}
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
            root=Path(folder)
            separator=pd.DataFrame([{'hour':0,'separator_oil_tpd':100,'plan_oil_tpd':110}])
            telemetry=pd.DataFrame([{'hour':0,'well_id':'arbitrary'}])
            incidents=pd.DataFrame([{'incident_id':name,'opened_hour':0,'observed_loss_tpd':10} for name in ['first','second']])
            result=run(root,separator,telemetry,0,incidents)
            self.assertEqual(set(result),{'first','second'})
            self.assertEqual(generate.call_count,2)
            # Two incidents share one field-wide compensation plan.
            self.assertEqual(planning.call_count,1)
            self.assertEqual(result['first']['field_plan'],result['second']['field_plan'])
            self.assertEqual(result['first']['field_plan']['incidents'],['first','second'])
            run(root,separator,telemetry,0,incidents)
            self.assertEqual(generate.call_count,2)
            # A terminated parent must not abandon an otherwise reusable answer.
            from src.live_reasoning import save
            from src.cycle_lock import acquire
            for path in (root/'data/live/executions').glob('*.json'):
                state=json.loads(path.read_text(encoding='utf-8'))
                state['stage']='running';save(path,state)
            calls=planning.call_count
            with acquire(root,'petex.lock') as locked:
                self.assertTrue(locked)
                waiting=run(root,separator,telemetry,0,incidents)
                self.assertTrue(all(s['stage']=='running' for s in waiting.values()))
                self.assertEqual(planning.call_count,calls)
            run(root,separator,telemetry,0,incidents)
            self.assertEqual(planning.call_count,calls+1)
            self.assertEqual(generate.call_count,2)

    @patch('src.autonomous_cycle.live_reasoning.generate',side_effect=RuntimeError('offline'))
    def test_failure_does_not_loop_on_ui_rerun(self,generate):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
            args=(Path(folder),pd.DataFrame([{'hour':0,'separator_oil_tpd':100,'plan_oil_tpd':110}]),pd.DataFrame([{'hour':0,'well_id':'any'}]),0,pd.DataFrame([{'incident_id':'any','opened_hour':0,'observed_loss_tpd':10}]))
            self.assertEqual(run(*args)['any']['stage'],'needs_attention')
            run(*args)
            self.assertEqual(generate.call_count,1)
