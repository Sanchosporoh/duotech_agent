import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from src import live_reasoning, live_execution
from src.calculation_dependencies import fingerprints

ROOT=Path(__file__).resolve().parents[1]


class DashboardApprovalTests(unittest.TestCase):
    def test_approval_button_writes_once_and_delays_effect(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'data/live').mkdir(parents=True);(root/'config').mkdir()
            for name in ['separator.csv','telemetry.csv']:
                shutil.copyfile(ROOT/'data/live'/name,root/'data/live'/name)
            shutil.copyfile(ROOT/'data/opportunity_register_structured.json',root/'data/opportunity_register_structured.json')
            shutil.copyfile(ROOT/'config/restoration_measures.json',root/'config/restoration_measures.json')
            rec={'ready':True,'basis':'test','limitations':[],
                 'selected':{'title':'Test proposal','expected_deficit_t':2,'expected_balance_t':-2,'unresolved':[],
                             'phases':[{'hours':17,'oil_delta_tpd':10,'water_delta_m3d':0,'wells':[]}]}}
            rec['candidates']=[rec['selected']]
            def run(project,separator,telemetry,hour,incidents):
                states={}
                for _,row in incidents.iterrows():
                    incident={'incident_id':row.incident_id,'opened_hour':int(row.opened_hour),'observed_loss_tpd':float(row.observed_loss_tpd)}
                    _,key=live_reasoning.snapshot(separator,telemetry,hour,incident,dependencies=fingerprints(project))
                    states[row.incident_id]={'stage':'awaiting_human_decision','fingerprint':key,'recommendation':rec}
                return states
            with patch('src.live_dashboard.autonomous_cycle.run',side_effect=run),patch('src.live_dashboard.live_checks.execute',return_value=[]):
                app=AppTest.from_string(f"from pathlib import Path\nfrom src.live_dashboard import render\nrender(Path({str(root)!r}))")
                app.session_state['live_hour']=6
                app.run(timeout=20)
                self.assertEqual(len(app.exception),0)
                app.checkbox[0].check()
                next(button for button in app.button if button.label=='Зафиксировать').click()
                app.run(timeout=20)
                self.assertEqual(len(app.exception),0)
                self.assertEqual(len(live_execution.load(root)['actions']),1)
                app.run(timeout=20)
                self.assertEqual(len(live_execution.load(root)['actions']),1)
