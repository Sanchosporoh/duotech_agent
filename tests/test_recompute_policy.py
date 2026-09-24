"""Recompute levels while incidents wait for a decision: none / network / full."""
import json
import os
import tempfile
import unittest
from unittest.mock import patch
import pandas as pd
from src import cycle_service, recompute_policy
from tests.support import FIRST, ROOT, make_project

POLICY=json.loads((ROOT/'config/recompute_policy.json').read_text(encoding='utf-8'))


def signature(**changes):
    base={'hour':6,'incidents':['I'],'comments':{'I':''},'dependencies':'d','events':['W|Изменение лифта'],
          'controls':{'W':50.,'V':40.},'pressures':{'W':100.},'oil_tpd':260.,'water_m3d':20.}
    base.update(changes)
    return base


class ClassifyTests(unittest.TestCase):
    def level(self,**changes):
        return recompute_policy.classify(POLICY,signature(),signature(**dict({'hour':7},**changes)))[0]

    def test_levels(self):
        self.assertEqual(self.level(),'none')
        self.assertEqual(self.level(pressures={'W':101.}),'none')
        self.assertEqual(self.level(water_m3d=20.3,oil_tpd=259.),'none')
        self.assertEqual(self.level(controls={'W':50.,'V':45.}),'network')
        self.assertEqual(self.level(water_m3d=21.),'network')
        self.assertEqual(self.level(events=['W|Изменение лифта','V|Изменение управляющего режима']),'network')
        self.assertEqual(self.level(events=['W|Изменение лифта','V|Остановка оборудования или потеря питания']),'full')
        self.assertEqual(self.level(pressures={'W':98.}),'full')
        self.assertEqual(self.level(oil_tpd=250.),'full')
        self.assertEqual(self.level(comments={'I':'не трогать W'}),'full')
        self.assertEqual(self.level(incidents=['I','J'],comments={'I':'','J':''}),'full')
        self.assertEqual(self.level(dependencies='e'),'full')
        self.assertEqual(self.level(hour=12),'full')

    def test_new_incident_is_not_reported_as_engineer_comment(self):
        level,reasons=recompute_policy.classify(POLICY,signature(),signature(hour=7,incidents=['I','J'],comments={'I':'','J':''}))
        self.assertEqual(level,'full')
        self.assertNotIn('Инженер вернул предложение с комментарием',reasons)

    def test_without_policy_every_hour_is_full(self):
        self.assertEqual(recompute_policy.classify(None,signature(),signature(hour=7))[0],'full')


class CycleLevelTests(unittest.TestCase):
    def test_waiting_incident_is_not_recalculated_without_changes(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory, patch.dict(os.environ,{'AGENT_TOOL_BACKEND':'stub'}):
            root=make_project(directory)
            for _ in range(7):first=cycle_service.tick(root)
            later=cycle_service.tick(root)  # 07:00, nothing new
            self.assertEqual((first['tools']['llm_calls'],first['tools']['gap_runs']),(2,3))
            self.assertEqual((later['tools']['llm_calls'],later['tools']['gap_runs'],later['tools']['prosper_runs']),(0,0,0))
            self.assertEqual(later['incidents'][FIRST]['stage'],'awaiting_human_decision')

    def test_changed_water_recalculates_network_only(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory, patch.dict(os.environ,{'AGENT_TOOL_BACKEND':'stub'}):
            root=make_project(directory)
            path=root/'data/live/separator.csv'
            separator=pd.read_csv(path);separator.loc[separator.hour==7,'separator_water_m3d']+=1.;separator.to_csv(path,index=False)
            for _ in range(8):run=cycle_service.tick(root)
            self.assertEqual((run['tools']['llm_calls'],run['tools']['prosper_runs']),(0,0))
            self.assertGreater(run['tools']['gap_runs'],0)

    def test_new_pressure_change_recalculates_fully(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory, patch.dict(os.environ,{'AGENT_TOOL_BACKEND':'stub'}):
            root=make_project(directory)
            path=root/'data/live/telemetry.csv'
            telemetry=pd.read_csv(path)
            selected=(telemetry.well_id=='W_BEL_27_TLBB')&(telemetry.hour==7)
            telemetry.loc[selected,'sensor_pressure_bar']+=3.;telemetry.to_csv(path,index=False)
            for _ in range(8):run=cycle_service.tick(root)
            self.assertEqual(run['tools']['llm_calls'],2)


if __name__=='__main__':
    unittest.main()
