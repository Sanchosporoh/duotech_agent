"""E3: one field-wide compensation plan, stable incident identities, known own actions."""
import os
import tempfile
import unittest
from unittest.mock import patch
import pandas as pd
from src import autonomous_cycle, cycle_service, incident_lifecycle, incident_view, live_execution, live_monitor
from tests.support import FIRST, SECOND, make_project


def states(root,hour):
    separator,telemetry,_=cycle_service.load_measurements(root)
    return autonomous_cycle.read_states(root,separator,telemetry,hour,incident_view.opened_incidents(separator,hour))


class FieldDayTests(unittest.TestCase):
    def test_second_incident_gets_its_own_plan_after_the_first_is_approved(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory, patch.dict(os.environ,{'AGENT_TOOL_BACKEND':'stub'}):
            root=make_project(directory)
            for _ in range(7):cycle_service.tick(root)
            first=states(root,6)[FIRST]
            self.assertEqual(first['stage'],'awaiting_human_decision')
            self.assertEqual(first['field_plan']['incidents'],[FIRST])
            action=live_execution.approve(root,first['field_plan']['incidents'],6,first['fingerprint'],first['recommendation'],True)
            self.assertEqual(action['incident_ids'],[FIRST])
            incident_lifecycle.record_decision(root/'data/live/lifecycle.json',FIRST,'Утверждено','',first['recommendation']['selected']['title'],'test')
            for _ in range(9):cycle_service.tick(root)  # up to 15:00
            later=states(root,15)
            self.assertEqual(later[FIRST]['stage'],'approved_for_execution')
            second=later[SECOND]
            # The missing facts at 11-12 h no longer block the rest of the day.
            self.assertEqual(second['stage'],'awaiting_human_decision',second.get('reason'))
            self.assertEqual(second['plan']['need']['estimated_hours'],[11,12])
            # The approved regimes of the first plan are not treated as new events.
            self.assertEqual(second['field_plan']['incidents'],[SECOND])
            self.assertFalse(any(fit.get('stage')=='needs_data' for fit in second['adaptation']))
            # 18:00: W50 pressure falls after the W22 stop. PROSPER cannot check a PCP well, which is not
            # evidence against its model: W50 stays usable. It already breaks the FBHP limit in the
            # current network, so every set must contain it.
            for _ in range(3):cycle_service.tick(root)
            evening=states(root,18)[SECOND]
            self.assertNotEqual(evening['stage'],'awaiting_model_state',evening.get('reason'))
            self.assertNotIn('W_BEL_50_TLBB',[w['well_id'] for w in evening['model_state']['excluded_wells']])
            # Either the measure sets already contain it or it was added as a compulsory correction.
            for alternative in evening['plan']['proposal']['alternatives']:
                self.assertIn('W_BEL_50_TLBB',alternative['selected_wells'])


class IdentityTests(unittest.TestCase):
    def test_earlier_data_correction_does_not_rename_later_incident(self):
        separator=pd.DataFrame({'hour':range(5),'timestamp':pd.date_range('2026-09-14',periods=5,freq='h'),
                                'plan_oil_tpd':100.,'separator_oil_tpd':[100.,90.,100.,100.,80.]})
        before=incident_view.opened_incidents(separator,4).incident_id.tolist()
        corrected=separator.copy();corrected.loc[1,'separator_oil_tpd']=100.
        after=incident_view.opened_incidents(corrected,4).incident_id.tolist()
        self.assertEqual(before,['INC-20260914-0100','INC-20260914-0400'])
        self.assertEqual(after,['INC-20260914-0400'])


class OwnActionTests(unittest.TestCase):
    def test_approved_control_change_is_not_a_hypothesis(self):
        rows=[{'hour':h,'well_id':'W','frequency_hz':50. if h==0 else 55.,'sensor_pressure_bar':100.,
               'control_source':'measured' if h==0 else source} for h in (0,1) for source in ['approved_plan']]
        telemetry=pd.DataFrame(rows)
        self.assertNotIn('W',live_monitor.hypotheses(telemetry,1).well_id.tolist())
        telemetry.loc[1,'control_source']='measured'
        self.assertIn('Изменение управляющего режима',live_monitor.hypotheses(telemetry,1).hypothesis.tolist())


if __name__=='__main__':
    unittest.main()


class BoundaryTests(unittest.TestCase):
    def test_exact_five_percent_deviation_opens_an_incident(self):
        plan=277.777
        separator=pd.DataFrame({'hour':[0,1],'timestamp':pd.date_range('2026-09-14',periods=2,freq='h'),
                                'plan_oil_tpd':plan,'separator_oil_tpd':[plan,plan*0.95]})
        self.assertEqual(len(incident_view.opened_incidents(separator,1)),1)
        separator.loc[1,'separator_oil_tpd']=plan*0.951
        self.assertTrue(incident_view.opened_incidents(separator,1).empty)

