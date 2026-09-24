"""One hourly agent cycle, independent of the user interface.

The scheduler (tools/run_agent.py) and the dashboard button call the same
functions. The dashboard itself only reads what the agent has written.
"""
from datetime import datetime
import json
import time
import uuid
import pandas as pd
from src import autonomous_cycle, escalation, incident_lifecycle, incident_view, live_execution, live_monitor, tool_gateway
from src.live_reasoning import save

CONDITION_COLUMNS=['whp_bara','water_cut_pct','gor_m3m3']
LAST_HOUR=23


def folder(root):
    return root/'data'/'live'


def load_measurements(root):
    """Read and validate input CSV, then add effects of approved local actions."""
    paths=[folder(root)/'separator.csv',folder(root)/'telemetry.csv']
    missing=[p.name for p in paths if not p.exists()]
    if missing:return None,None,['Нет входных измерений: '+', '.join(missing)]
    try:
        separator,telemetry=(pd.read_csv(p) for p in paths)
    except (OSError,ValueError) as exc:
        return None,None,['Не удалось прочитать измерения: '+str(exc)]
    errors=live_monitor.validate_inputs(separator,telemetry)
    for label,frame in [('Сепаратор',separator),('Телеметрия',telemetry)]:
        if 'timestamp' not in frame:
            errors.append(label+': отсутствует время измерения timestamp')
        else:
            frame['timestamp']=pd.to_datetime(frame.timestamp,errors='coerce')
            if frame.timestamp.isna().any():errors.append(label+': некорректное время измерения')
    if errors:return None,None,errors
    separator,telemetry=live_execution.apply(root,separator,telemetry)
    for column in CONDITION_COLUMNS:
        if column not in telemetry:telemetry[column]=float('nan')
    return separator,telemetry,[]


def clock(root):
    path=folder(root)/'clock.json'
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}


def set_clock(root,hour,mode):
    save(folder(root)/'clock.json',{'hour':hour,'mode':mode,'updated_at':datetime.now().isoformat(timespec='seconds')})


def reset_clock(root):
    path=folder(root)/'clock.json'
    if path.exists():path.unlink()


def process_hour(root,hour):
    """Process all incidents visible at this hour and write a run journal entry."""
    tool_gateway.guard(root)
    started=time.monotonic()
    run={'run_id':datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6],'hour':hour,
         'started_at':datetime.now().isoformat(timespec='seconds'),'tool_backend':tool_gateway.backend(),'incidents':{}}
    limits=_limits(root)
    tool_gateway.start_tick(root)
    try:
        separator,telemetry,errors=load_measurements(root)
        if errors:
            run.update(status='invalid_input',errors=errors)
        else:
            incidents=incident_view.opened_incidents(separator,hour)
            active=_active(root,incidents)
            if incidents.empty:
                run.update(status='no_incidents')
            elif limits.get('max_open_incidents') is not None and len(active)>limits['max_open_incidents']:
                run.update(status='too_many_incidents',errors=[f"Одновременно открыто {len(active)} инцидентов при лимите {limits['max_open_incidents']}: автоматический разбор остановлен, нужен инженер."])
            else:
                try:
                    states=autonomous_cycle.run(root,separator,telemetry,hour,incidents)
                    run['incidents']={name:{'stage':s.get('stage'),'recompute':s.get('recompute',{}).get('level'),'reason':s.get('reason') or s.get('error') or s.get('plan',{}).get('reason')}
                                      for name,s in states.items()}
                    run['status']='processed'
                except Exception as exc:  # the journal must record any crash of the cycle
                    run.update(status='failed',errors=[str(exc)])
    finally:
        run['tools']=tool_gateway.finish_tick()
    run['duration_seconds']=round(time.monotonic()-started,3)
    run['slow']=limits.get('slow_tick_seconds') is not None and run['duration_seconds']>limits['slow_tick_seconds']
    run['finished_at']=datetime.now().isoformat(timespec='seconds')
    run['escalations']=[item['id'] for item in _escalate(root,run)]
    save(folder(root)/'runs'/f"{run['run_id']}.json",run)
    return run


def _limits(root):
    path=root/'config'/'cycle_limits.json'
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}


def _active(root,incidents):
    lifecycle=incident_lifecycle.load(folder(root)/'lifecycle.json')['incidents']
    return [i for i in incidents.incident_id if lifecycle.get(i,{}).get('stage') not in ('closed_rejected','approved_for_execution')]


def _escalate(root,run):
    """What the agent cannot resolve by itself goes to the engineer queue with a deadline."""
    if not (root/'config'/'escalation.json').exists():return []
    items=[]
    if run['status'] in ('failed','invalid_input','too_many_incidents'):
        items.append(escalation.raise_item(root,'Цикл агента','; '.join(run.get('errors',[])),run['run_id'],run['hour']))
    for name,state in run['incidents'].items():
        if state['stage']=='needs_attention':
            items.append(escalation.raise_item(root,name,state.get('reason') or 'Расчёт остановлен',run['run_id'],run['hour']))
    items+=_decision_waits(root,run)
    return items


def _decision_waits(root,run):
    """A ready proposal that nobody approved or returned within the deadline goes to the field technologist."""
    policy=json.loads((root/'config'/'escalation.json').read_text(encoding='utf-8'))
    if 'decision_response_hours' not in policy:return []
    path=folder(root)/'decision_wait.json'
    waits=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    items=[]
    for name,state in run['incidents'].items():
        if state['stage']!='awaiting_human_decision':
            waits.pop(name,None)  # decided, recalculating or closed: the wait starts again
            continue
        since=waits.setdefault(name,run['hour'])
        if run['hour']-since>=policy['decision_response_hours']:
            items.append(escalation.raise_item(root,name,f"Готовое предложение с {since:02d}:00 ждёт решения инженера дольше {policy['decision_response_hours']} ч",
                                               run['run_id'],run['hour'],kind='decision'))
    save(path,waits)
    return items


def tick(root,mode='simulated',now=None):
    """Advance the agent clock and process the hour.

    simulated: one call = one new hour of measurements (demo with accelerated time);
    wall: the hour of the current local time; repeated calls reprocess it cheaply from cache.
    """
    tool_gateway.guard(root)
    if mode=='wall':
        hour=(now or datetime.now()).hour
    elif mode=='simulated':
        previous=clock(root).get('hour')
        if previous is not None and previous>=LAST_HOUR:
            return {'status':'day_finished','hour':previous}
        hour=0 if previous is None else previous+1
    else:
        raise ValueError('Неизвестный режим часов: '+mode)
    set_clock(root,hour,mode)
    return process_hour(root,hour)


def recent_runs(root,limit=10):
    paths=sorted((folder(root)/'runs').glob('*.json'),reverse=True)[:limit]
    return [json.loads(p.read_text(encoding='utf-8')) for p in paths]
