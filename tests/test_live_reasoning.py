import unittest
from unittest.mock import patch
import pandas as pd
from src.live_reasoning import snapshot, generate


class LiveReasoningTests(unittest.TestCase):
    def test_snapshot_excludes_future_and_invalidates_on_edits(self):
        separator=pd.DataFrame([{'hour':0,'separator_oil_tpd':100},{'hour':1,'separator_oil_tpd':90}])
        telemetry=pd.DataFrame([{'hour':0,'well_id':'any','sensor_pressure_bar':100},{'hour':1,'well_id':'future','sensor_pressure_bar':200}])
        context,key=snapshot(separator,telemetry,0,{'incident_id':'any'})
        self.assertEqual(len(context['telemetry']),1)
        telemetry.loc[0,'sensor_pressure_bar']=110
        self.assertNotEqual(key,snapshot(separator,telemetry,0,{'incident_id':'any'})[1])
        self.assertNotEqual(key,snapshot(separator,telemetry,0,{'incident_id':'any'},'new constraint')[1])

    @patch('src.live_reasoning.ask_codex')
    def test_unknown_well_is_rejected(self, ask):
        ask.return_value={'hypotheses':[{'candidate_wells':['invented']}],'assessment':'x'}
        with self.assertRaises(ValueError):
            generate({'telemetry':[{'well_id':'known'}]},'hash')
