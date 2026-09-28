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

    def test_llm_model_and_actual_cost_are_journaled(self):
        from src import tool_gateway, llm_client
        with tempfile.TemporaryDirectory() as directory:
            root=make_project(directory)
            meta={'model':'openai/gpt-4.1','seconds':1.0,'prompt_tokens':1000,'completion_tokens':50,'cost_usd':0.0024}
            with patch.dict(os.environ,{'AGENT_TOOL_BACKEND':'petex','AGENT_LLM':'openrouter:openai/gpt-4.1'}),                  patch.object(llm_client,'ask',return_value=({'ok':True},meta)), patch.object(llm_client,'api_key',return_value='k'):
                tool_gateway.start_tick(root)
                tool_gateway.ask_codex(root,'x',{},directory)
                tools=tool_gateway.finish_tick()
        self.assertEqual(tools['llm_models'],['openai/gpt-4.1'])
        self.assertEqual(tools['llm_tokens_reported'],{'prompt':1000,'completion':50})
        self.assertEqual(tools['llm_cost_usd'],0.0024)

    def test_exceeded_llm_limit_stops_and_escalates(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory, patch.dict(os.environ,{'AGENT_TOOL_BACKEND':'stub'}):
            root=make_project(directory)
            set_limits(root,llm_calls_per_incident=0,llm_calls_per_plan=1)
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
            self.assertEqual((late['overdue'],late['current_role']),(True,'инженер-моделист'))   # 3 h: overdue, still the owner
            later=escalation.open_items(root,now=start+timedelta(hours=5))[0]
            self.assertEqual(later['current_role'],'руководитель группы моделирования и оптимизации')   # after 4 h
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
            self.assertEqual([(i['subject'],i['kind'],i['current_role']) for i in items],[(FIRST,'decision','инженер-моделист')])
            cycle_service.tick(root);cycle_service.tick(root)   # 10:00 — 4 h: his head; the item is not duplicated
            items=escalation.open_items(root,agent_hour=10)
            self.assertEqual([(i['current_role'],i['overdue']) for i in items],[('руководитель группы моделирования и оптимизации',True)])

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


class FormulaAndGapTests(unittest.TestCase):
    def test_llm_limit_grows_with_open_incidents(self):
        from src import tool_gateway
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root=make_project(directory)
            tool_gateway.start_tick(root)
            try:
                tool_gateway.set_open_incidents(1)
                self.assertEqual(tool_gateway.tick_limit('llm_calls'),3)
                tool_gateway.set_open_incidents(3)
                self.assertEqual(tool_gateway.tick_limit('llm_calls'),5)
            finally:
                tool_gateway.finish_tick()

    def test_no_admissible_gap_variant_is_escalated_to_the_modelling_engineer(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory, patch.dict(os.environ,{'AGENT_TOOL_BACKEND':'stub'}):
            root=make_project(directory)
            path=root/'config/network_constraints.json'
            limits=json.loads(path.read_text(encoding='utf-8'));limits['minimum_fbhp_bar']=200.   # impossible for every variant
            path.write_text(json.dumps(limits),encoding='utf-8')
            run=run_until(root,6)
            self.assertEqual(run['incidents'][FIRST]['stage'],'conditional_network_calculated')
            items=escalation.open_items(root)
            self.assertEqual(len(items),1)
            self.assertIn('GAP: нет допустимого варианта',items[0]['reason'])
            self.assertIn('Pзаб',items[0]['reason'])
            self.assertEqual(items[0]['owner_role'],'инженер-моделист')



class GapLicenseTests(unittest.TestCase):
    def test_license_failure_waits_and_reuses_measure_sets_without_new_llm_calls(self):
        import subprocess
        from src import tool_gateway, license_retry
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory, patch.dict(os.environ,{'AGENT_TOOL_BACKEND':'stub'}):
            root=make_project(directory)
            real=tool_gateway.run_worker
            def no_license(root_,script,request,output):
                if script=='run_live_gap':
                    return subprocess.CompletedProcess([script],1,'','No OpenServer license available')
                return real(root_,script,request,output)
            with patch('src.live_planning.tool_gateway.run_worker',side_effect=no_license):
                run=run_until(root,6)
            self.assertEqual(run['incidents'][FIRST]['stage'],'waiting_license')
            self.assertEqual(escalation.open_items(root),[])
            # License is back and the retry time has passed: GAP only, the LLM is not asked again.
            license_retry.success(root)
            later=cycle_service.tick(root)
            self.assertEqual(later['tools']['llm_calls'],0)
            self.assertGreater(later['tools']['gap_runs'],0)
            self.assertEqual(later['incidents'][FIRST]['stage'],'awaiting_human_decision')


class CalculationFailureTests(unittest.TestCase):
    TRACEBACK=('Traceback (most recent call last):\n  File "tools/export_live_vlp.py", line 39, in main\n'
               'open_server.OpenServerError: Variable name was not found\n')

    def run_with_failures(self,failures):
        import subprocess
        from src import tool_gateway
        directory=tempfile.TemporaryDirectory(ignore_cleanup_errors=True);self.addCleanup(directory.cleanup)
        patcher=patch.dict(os.environ,{'AGENT_TOOL_BACKEND':'stub'});patcher.start();self.addCleanup(patcher.stop)
        root=make_project(directory.name)
        real=tool_gateway.run_worker;left=[failures]
        def failing(root_,script,request,output):
            if script=='export_live_vlp' and left[0]>0:
                left[0]-=1
                return subprocess.CompletedProcess([script],1,'',self.TRACEBACK)
            return real(root_,script,request,output)
        worker=patch('src.live_adaptation.tool_gateway.run_worker',side_effect=failing);worker.start();self.addCleanup(worker.stop)
        return root,run_until(root,6)

    def test_failed_petex_calculation_is_retried_once_without_escalation(self):
        root,run=self.run_with_failures(1)
        state=run['incidents'][FIRST]
        self.assertEqual(state['stage'],'calculation_failed')
        self.assertNotIn('Traceback',state['reason'])
        self.assertIn('повторит расчёт',state['reason'])
        self.assertEqual([i for i in escalation.open_items(root) if i.get('kind')=='agent'],[])
        later=cycle_service.tick(root)
        self.assertEqual(later['incidents'][FIRST]['stage'],'awaiting_human_decision')

    def test_second_failure_goes_to_the_modelling_engineer(self):
        root,run=self.run_with_failures(2)
        later=cycle_service.tick(root)
        state=later['incidents'][FIRST]
        self.assertEqual(state['stage'],'needs_attention')
        self.assertTrue(state['reason'].startswith('Повторный расчёт тоже не удался'))
        self.assertNotIn('Traceback',state['reason'])
        items=[i for i in escalation.open_items(root) if i.get('kind')=='agent']
        self.assertEqual(items[0]['owner_role'],'инженер-моделист')
