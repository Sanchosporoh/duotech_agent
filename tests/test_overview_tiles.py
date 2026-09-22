import unittest
import tempfile
from pathlib import Path
import pandas as pd
from src.measurement_overview import allocation_tiles,well_statuses
from src.reset_decisions import reset
from src.live_reasoning import save
from src.live_execution import load


class OverviewTests(unittest.TestCase):
    def test_tile_areas_and_signed_gap(self):
        allocation=pd.DataFrame({'Скважина':['A','B'],'Оценочный вклад, т/сут':[60.,40.]})
        for measured,residual in [(86.,-14.),(110.,10.)]:
            tiles=allocation_tiles(allocation,measured)
            self.assertEqual(tiles[tiles.gap]['Нефть, т/сут'].iloc[0],residual)
            areas=(tiles.x2-tiles.x)*(tiles.y2-tiles.y)
            self.assertAlmostEqual(areas.sum(),320000)
            self.assertAlmostEqual(areas[tiles.gap].iloc[0]/areas.sum(),abs(residual)/(100+abs(residual)))
        self.assertFalse(allocation_tiles(allocation,100.).gap.any())
        self.assertFalse(allocation_tiles(allocation,None).gap.any())

    def test_anomalies_precede_normal_wells(self):
        telemetry=pd.DataFrame([{'well_id':w,'hour':h,'frequency_hz':0 if w=='Z' and h==1 else 60,
                                 'sensor_pressure_bar':105 if w=='Y' and h==1 else 100} for h in [0,1] for w in ['A','Y','Z']])
        self.assertEqual(well_statuses(telemetry,1)['Скважина'].tolist(),['Z','Y','A'])

    def test_reset_preserves_inputs_and_archives_decisions(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            save(root/'data/live/approved_actions.json',{'actions':[{'incident_id':'test'}]})
            save(root/'data/live/lifecycle.json',{'incidents':{'test':{}}})
            path=root/'data/live/separator.csv';path.write_text('unchanged',encoding='utf-8')
            archive=reset(root)
            self.assertEqual(load(root)['actions'],[])
            self.assertEqual(path.read_text(encoding='utf-8'),'unchanged')
            self.assertTrue((archive/'approved_actions.json').exists())
