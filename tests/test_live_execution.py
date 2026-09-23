import tempfile
import unittest
from pathlib import Path
import pandas as pd
from src.live_execution import approve,load,apply


class ExecutionTests(unittest.TestCase):
    def test_acknowledgement_and_idempotence(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root=Path(directory);rec={'ready':True,'selected':{'phases':[]}}
            with self.assertRaises(ValueError):approve(root,'I',6,'key',rec)
            self.assertEqual(load(root)['actions'],[])
            approve(root,'I',6,'key',rec,True);approve(root,'I',6,'key',rec,True)
            self.assertEqual(len(load(root)['actions']),1)

    def test_delayed_recovery_and_no_input_mutation(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root=Path(directory)
            phases=[{'hours':1,'oil_delta_tpd':0,'water_delta_m3d':0,'wells':[]},
                    {'hours':3,'oil_delta_tpd':-10,'water_delta_m3d':-1,'wells':[]},
                    {'hours':2,'oil_delta_tpd':20,'water_delta_m3d':0,'wells':[]}]
            approve(root,'I',6,'key',{'ready':True,'selected':{'phases':phases}},True)
            original=pd.DataFrame({'hour':list(range(13)),'separator_oil_tpd':[100.]*13})
            telemetry=pd.DataFrame({'hour':[6],'well_id':['A']})
            result,_=apply(root,original,telemetry)
            self.assertEqual(result.loc[6,'separator_oil_tpd'],100)
            self.assertEqual(result.loc[7,'separator_oil_tpd'],100)
            self.assertEqual(result.loc[10,'separator_oil_tpd'],90)
            self.assertEqual(result.loc[11,'separator_oil_tpd'],120)
            self.assertTrue((original.separator_oil_tpd==100).all())
            repeated,_=apply(root,original,telemetry)
            pd.testing.assert_frame_equal(result,repeated)
