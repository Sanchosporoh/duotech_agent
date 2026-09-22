import unittest
import pandas as pd
from src.live_monitor import hypotheses,validate_inputs


class LiveMonitorTests(unittest.TestCase):
    def test_bad_input_reports_errors_instead_of_raising(self):
        separator=pd.DataFrame([{'hour':0,'plan_oil_tpd':100,'separator_oil_tpd':90,'separator_water_m3d':10}])
        telemetry=pd.DataFrame([{'hour':0,'well_id':'A','sensor_pressure_bar':100}])
        self.assertEqual(validate_inputs(separator,telemetry),[])
        self.assertTrue(validate_inputs(separator.drop(columns=['hour']),telemetry))
        for field,value in [('hour','bad'),('hour',.5),('plan_oil_tpd','bad'),('separator_oil_tpd',float('inf')),('separator_water_m3d',-1)]:
            changed=separator.astype(object).copy();changed.loc[0,field]=value
            self.assertTrue(validate_inputs(changed,telemetry))

    def test_fluid_change_is_detected_without_pressure_change(self):
        frame=pd.DataFrame([{'hour':h,'well_id':'any','sensor_pressure_bar':100,'frequency_hz':60,'water_cut_pct':5 if h==0 else 50} for h in [0,3]])
        self.assertEqual(hypotheses(frame,3).iloc[0].well_id,'any')

    def test_candidate_follows_changed_well_not_incident_number(self):
        frame=pd.DataFrame([{'hour':h,'well_id':well,'sensor_pressure_bar':100+(5 if h==3 and well=='arbitrary-well' else 0),'frequency_hz':60} for h in [0,3] for well in ['arbitrary-well','other']])
        result=hypotheses(frame,3)
        self.assertEqual(set(result.well_id),{'arbitrary-well'})
        frame.loc[(frame.hour==3)&(frame.well_id=='arbitrary-well'),'sensor_pressure_bar']=100
        self.assertEqual(hypotheses(frame,3).iloc[0].well_id,'—')

    def test_future_and_stale_measurements_do_not_localize(self):
        frame=pd.DataFrame([{'hour':h,'well_id':'new-well','sensor_pressure_bar':100+h*10,'frequency_hz':60} for h in [0,3]])
        self.assertEqual(hypotheses(frame,1).iloc[0].well_id,'—')
        self.assertEqual(hypotheses(frame,4).iloc[0].well_id,'—')
