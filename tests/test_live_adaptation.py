import json
from pathlib import Path
import tempfile
import unittest
import pandas as pd
from src.live_adaptation import run, prepare_lifts


class AdaptationTests(unittest.TestCase):
    def test_stale_unchanged_signal_cannot_be_used_as_current_model_state(self):
        from unittest.mock import patch
        from src.live_reasoning import save
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root=Path(directory)
            save(root/'config/diagnostic_models.json',{'A':{'working_model':'runtime/A.Out'}})
            save(root/'config/diagnostic_sensors.json',{})
            signals=[{'hour':h,'well_id':'A','frequency_hz':60.,'sensor_pressure_bar':100.} for h in [0,2]]
            with patch('src.live_adaptation.tool_gateway.run_worker') as worker:
                for history in [signals,signals+[dict(signals[-1],hour=8,sensor_pressure_bar=120.)]]:
                    context={'hour':6,'telemetry':history}
                    result=run(root,context,'stale',{'hypotheses':[{'candidate_wells':['A']}]})
                    self.assertEqual(result[0]['stage'],'needs_data')
                    state=prepare_lifts(root,context,result)
                    # A stale signal is not evidence against the model: no lift table, no exclusion;
                    # the age of the data lowers the well trust instead (src/well_trust.py).
                    self.assertTrue(state['ready'])
                    self.assertEqual(state['lift_tables'],[])
                    self.assertEqual(state['excluded_wells'],[])
                    self.assertTrue(any('проверка PROSPER невозможна' in a for a in state['assumptions']))
                worker.assert_not_called()

    def test_partial_diagnostic_result_does_not_override_failed_attempt(self):
        from unittest.mock import patch
        from src.live_reasoning import save
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root=Path(directory)
            save(root/'config/diagnostic_models.json',{'A':{'working_model':'runtime/A.Out'}})
            save(root/'config/diagnostic_sensors.json',{'A':{'pressure_residual_tolerance_bar':1.5}})
            signal={'hour':6,'well_id':'A','frequency_hz':60.,'sensor_pressure_bar':110.,'whp_bara':5.,'water_cut_pct':5.,'gor_m3m3':10.}
            folder=root/'data/live/adaptation/dispatch_v2_test/A'
            save(folder/'result.json',{'well_id':'A','candidates':[{'kind':'pump','pressure_compatible':True}]})
            save(folder/'attempt.json',{'stage':'needs_attention','reason':'worker failed'})
            with patch('src.live_adaptation.tool_gateway.run_worker') as worker:
                result=run(root,{'hour':6,'telemetry':[signal]},'test',{'hypotheses':[{'candidate_wells':['A']}]})
            self.assertEqual(result[0]['stage'],'needs_attention')
            self.assertNotIn('candidates',result[0])
            worker.assert_not_called()

    def test_failed_export_file_is_not_accepted_as_completed(self):
        import hashlib
        from src.live_reasoning import save
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root=Path(directory);(root/'config').mkdir()
            (root/'config/diagnostic_models.json').write_text(json.dumps({'A':{'working_model':'runtime/A.Out'}}),encoding='utf-8')
            candidate={'kind':'pump','pressure_compatible':True}
            signal={'hour':6,'well_id':'A','frequency_hz':60.,'sensor_pressure_bar':110.,'whp_bara':5.,'water_cut_pct':5.,'gor_m3m3':10.}
            request={f:signal[f] for f in ['frequency_hz','sensor_pressure_bar','whp_bara','water_cut_pct','gor_m3m3']}
            request.update(working_model='runtime/A.Out',candidate=candidate)
            digest=hashlib.sha256(json.dumps(request,sort_keys=True).encode()).hexdigest()
            folder=root/'data/live/lift_tables'/digest
            save(folder/'attempt.json',{'stage':'needs_attention','reason':'incomplete export'})
            (folder/'fitted.tpd').write_bytes(b'partial')
            result=prepare_lifts(root,{'telemetry':[signal]},[{'well_id':'A','candidates':[candidate]}])
            self.assertFalse(result['ready'])
    def test_absent_pcp_frequency_is_not_zero_or_missing_model(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root=Path(directory);(root/'config').mkdir()
            (root/'config/diagnostic_models.json').write_text(json.dumps({'A':{'working_model':'runtime/A.Out'}}),encoding='utf-8')
            (root/'config/diagnostic_sensors.json').write_text('{}',encoding='utf-8')
            telemetry=[{'hour':h,'well_id':'A','frequency_hz':float('nan'),'sensor_pressure_bar':100} for h in [0,6]]
            result=run(root,{'hour':6,'telemetry':telemetry},'test',{'hypotheses':[{'candidate_wells':['A']}]})
            self.assertEqual(result[0]['stage'],'screened')
            self.assertFalse((root/'data').exists())
    def test_ambiguous_pressure_fit_leaves_well_untouched(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root=Path(directory)
            (root/'config').mkdir()
            (root/'config'/'diagnostic_models.json').write_text('{}',encoding='utf-8')
            result=prepare_lifts(root,{'telemetry':[]},[{'well_id':'A','candidates':[{'pressure_compatible':True},{'pressure_compatible':True}]}])
            self.assertTrue(result['ready'])
            self.assertEqual(result['lift_tables'],[])
            self.assertEqual([w['well_id'] for w in result['excluded_wells']],['A'])
            self.assertFalse((root/'data').exists())

    def test_inflow_change_is_not_transferred_as_lift_only(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root=Path(directory)
            (root/'config').mkdir()
            (root/'config'/'diagnostic_models.json').write_text('{}',encoding='utf-8')
            result=prepare_lifts(root,{'telemetry':[]},[{'well_id':'A','candidates':[{'pressure_compatible':True,'kind':'inflow'}]}])
            self.assertTrue(result['ready'])
            self.assertEqual(result['lift_tables'],[])
            self.assertEqual([w['well_id'] for w in result['excluded_wells']],['A'])
            self.assertFalse((root/'data').exists())
    def test_missing_telemetry_does_not_launch_model(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root=Path(directory)
            (root/'config').mkdir()
            (root/'config'/'diagnostic_models.json').write_text(json.dumps({'A':{'working_model':'runtime/A.Out'}}),encoding='utf-8')
            (root/'config'/'diagnostic_sensors.json').write_text('{}',encoding='utf-8')
            result=run(root,{'hour':6,'telemetry':[]},'test',{'hypotheses':[{'candidate_wells':['A']}]})
            self.assertEqual(result[0]['stage'],'needs_data')
            self.assertFalse((root/'data').exists())

    def test_unknown_well_is_not_replaced_by_reference_model(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root=Path(directory)
            (root/'config').mkdir()
            for name in ['diagnostic_models','diagnostic_sensors']:
                (root/'config'/f'{name}.json').write_text('{}',encoding='utf-8')
            result=run(root,{'hour':6,'telemetry':[]},'test',{'hypotheses':[{'candidate_wells':['UNKNOWN']}]})
            self.assertEqual(result[0]['stage'],'needs_data')
            self.assertFalse((root/'data').exists())
