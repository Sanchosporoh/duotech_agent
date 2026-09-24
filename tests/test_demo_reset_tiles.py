import tempfile
import unittest
from pathlib import Path
import pandas as pd
from src.live_reasoning import save
from src.reset_decisions import reset
from src.measurement_overview import known_changes
from src import live_execution


class ResetTests(unittest.TestCase):
    def test_plain_reset_keeps_calculations_and_forgets_basis(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root=Path(directory);live=root/'data/live'
            save(live/'field_basis.json',{'hour':6});save(live/'escalations.json',{'items':[]})
            save(live/'reasoning/key.json',{'answer':{}})
            archive=reset(root)
            self.assertFalse((live/'field_basis.json').exists())
            self.assertFalse((live/'escalations.json').exists())
            self.assertTrue((archive/'field_basis.json').exists())
            self.assertTrue((live/'reasoning/key.json').exists())

    def test_fresh_reset_moves_saved_calculations_to_archive(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root=Path(directory);live=root/'data/live'
            save(live/'reasoning/key.json',{'answer':{}});save(live/'network/k/s/result.json',{})
            (live/'separator.csv').write_text('kept',encoding='utf-8')
            archive=reset(root,fresh=True)
            self.assertFalse((live/'reasoning').exists())
            self.assertTrue((archive/'network/k/s/result.json').exists())
            self.assertEqual((live/'separator.csv').read_text(encoding='utf-8'),'kept')


class KnownChangeTests(unittest.TestCase):
    def test_tiles_include_approved_regimes_and_measured_stops(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root=Path(directory)
            proposal={'ready':True,'selected':{'phases':[{'hours':10,'oil_delta_tpd':3,'water_delta_m3d':0,'wells':[],
                       'well_deltas':{'A':2.,'B':1.}}]}}
            live_execution.approve(root,['I'],6,'key',proposal,True)
            parts=pd.DataFrame({'Скважина':['A','B','C'],'Оценочный вклад, т/сут':[10.,5.,4.]})
            telemetry=pd.DataFrame([{'hour':7,'well_id':'B','frequency_hz':0.},{'hour':7,'well_id':'C','frequency_hz':50.}])
            before=known_changes(root,telemetry,6,parts).set_index('Скважина')
            self.assertEqual(before.loc['A','Оценочный вклад, т/сут'],10.)   # effect starts next hour
            after=known_changes(root,telemetry,7,parts).set_index('Скважина')
            self.assertEqual(after.loc['A','Оценочный вклад, т/сут'],12.)
            self.assertEqual((after.loc['B','Оценочный вклад, т/сут'],after.loc['B','Почему']),(0.,'остановлена по замеру'))
            self.assertEqual(after.loc['C','Оценочный вклад, т/сут'],4.)


if __name__=='__main__':
    unittest.main()
