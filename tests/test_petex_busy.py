"""PetEx opened by the engineer is a temporary unavailability, not a failure for escalation."""
import os
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from src import cycle_service, escalation, license_retry, tool_gateway
from tests.support import FIRST, make_project

BUSY=subprocess.CompletedProcess(['worker'],1,'','RuntimeError: PROSPER уже открыт; чужая рабочая модель не переключается')


class PetexBusyTests(unittest.TestCase):
    def test_busy_message_is_a_wait_state(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            state=license_retry.failure(make_project(directory),BUSY.stderr)
            self.assertEqual(state['stage'],'waiting_petex')

    def test_agent_waits_while_petex_is_open_and_continues_after_it_is_closed(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory, patch.dict(os.environ,{'AGENT_TOOL_BACKEND':'stub'}):
            root=make_project(directory)
            for _ in range(6):cycle_service.tick(root)
            real_worker=tool_gateway.run_worker
            with patch('src.live_adaptation.tool_gateway.run_worker',return_value=BUSY), \
                    patch('src.license_retry.petex_running',return_value=True):
                busy=cycle_service.tick(root)  # 06:00
            self.assertEqual(busy['incidents'][FIRST]['stage'],'waiting_petex')
            self.assertEqual(busy['escalations'],[])
            self.assertEqual(escalation.open_items(root),[])
            with patch('src.license_retry.petex_running',return_value=False):
                later=cycle_service.process_hour(root,6)  # the engineer closed PetEx
            self.assertEqual(later['incidents'][FIRST]['stage'],'awaiting_human_decision')
            self.assertIs(tool_gateway.run_worker,real_worker)


if __name__=='__main__':
    unittest.main()
