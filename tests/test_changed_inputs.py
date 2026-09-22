import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import pandas as pd
from src.autonomous_cycle import run
from src.incident_view import opened_incidents
from src.live_reasoning import snapshot,save
from src.cycle_lock import acquire


class ChangedInputTests(unittest.TestCase):
    def test_parallel_session_does_not_start_another_cycle(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            with acquire(root) as locked:
                self.assertTrue(locked)
                with patch('src.autonomous_cycle._run') as process:
                    result=run(root,None,None,6,pd.DataFrame([{'incident_id':'test'}]))
                    self.assertEqual(result['test']['stage'],'running')
                    process.assert_not_called()
            with acquire(root) as locked:self.assertTrue(locked)

    def test_incidents_independent_of_file_order(self):
        data=pd.DataFrame({'hour':[0,1,2,3],'plan_oil_tpd':[100]*4,'separator_oil_tpd':[100,94,94,80]})
        expected=opened_incidents(data,3)
        for seed in range(10):
            pd.testing.assert_frame_equal(expected,opened_incidents(data.sample(frac=1,random_state=seed),3))

    def test_snapshot_ignores_order_but_detects_changes(self):
        sep=pd.DataFrame({'hour':[0,1],'plan_oil_tpd':[100,100],'separator_oil_tpd':[100,94]})
        tel=pd.DataFrame({'hour':[0,0,1,1],'well_id':['A','B','A','B'],'sensor_pressure_bar':[100,100,105,100]})
        expected=snapshot(sep,tel,1,{})[1]
        for seed in range(10):
            self.assertEqual(expected,snapshot(sep.sample(frac=1,random_state=seed),tel.sample(frac=1,random_state=seed),1,{})[1])
        tel.loc[3,'sensor_pressure_bar']=106
        self.assertNotEqual(expected,snapshot(sep,tel,1,{})[1])

    @patch('src.autonomous_cycle.live_reasoning.generate')
    def test_missing_current_fact_never_calls_model(self,generate):
        with tempfile.TemporaryDirectory() as directory:
            incidents=pd.DataFrame([{'incident_id':'test','opened_hour':0,'observed_loss_tpd':10}])
            for value in [None,float('nan'),float('inf'),-1]:
                sep=pd.DataFrame({'hour':[0,1],'plan_oil_tpd':[100,100],'separator_oil_tpd':[90,value]})
                result=run(Path(directory),sep,pd.DataFrame(),1,incidents)
                self.assertEqual(result['test']['stage'],'needs_data')
            generate.assert_not_called()

    def test_failed_save_preserves_previous_result(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'result.json'
            save(path,{'stage':'completed'})
            original=path.read_bytes()
            with patch('src.live_reasoning.os.replace',side_effect=OSError('interrupted')):
                with self.assertRaises(OSError):save(path,{'stage':'running'})
            self.assertEqual(path.read_bytes(),original)
            self.assertEqual(list(path.parent.glob('*.tmp')),[])

    def test_atomic_save_retries_temporary_windows_permission_error(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'result.json'
            from os import replace as real_replace
            attempts={'count':0}
            def briefly_locked(source,target):
                attempts['count']+=1
                if attempts['count']<3:raise PermissionError(5,'temporarily locked')
                return real_replace(source,target)
            with patch('src.live_reasoning.os.replace',side_effect=briefly_locked):
                save(path,{'stage':'completed'})
            self.assertEqual(attempts['count'],3)
            self.assertIn('completed',path.read_text(encoding='utf-8'))
