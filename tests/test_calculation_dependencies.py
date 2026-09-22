import tempfile
import unittest
from pathlib import Path
from src.calculation_dependencies import fingerprints
from src.live_reasoning import save, snapshot
import pandas as pd


class DependencyTests(unittest.TestCase):
    def test_model_and_limits_invalidate_unchanged_measurements(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            model=root/'runtime/petex_case/IM_2022_06/A.Out'
            model.parent.mkdir(parents=True);model.write_bytes(b'model-one')
            save(root/'config/diagnostic_sensors.json',{'tolerance_bar':1.5})
            frame=pd.DataFrame([{'hour':0}])
            def key():return snapshot(frame,frame,0,{},dependencies=fingerprints(root))[1]
            first=key();self.assertEqual(first,key())
            model.write_bytes(b'model-two')
            second=key();self.assertNotEqual(first,second)
            save(root/'config/diagnostic_sensors.json',{'tolerance_bar':2.})
            self.assertNotEqual(second,key())

    def test_external_model_is_not_read(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            save(root/'config/diagnostic_models.json',{'A':{'working_model':'../forbidden.Out'}})
            with self.assertRaises(ValueError):fingerprints(root)
