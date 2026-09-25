"""4.2: the agent chooses the tool — single-well screening in GAP or full measure sets."""
import os
import tempfile
import unittest
from unittest.mock import patch
from src import autonomous_cycle, cycle_service, incident_view, live_planning, tool_stubs
from tests.support import FIRST, make_project


def state_at_six(root):
    for _ in range(7):run=cycle_service.tick(root)
    separator,telemetry,_=cycle_service.load_measurements(root)
    return run,autonomous_cycle.read_states(root,separator,telemetry,6,incident_view.opened_incidents(separator,6))[FIRST]


class ToolChoiceTests(unittest.TestCase):
    def test_screening_without_single_solution_leads_to_measure_sets(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory, patch.dict(os.environ,{'AGENT_TOOL_BACKEND':'stub'}):
            run,state=state_at_six(make_project(directory))
            trace=state['plan']['tool_trace']
            self.assertEqual([t['tool'] for t in trace],['screen_single_wells','screen_single_wells','calculate_sets'])
            self.assertIn('ни одна скважина',trace[1]['result'])
            self.assertEqual(state['stage'],'awaiting_human_decision')

    def test_single_covering_well_skips_the_second_llm_call(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory, patch.dict(os.environ,{'AGENT_TOOL_BACKEND':'stub'}):
            screen={'wells':[{'well_id':'W_BEL_13_TLBB','gain_oil_tpd':20.,'constraints_met':True,'covers_need':True}]}
            with patch('src.live_planning.screen_single_wells',return_value=screen):
                run,state=state_at_six(make_project(directory))
            self.assertEqual(run['tools']['llm_calls'],2)   # diagnosis + tool choice only
            alternatives=state['plan']['proposal']['alternatives']
            self.assertEqual(alternatives[0]['title'],'Одна скважина по скринингу: W_BEL_13_TLBB')
            self.assertIn('W_BEL_13_TLBB',alternatives[0]['selected_wells'])

    def test_direct_choice_of_sets_runs_no_screening(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory, patch.dict(os.environ,{'AGENT_TOOL_BACKEND':'stub'}):
            real=tool_stubs.codex
            def direct(prompt,schema):
                if 'alternatives' in schema['properties']:
                    return dict(tool_stubs._measure_sets(tool_stubs._payload(prompt)),tool='calculate_sets',tool_reason='Нужны несколько скважин')
                return real(prompt,schema)
            with patch('src.tool_stubs.codex',side_effect=direct), patch('src.live_planning.screen_single_wells') as screen:
                run,state=state_at_six(make_project(directory))
            screen.assert_not_called()
            self.assertEqual([t['tool'] for t in state['plan']['tool_trace']],['calculate_sets'])

    def test_screen_ignores_violations_that_exist_before_any_change(self):
        limits={'minimum_fbhp_bar':80.}
        alternative={'title':'single:A','status':'conditional_calculated','gain_oil_tpd':5.,'water_limit_met':True,
                     'current':{'wells':[{'well_id':'V','fbhp_bar':79.5,'oil_sm3d':3}]},
                     'optimised':{'wells':[{'well_id':'V','fbhp_bar':79.5,'oil_sm3d':3},{'well_id':'A','fbhp_bar':85,'oil_sm3d':9}]}}
        with patch('src.live_planning.calculate',return_value={'network':{'alternatives':[alternative]}}):
            result=live_planning.screen_single_wells(None,{},'k',[{'well_id':'A'}],{},{'required_extra_oil_tpd':4.},limits)
        self.assertEqual(result['wells'],[{'well_id':'A','gain_oil_tpd':5.0,'constraints_met':True,'covers_need':True}])


if __name__=='__main__':
    unittest.main()
