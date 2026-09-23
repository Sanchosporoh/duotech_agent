import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
import pandas as pd
from src import autonomous_cycle, cycle_service, incident_view
from tests.support import ROOT, make_project


class CycleServiceTests(unittest.TestCase):
    def test_simulated_clock_walks_the_day_once_and_journals_every_hour(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory, \
                patch('src.cycle_service.autonomous_cycle.run',return_value={}) as cycle:
            root=make_project(directory)
            hours=[cycle_service.tick(root)['hour'] for _ in range(24)]
            self.assertEqual(hours,list(range(24)))
            self.assertEqual(cycle_service.tick(root)['status'],'day_finished')
            self.assertEqual(len(list((root/'data/live/runs').glob('*.json'))),24)
            # The cycle is called only for hours with an open incident (first one at 06:00).
            self.assertEqual(cycle.call_args_list[0].args[3],6)

    def test_wall_clock_uses_current_hour(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root=make_project(directory)
            result=cycle_service.tick(root,'wall',now=datetime(2026,9,23,2,30))
            self.assertEqual((result['hour'],result['status']),(2,'no_incidents'))
            self.assertEqual(cycle_service.clock(root)['mode'],'wall')

    def test_invalid_input_is_journaled_without_calculation(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory, \
                patch('src.cycle_service.autonomous_cycle.run') as cycle:
            root=make_project(directory)
            path=root/'data/live/separator.csv'
            frame=pd.read_csv(path);frame.loc[0,'plan_oil_tpd']=-1;frame.to_csv(path,index=False)
            result=cycle_service.process_hour(root,6)
            self.assertEqual(result['status'],'invalid_input')
            self.assertTrue(result['errors'])
            cycle.assert_not_called()
            self.assertTrue(list((root/'data/live/runs').glob('*.json')))

    def test_cycle_crash_is_journaled(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory, \
                patch('src.cycle_service.autonomous_cycle.run',side_effect=RuntimeError('boom')):
            root=make_project(directory)
            result=cycle_service.process_hour(root,6)
            self.assertEqual((result['status'],result['errors']),('failed',['boom']))


class ReadOnlyViewTests(unittest.TestCase):
    """The dashboard reads the agent state and never starts a calculation itself."""

    def test_states_are_pending_until_the_agent_processes_the_hour(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory, patch.dict(os.environ,{'AGENT_TOOL_BACKEND':'stub'}):
            root=make_project(directory)
            separator,telemetry,_=cycle_service.load_measurements(root)
            incidents=incident_view.opened_incidents(separator,6)
            with patch('src.autonomous_cycle.live_reasoning.generate',side_effect=AssertionError('calculation started')):
                self.assertEqual(autonomous_cycle.read_states(root,separator,telemetry,6,incidents)['INC-001']['stage'],'pending')
            cycle_service.process_hour(root,6)
            state=autonomous_cycle.read_states(root,separator,telemetry,6,incidents)['INC-001']
            self.assertEqual(state['stage'],'awaiting_human_decision')

    def test_missing_fact_is_shown_without_agent_run(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory, patch.dict(os.environ,{'AGENT_TOOL_BACKEND':'stub'}):
            root=make_project(directory)
            cycle_service.process_hour(root,6)
            separator,telemetry,_=cycle_service.load_measurements(root)
            state=autonomous_cycle.read_states(root,separator,telemetry,11,incident_view.opened_incidents(separator,11))
            self.assertEqual(state['INC-001']['stage'],'needs_data')


class RunAgentCommandTests(unittest.TestCase):
    def test_command_processes_one_hour_in_a_separate_process(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root=make_project(directory)
            completed=subprocess.run([sys.executable,str(ROOT/'tools/run_agent.py'),'--root',str(root),'--backend','stub','--once'],
                                     capture_output=True,text=True,encoding='utf-8',timeout=120)
            self.assertEqual(completed.returncode,0,completed.stderr)
            self.assertEqual(json.loads(completed.stdout.strip().splitlines()[-1])['hour'],0)
            self.assertEqual(cycle_service.clock(root)['hour'],0)

    def test_stub_backend_is_refused_before_touching_the_working_project(self):
        before=sorted(p.name for p in (ROOT/'data/live').glob('*')) if (ROOT/'data/live').exists() else []
        with patch.dict(os.environ,{'AGENT_TOOL_BACKEND':'stub'}):
            with self.assertRaises(RuntimeError):cycle_service.process_hour(ROOT,6)
            with self.assertRaises(RuntimeError):cycle_service.tick(ROOT)
        after=sorted(p.name for p in (ROOT/'data/live').glob('*')) if (ROOT/'data/live').exists() else []
        self.assertEqual(before,after)

if __name__=='__main__':
    unittest.main()
