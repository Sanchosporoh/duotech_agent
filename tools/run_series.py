"""Five-run series of the pattern on real PetEx and a real LLM (course table of five runs).

Criterion and inputs: course/five_runs/criterion.md (recorded before the runs).
Runs in the project itself (PetEx workers use the project runtime copies), restores the
training-day measurements afterwards. Nothing is approved: every input is built from data.
Run: python tools/run_series.py --llm openrouter:openai/gpt-4.1 --label gpt-4.1
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO))
W22,W27,W50='W_BEL_22_TLBB','W_BEL_27_TLBB','W_BEL_50_TLBB'
# Loss of the W22 stop in the training day at 15:00 (separator 263.539 -> 233.987 t/d, water 20.582 -> 19.438).
W22_OIL,W22_WATER=29.552,1.144


def move_w22_stop(folder,hour):
    """Build a day where W22 stops at `hour` (< 15) instead of 15:00."""
    import pandas as pd
    separator=pd.read_csv(folder/'separator.csv')
    selected=(separator.hour>=hour)&(separator.hour<15)
    separator.loc[selected,'separator_oil_tpd']-=W22_OIL
    separator.loc[selected,'separator_water_m3d']-=W22_WATER
    separator.to_csv(folder/'separator.csv',index=False)
    telemetry=pd.read_csv(folder/'telemetry.csv')
    stopped=telemetry[(telemetry.well_id==W22)&(telemetry.hour==15)].iloc[0]
    telemetry.loc[(telemetry.well_id==W22)&(telemetry.hour>=hour)&(telemetry.hour<15),'frequency_hz']=0.
    if telemetry[(telemetry.well_id==W22)&(telemetry.hour==hour)].empty:
        row=stopped.copy();row['hour']=hour;row['timestamp']=f'2026-09-14 {hour:02d}:00:00'
        telemetry=pd.concat([telemetry,row.to_frame().T]).sort_values(['hour','well_id'])
    telemetry.to_csv(folder/'telemetry.csv',index=False)


# (number, day variant: None or stop hour of W22, incident hour, main cause, stopped well)
RUNS=[(1,None,6,W27,None),(2,None,15,W22,W22),(3,None,18,W50,W22),(4,3,3,W22,W22),(5,10,10,W22,W22)]


def judge(root,run,hour,cause,stopped):
    from src import autonomous_cycle, cycle_service, escalation, incident_view
    separator,telemetry,_=cycle_service.load_measurements(root)
    states=autonomous_cycle.read_states(root,separator,telemetry,hour,incident_view.opened_incidents(separator,hour))
    open_states=[s for s in states.values() if s.get('stage')!='approved_for_execution']
    candidates={w for s in open_states for h in (s.get('hypotheses') or {}).get('hypotheses',[]) for w in h['candidate_wells']}
    ready=[s for s in open_states if s.get('stage')=='awaiting_human_decision' and s.get('recommendation',{}).get('ready')]
    selected=ready[0]['recommendation']['selected'] if ready else {}
    regulated={w['well_id'] for phase in selected.get('phases',[]) for w in phase.get('wells',[])
               if w.get('control_optimised') is not None and w.get('control_optimised')!=w.get('control_actual')}
    agent_failures=[i for i in escalation.load(root).get('items',[]) if i.get('run_id')==run['run_id'] and i.get('kind','agent')=='agent']
    checks={'1 готовое предложение':bool(ready),
            '2 главная причина среди гипотез':cause in candidates,
            '3 валидатор и ограничения GAP':bool(ready),
            '4 остановленная скважина не регулируется':stopped is None or (bool(ready) and stopped not in regulated),
            '5 нет потолка и сбоя агента':not run['tools'].get('limit_exceeded') and not agent_failures}
    return checks,{'stages':{k:s.get('stage') for k,s in states.items()},'candidates':sorted(candidates),
                   'recommendation':selected.get('title'),'expected_deficit_t':selected.get('expected_deficit_t'),
                   'regulated_wells':sorted(regulated)}


def price(run):
    tools=run.get('tools',{})
    reported=tools.get('llm_tokens_reported')
    return {'llm_calls':tools.get('llm_calls'),'llm_cost_usd':tools.get('llm_cost_usd'),
            'tokens':reported or {'prompt_estimate':tools.get('llm_prompt_tokens_estimate')},
            'prosper_runs':tools.get('prosper_runs'),'gap_runs':tools.get('gap_runs'),'seconds':run.get('duration_seconds'),
            'models':tools.get('llm_models')}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--llm',required=True,help='codex or openrouter:<model>')
    parser.add_argument('--label',required=True)
    args=parser.parse_args()
    if args.llm=='codex':os.environ.pop('AGENT_LLM',None)
    else:os.environ['AGENT_LLM']=args.llm
    os.environ['AGENT_TOOL_BACKEND']='petex'
    from src import cycle_service, license_retry
    from src.reset_decisions import reset
    if license_retry.petex_running():raise SystemExit('PetEx открыт: серия не запускается, чужие окна не закрываются')
    live=REPO/'data/live';base=live/'series_base'
    base.mkdir(exist_ok=True)
    for name in ('separator.csv','telemetry.csv'):shutil.copy2(live/name,base/name)
    results=[];day=object();journal={}
    try:
        for number,variant,hour,cause,stopped in RUNS:
            if variant!=day:
                for name in ('separator.csv','telemetry.csv'):shutil.copy2(base/name,live/name)
                if variant is not None:move_w22_stop(live,variant)
                # Fresh only for the first day: identical earlier hours of a variant reuse the saved calculations.
                reset(REPO,fresh=number==1)
                day=variant;journal={}
            while cycle_service.clock(REPO).get('hour',-1)<hour:
                run=cycle_service.tick(REPO);journal[run['hour']]=run
                print(f"  {run['hour']:02d}:00 {run['status']} LLM {run['tools'].get('llm_calls')} GAP {run['tools'].get('gap_runs')}",flush=True)
            run=journal[hour]
            checks,observed=judge(REPO,run,hour,cause,stopped)
            results.append({'number':number,'variant_w22_stop':variant,'hour':hour,'run_id':run['run_id'],
                            'success':all(checks.values()),'checks':checks,'observed':observed,'price':price(run)})
            print(number,'успешно' if results[-1]['success'] else 'НЕТ',checks,flush=True)
    finally:
        for name in ('separator.csv','telemetry.csv'):shutil.copy2(base/name,live/name)
        reset(REPO)
    successes=sum(r['success'] for r in results)
    costs=[r['price']['llm_cost_usd'] for r in results]
    total=round(sum(c or 0 for c in costs),4) if all(c is not None for c in costs) else None
    summary={'llm':args.llm,'runs':len(results),'successes':successes,'failure_share':f'{len(results)-successes} из {len(results)}',
             'llm_cost_usd_total':total,'cost_per_success_usd':round(total/successes,4) if total is not None and successes else None,
             'criterion':'course/five_runs/criterion.md'}
    out=REPO/'course/five_runs'/f'{args.label}.json'
    out.write_text(json.dumps({'summary':summary,'runs':results},ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False))


if __name__=='__main__':
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    main()
