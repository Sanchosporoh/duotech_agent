import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from src import cycle_service, live_reasoning, live_execution
from src.calculation_dependencies import fingerprints
from tests.support import FIRST, make_project


def recommendation(ready=True):
    rec={'ready':ready,'basis':'test','limitations':[],
         'selected':{'title':'Test proposal','expected_deficit_t':2,'expected_balance_t':-2,'unresolved':[],
                     'phases':[{'hours':17,'oil_delta_tpd':10,'water_delta_m3d':0,'wells':[]}]}}
    rec['candidates']=[rec['selected']]
    return rec if ready else {'ready':False,'reason':'test'}


class DashboardDecisionTests(unittest.TestCase):
    """Exercise the live HITL form with the autonomous cycle replaced by a fixed state."""

    def open_app(self, root, ready=True):
        rec=recommendation(ready)
        def run(project,separator,telemetry,hour,incidents):
            states={}
            for _,row in incidents.iterrows():
                incident={'incident_id':row.incident_id,'opened_hour':int(row.opened_hour),'observed_loss_tpd':float(row.observed_loss_tpd)}
                _,key=live_reasoning.snapshot(separator,telemetry,hour,incident,dependencies=fingerprints(project))
                states[row.incident_id]={'stage':'awaiting_human_decision' if ready else 'needs_attention','fingerprint':key,'recommendation':rec}
            return states
        patches=[patch('src.live_dashboard.autonomous_cycle.read_states',side_effect=run),
                 patch('src.live_dashboard.live_checks.execute',return_value=[])]
        for item in patches:
            item.start(); self.addCleanup(item.stop)
        cycle_service.set_clock(root,6,'simulated')
        app=AppTest.from_string(f"from pathlib import Path\nfrom src.live_dashboard import render\nrender(Path({str(root)!r}))")
        app.run(timeout=30)
        self.assertEqual(len(app.exception),0)
        return app

    def submit(self, app, decision, comment=''):
        next(r for r in app.radio if r.label=='Решение инженера').set_value(decision)
        next(t for t in app.text_input if t.label=='Комментарий / новое ограничение').set_value(comment)
        next(b for b in app.button if b.label=='Зафиксировать').click()
        app.run(timeout=30)
        self.assertEqual(len(app.exception),0)

    def incident(self, root):
        return json.loads((root/'data/live/lifecycle.json').read_text(encoding='utf-8'))['incidents'][FIRST]

    def test_approval_button_writes_once_and_delays_effect(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root=make_project(directory)
            app=self.open_app(root)
            app.checkbox[0].check()
            self.submit(app,'Утвердить')
            self.assertEqual(len(live_execution.load(root)['actions']),1)
            app.run(timeout=30)
            self.assertEqual(len(live_execution.load(root)['actions']),1)

    def test_return_with_comment_is_saved(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root=make_project(directory)
            self.submit(self.open_app(root),'Вернуть на доработку','Пересмотреть набор скважин')
            incident=self.incident(root)
            self.assertEqual(incident['stage'],'awaiting_revision_calculation')
            self.assertEqual(incident['versions'][-1]['human_comment'],'Пересмотреть набор скважин')

    def test_empty_comment_is_not_saved(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root=make_project(directory)
            app=self.open_app(root)
            self.submit(app,'Вернуть на доработку')
            self.assertTrue(app.error)
            self.assertNotEqual(self.incident(root)['stage'],'awaiting_revision_calculation')

    def test_reject_is_saved_even_when_approval_is_not_allowed(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root=make_project(directory)
            app=self.open_app(root,ready=False)
            self.assertNotIn('Утвердить',next(r for r in app.radio if r.label=='Решение инженера').options)
            self.submit(app,'Отклонить','Не подходит')
            self.assertEqual(self.incident(root)['stage'],'closed_rejected')
            self.assertEqual(live_execution.load(root)['actions'],[])


if __name__=='__main__':
    unittest.main()
