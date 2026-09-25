"""E4: per-tick limits, run journal counters and the escalation queue."""
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch
import pandas as pd
from src import cycle_service, escalation
from tests.support import FIRST, make_project


def set_limits(root,**values):
    path=root/'config/cycle_limits.json'
    limits=json.loads(path.read_text(encoding='utf-8'));limits.update(values)
    path.write_text(json.dumps(limits,ensure_ascii=False),encoding='utf-8')


def run_until(root,hour):
    result=None
    for _ in range(hour+1):result=cycle_service.tick(root)
    return result


class LimitTests(unittest.TestCase):
    def test_normal_tick_is_journaled_with_tool_counts(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory, patch.dict(os.environ,{'AGENT_TOOL_BACKEND':'stub'}):
            root=make_project(directory)
            run=run_until(root,6)
            self.assertEqual(run['incidents'][FIRST]['stage'],'awaiting_human_decision')
            tools=run['tools']
            # 3 LLM calls: diagnosis, tool choice, sets after screening.
            # 5 GAP runs: screening, sets, sets with compulsory W50 correction, all-capacity check, pump wash.
            self.assertEqual((tools['llm_calls'],tools['gap_runs']),(3,5))
            self.assertGreater(tools['llm_prompt_tokens_estimate'],0)
            self.assertIsNone(tools['limit_exceeded'])
            self.assertEqual(run['escalations'],[])

    def test_exceeded_llm_limit_stops_and_escalates(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory, patch.dict(os.environ,{'AGENT_TOOL_BACKEND':'stub'}):
            root=make_project(directory)
            set_limits(root,max_llm_calls=1)
            run=run_until(root,6)
            self.assertEqual(run['incidents'][FIRST]['stage'],'needs_attention')
            self.assertIn('Превышен лимит такта',run['tools']['limit_exceeded'])
            self.assertEqual(run['tools']['llm_calls'],1)
            items=escalation.open_items(root)
            self.assertEqual([i['subject'] for i in items],[FIRST])
            self.assertEqual(items[0]['current_role'],'инженер-моделист')

    def test_exceeded_gap_limit_stops_before_extra_runs(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory, patch.dict(os.environ,{'AGENT_TOOL_BACKEND':'stub'}):
            root=make_project(directory)
            set_limits(root,max_gap_runs=1)
            run=run_until(root,6)
            self.assertEqual(run['tools']['gap_runs'],1)
            self.assertEqual(run['incidents'][FIRST]['stage'],'needs_attention')

    def test_too_many_open_incidents_go_to_engineer_without_calculation(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory, patch.dict(os.environ,{'AGENT_TOOL_BACKEND':'stub'}):
            root=make_project(directory)
            set_limits(root,max_open_incidents=1)
            run_until(root,14)
            run=cycle_service.tick(root)  # 15:00, second incident opens
            self.assertEqual(run['status'],'too_many_incidents')
            self.assertEqual(run['tools']['llm_calls'],0)
            self.assertEqual([i['subject'] for i in escalation.open_items(root) if i['kind']=='agent'],['Цикл агента'])


class EscalationQueueTests(unittest.TestCase):
    def test_same_problem_is_queued_once_and_moves_to_backup_after_deadline(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root=make_project(directory)
            start=datetime(2026,9,24,9,0)
            first=escalation.raise_item(root,'INC-X','причина','run-1',6,now=start)
            again=escalation.raise_item(root,'INC-X','причина','run-2',7,now=start+timedelta(hours=1))
            self.assertEqual(first['id'],again['id'])
            self.assertEqual(first['deadline'],'2026-09-24T11:00')
            late=escalation.open_items(root,now=start+timedelta(hours=3))[0]
            self.assertTrue(late['overdue'])
            self.assertEqual(late['current_role'],'руководитель группы моделирования и оптимизации')
            escalation.close(root,first['id'],'перезапущен и прошёл')
            self.assertEqual(escalation.open_items(root),[])

    def test_invalid_input_is_escalated(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root=make_project(directory)
            path=root/'data/live/separator.csv'
            frame=pd.read_csv(path);frame.loc[0,'plan_oil_tpd']=-1;frame.to_csv(path,index=False)
            run=cycle_service.process_hour(root,6)
            self.assertEqual(run['status'],'invalid_input')
            self.assertEqual(len(run['escalations']),1)


if __name__=='__main__':
    unittest.main()


class DecisionWaitTests(unittest.TestCase):
    def test_unanswered_proposal_is_escalated_to_the_field_technologist(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory, patch.dict(os.environ,{'AGENT_TOOL_BACKEND':'stub'}):
            root=make_project(directory)
            run_until(root,7)   # ready at 06:00, nobody decides; 07:00 is 1 h
            self.assertEqual(escalation.open_items(root),[])
            cycle_service.tick(root)   # 08:00 — 2 h without a decision: field technologist
            items=escalation.open_items(root,agent_hour=8)
            self.assertEqual([(i['subject'],i['kind'],i['current_role']) for i in items],[(FIRST,'decision','ведущий технолог по добыче')])
            cycle_service.tick(root);cycle_service.tick(root)   # 10:00 — 4 h: his head; the item is not duplicated
            items=escalation.open_items(root,agent_hour=10)
            self.assertEqual([(i['current_role'],i['overdue']) for i in items],[('начальник технологического отдела ЦДНГ',True)])

    def test_return_with_comment_restarts_the_decision_wait(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory, patch.dict(os.environ,{'AGENT_TOOL_BACKEND':'stub'}):
            from src import incident_lifecycle
            root=make_project(directory)
            run_until(root,7)
            incident_lifecycle.record_decision(root/'data/live/lifecycle.json',FIRST,'На доработке','Не трогать W13',None,'test')
            cycle_service.tick(root);cycle_service.tick(root)   # 08:00 and 09:00: only 1 h since the new version
            self.assertEqual(escalation.open_items(root),[])

    def test_daily_budget_stops_repeated_recalculation(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory, patch.dict(os.environ,{'AGENT_TOOL_BACKEND':'stub'}):
            from src import incident_lifecycle
            root=make_project(directory)
            set_limits(root,max_llm_calls_per_day=5)
            run=None
            for _ in range(10):
                run=cycle_service.tick(root)
                if run['incidents'].get(FIRST,{}).get('stage')=='awaiting_human_decision':
                    incident_lifecycle.record_decision(root/'data/live/lifecycle.json',FIRST,'На доработке',f"комментарий {run['hour']}",None,'test')
                if run['tools'].get('limit_exceeded'):break
            self.assertIn('суточный бюджет',run['tools']['limit_exceeded'])
            self.assertEqual(run['incidents'][FIRST]['stage'],'needs_attention')

