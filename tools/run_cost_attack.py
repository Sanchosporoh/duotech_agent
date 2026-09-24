"""Cost attack on a project copy with tool stubs: the engineer returns the proposal
with a new comment every hour, so every tick asks for a full recalculation.

Shows where the control layer stops the agent. Result: course/cost_attack.json.
Run: python tools/run_cost_attack.py
"""
import json
import os
from pathlib import Path
import sys
import tempfile

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO))
os.environ['AGENT_TOOL_BACKEND']='stub'


def main():
    from tests.support import make_project, FIRST
    from src import cycle_service, escalation, incident_lifecycle
    limits=json.loads((REPO/'config/cycle_limits.json').read_text(encoding='utf-8'))
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
        root=make_project(directory)
        hours=[];stopped=None;total=0
        for _ in range(24):
            run=cycle_service.tick(root)
            if run.get('status')=='day_finished':break
            tools=run.get('tools',{})
            total+=tools.get('llm_calls',0) or 0
            state=run['incidents'].get(FIRST,{})
            hours.append({'hour':run['hour'],'llm_calls':tools.get('llm_calls',0),'llm_calls_today':total,
                          'stage':state.get('stage'),'limit':tools.get('limit_exceeded')})
            if tools.get('limit_exceeded') and stopped is None:
                stopped={'hour':run['hour'],'message':tools['limit_exceeded']}
            if state.get('stage')=='awaiting_human_decision':
                # The attack: a new comment every hour forces a full recalculation.
                incident_lifecycle.record_decision(root/'data/live/lifecycle.json',FIRST,'На доработке',
                    f"Пересчитать с ограничением №{run['hour']}",None,'cost attack')
        result={'scenario':'Возврат предложения с новым комментарием каждый час (полный пересчёт каждый такт)',
                'limits':{k:limits[k] for k in ('max_llm_calls','max_llm_calls_per_day','max_gap_runs','max_gap_runs_per_day')},
                'stopped':stopped,'llm_calls_total':total,'hours':hours,
                'escalations':[{k:i[k] for k in ('subject','reason','owner_role','hour')} for i in escalation.open_items(root)]}
    out=REPO/'course/cost_attack.json'
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'stopped':stopped,'llm_calls_total':total,'escalations':len(result['escalations'])},ensure_ascii=False))


if __name__=='__main__':
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    main()
