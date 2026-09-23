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


class PlannedRegimeTests(unittest.TestCase):
    def test_plan_sets_only_regulated_wells_and_keeps_measured_stop(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root=Path(directory)
            wells=[{'well_id':'R','well_type':'OilProducerESP','control_actual':50.,'control_optimised':55.},
                   {'well_id':'U','well_type':'OilProducerESP','control_actual':40.,'control_optimised':None},
                   {'well_id':'S','well_type':'OilProducerESP','control_actual':45.,'control_optimised':48.}]
            approve(root,['I'],0,'key',{'ready':True,'selected':{'phases':[{'hours':3,'oil_delta_tpd':1,'water_delta_m3d':0,'wells':wells}]}},True)
            separator=pd.DataFrame({'hour':[0,1,2],'separator_oil_tpd':[100.]*3})
            telemetry=pd.DataFrame({'hour':[1,1,1],'well_id':['R','U','S'],'frequency_hz':[50.,41.,0.]})
            _,result=apply(root,separator,telemetry)
            result=result.set_index('well_id')
            self.assertEqual((result.loc['R','frequency_hz'],result.loc['R','control_source']),(55.,'approved_plan'))
            self.assertEqual((result.loc['U','frequency_hz'],result.loc['U','control_source']),(41.,'measured'))
            self.assertEqual((result.loc['S','frequency_hz'],result.loc['S','control_source']),(0.,'measured'))
