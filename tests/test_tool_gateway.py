import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import pandas as pd
from src import autonomous_cycle, incident_view, tool_gateway
from src.calculation_dependencies import fingerprints
from tests.support import FIRST, ROOT, make_project


def measurements(root):
    return pd.read_csv(root/'data/live/separator.csv'),pd.read_csv(root/'data/live/telemetry.csv')


class ToolGatewayTests(unittest.TestCase):
    def test_stub_backend_is_refused_in_the_working_project(self):
        with patch.dict(os.environ,{'AGENT_TOOL_BACKEND':'stub'}):
            with self.assertRaises(RuntimeError):
                tool_gateway.run_worker(ROOT,'run_live_gap',ROOT/'request.json',ROOT/'result.json')

    def test_unknown_backend_is_an_error(self):
        with patch.dict(os.environ,{'AGENT_TOOL_BACKEND':'demo'}):
            with self.assertRaises(ValueError):tool_gateway.backend()

    def test_stub_and_real_results_do_not_share_cache_keys(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root=Path(directory)
            with patch.dict(os.environ,{'AGENT_TOOL_BACKEND':'petex'}):real=fingerprints(root)
            with patch.dict(os.environ,{'AGENT_TOOL_BACKEND':'stub'}):stub=fingerprints(root)
            self.assertNotEqual(real,stub)


class StubCycleTests(unittest.TestCase):
    """The whole chain runs without Codex and PetEx; every tool result is marked as a stub."""

    def run_hour(self,root,hour):
        separator,telemetry=measurements(root)
        return autonomous_cycle.run(root,separator,telemetry,hour,incident_view.opened_incidents(separator,hour))

    def test_first_incident_reaches_engineer_decision_without_external_processes(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory, patch.dict(os.environ,{'AGENT_TOOL_BACKEND':'stub'}), \
                patch('subprocess.run',side_effect=AssertionError('external process started')) as process:
            root=make_project(directory)
            state=self.run_hour(root,6)[FIRST]
            self.assertEqual(state['stage'],'awaiting_human_decision',state.get('error'))
            self.assertTrue(state['recommendation']['ready'])
            process.assert_not_called()
            for alternative in state['plan']['network']['alternatives']:
                self.assertEqual(alternative['tool_backend'],'stub')
            self.assertEqual(state['adaptation'][0]['tool_backend'],'stub')

    def test_missing_current_fact_stops_before_any_tool(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory, patch.dict(os.environ,{'AGENT_TOOL_BACKEND':'stub'}), \
                patch('src.tool_gateway.ask_codex') as codex:
            root=make_project(directory)
            self.assertEqual(self.run_hour(root,11)[FIRST]['stage'],'needs_data')
            codex.assert_not_called()

    def test_incomplete_well_conditions_block_network_state(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory, patch.dict(os.environ,{'AGENT_TOOL_BACKEND':'stub'}):
            root=make_project(directory,conditions=False)
            state=self.run_hour(root,6)[FIRST]
            self.assertEqual(state['stage'],'awaiting_model_state')
            self.assertFalse(state['recommendation']['ready'])


if __name__=='__main__':
    unittest.main()
