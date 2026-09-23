"""Run reasoning and available checks once per observed snapshot, independent of UI selection."""
from datetime import datetime
import json
import math
from src import live_reasoning, live_checks, incident_lifecycle, live_planning, live_adaptation, restoration_planning, proposal_selection, license_retry
from src.cycle_lock import acquire
from src.calculation_dependencies import fingerprints


def fresh_separator_fact(separator,hour):
    current=separator[separator.hour==hour]
    if len(current)!=1:return False
    try:
        oil=float(current.iloc[0]['separator_oil_tpd'])
        plan=float(current.iloc[0]['plan_oil_tpd'])
        return math.isfinite(oil) and oil>=0 and math.isfinite(plan) and plan>0
    except (KeyError,TypeError,ValueError):return False


NO_FRESH_FACT={'stage':'needs_data','reason':'Нет свежего корректного факта и плана сепаратора на текущий час. Диагностика и оптимизация ожидают измерений.'}


def _snapshot(row,life,separator,telemetry,hour,dependencies):
    version=life['versions'][-1]
    incident={'incident_id':row.incident_id,'opened_hour':int(row.opened_hour),'observed_loss_tpd':float(row.observed_loss_tpd)}
    return live_reasoning.snapshot(separator,telemetry,hour,incident,version.get('human_comment',''),version['version'],dependencies)


def _execution_path(root,key):
    return root/'data'/'live'/'executions'/f'proposal_v4_{key}.json'


def read_states(root, separator, telemetry, hour, incidents):
    """What the agent has already written for this snapshot; never starts a calculation."""
    lifecycle=incident_lifecycle.load(root/'data'/'live'/'lifecycle.json')['incidents']
    dependencies=fingerprints(root) if not incidents.empty else {}
    statuses={}
    for _,row in incidents.iterrows():
        life=lifecycle.get(row.incident_id)
        if life is None:
            statuses[row.incident_id]={'stage':'pending','reason':'Агент ещё не обработал этот инцидент.'}
            continue
        if life['stage'] in ('closed_rejected','approved_for_execution'):
            statuses[row.incident_id]={'stage':life['stage']}
            continue
        if not fresh_separator_fact(separator,hour):
            statuses[row.incident_id]=dict(NO_FRESH_FACT,incident_id=row.incident_id)
            continue
        _,key=_snapshot(row,life,separator,telemetry,hour,dependencies)
        path=_execution_path(root,key)
        waiting=license_retry.blocked(root)
        if waiting and not path.exists():
            statuses[row.incident_id]=dict(waiting,incident_id=row.incident_id)
            continue
        statuses[row.incident_id]=json.loads(path.read_text(encoding='utf-8')) if path.exists() else             {'stage':'pending','fingerprint':key,'reason':'Агент ещё не обработал текущие данные этого часа или новую версию после доработки.'}
    return statuses


def run(root, separator, telemetry, hour, incidents):
    with acquire(root) as locked:
        if not locked:
            return {row.incident_id:{'stage':'running','reason':'Этот проект уже обрабатывается в другой сессии. Ожидаем завершения расчёта.'} for _,row in incidents.iterrows()}
        return _run(root,separator,telemetry,hour,incidents)


def _run(root, separator, telemetry, hour, incidents):
    folder=root/'data'/'live'
    statuses={}
    dependencies=fingerprints(root) if not incidents.empty else {}
    for _,row in incidents.iterrows():
        identity=row.incident_id
        life=incident_lifecycle.ensure_incident(folder/'lifecycle.json',identity,'Причина определяется по измерениям')
        if life['stage']=='closed_rejected':
            statuses[identity]={'stage':'closed_rejected'}
            continue
        if life['stage']=='approved_for_execution':
            statuses[identity]={'stage':'approved_for_execution'}
            continue
        if not fresh_separator_fact(separator,hour):
            statuses[identity]=dict(NO_FRESH_FACT,incident_id=identity)
            continue
        context,key=_snapshot(row,life,separator,telemetry,hour,dependencies)
        response=folder/'reasoning'/f'{key}.json'
        execution=_execution_path(root,key)
        execution.parent.mkdir(parents=True,exist_ok=True)
        waiting=license_retry.blocked(root)
        if waiting:
            statuses[identity]=dict(waiting,incident_id=identity)
            continue
        if execution.exists():
            previous=json.loads(execution.read_text(encoding='utf-8'))
            if previous['stage']=='running':
                with acquire(root,'petex.lock') as free:
                    if not free:
                        statuses[identity]=dict(previous,reason='Дочерний расчёт PetEx ещё работает. Ожидаем завершения.')
                        continue
                if not response.exists():
                    previous.update(stage='needs_attention',reason='Предыдущий цикл прерван до сохранения ответа Codex. Автоповтор не запущен: состояние прежнего вызова неизвестно.')
                    live_reasoning.save(execution,previous)
            if previous['stage']=='needs_attention':
                statuses[identity]=previous
                continue  # UI reruns must not cause an endless retry loop
        state={'fingerprint':key,'incident_id':identity,'stage':'running','started_at':datetime.now().isoformat()}
        live_reasoning.save(execution,state)
        try:
            if response.exists():
                result=json.loads(response.read_text(encoding='utf-8'))
            else:
                result=live_reasoning.generate(root,context,key)
                live_reasoning.save(response,result)
            checks=live_checks.execute(root,context,result['answer'])
            adaptation=live_adaptation.run(root,context,key,result['answer'])
            model_state=live_adaptation.prepare_lifts(root,context,adaptation)
            plan=live_planning.prepare(root,context,key,result['answer'],checks,model_state)
            if model_state.get('ready') and 'network' in plan:
                plan['restoration_forecast']=restoration_planning.prepare(root,context,key,plan,model_state)
            recommendation=proposal_selection.select(context,plan)
            state.update(stage=plan['stage'],checks=checks,plan=plan,adaptation=adaptation,model_state=model_state,
                         recommendation=recommendation,
                         next_step='Наборы мероприятий требуют расчёта на актуальной ИМА; исполнение не разрешено')
            if recommendation.get('ready'):
                state.update(stage='awaiting_human_decision',next_step='Утвердить лучший допустимый вариант либо вернуть с комментарием')
            if license_retry.state(root).get('stage')=='waiting_license':
                state.update(license_retry.state(root))
        except Exception as exc:
            state.update(stage='needs_attention',error=str(exc))
        live_reasoning.save(execution,state)
        if state.get('recommendation',{}).get('ready') and life['stage']=='awaiting_revision_calculation':
            incident_lifecycle.complete_revision(folder/'lifecycle.json',identity,execution,{'comparison':execution},state['recommendation']['selected']['title'],'Актуальные варианты рассчитаны; ожидается решение')
        statuses[identity]=state
    return statuses
