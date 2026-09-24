"""Run reasoning and available checks once per observed snapshot, independent of UI selection."""
from datetime import datetime
import hashlib
import json
import math
from src import live_reasoning, live_checks, incident_lifecycle, live_planning, live_adaptation, restoration_planning, proposal_selection, license_retry, recompute_policy
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
    """Diagnose each open incident, then build one field-wide compensation plan.

    The separator deficit belongs to the field, not to one incident: several
    incidents share one plan, so the same shortfall is never compensated twice.
    While incidents wait for a decision, the recompute level (full / network /
    none) compares the new hour with the last full calculation.
    """
    folder=root/'data'/'live'
    statuses={}
    dependencies=fingerprints(root) if not incidents.empty else {}
    pending=[]  # (identity, life, context, key, execution, response)
    for _,row in incidents.iterrows():
        identity=row.incident_id
        life=incident_lifecycle.ensure_incident(folder/'lifecycle.json',identity,'Причина определяется по измерениям')
        if life['stage'] in ('closed_rejected','approved_for_execution'):
            statuses[identity]={'stage':life['stage']}
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
                if not response.exists() and previous.get('recompute',{}).get('level')=='full':
                    previous.update(stage='needs_attention',reason='Предыдущий цикл прерван до сохранения ответа Codex. Автоповтор не запущен: состояние прежнего вызова неизвестно.')
                    live_reasoning.save(execution,previous)
            if previous['stage']=='needs_attention':
                statuses[identity]=previous
                continue  # repeated ticks must not cause an endless retry loop
        pending.append((identity,life,context,key,execution,response))
    if not pending:
        return statuses
    policy=recompute_policy.load(root)
    current=recompute_policy.signature(separator,telemetry,hour,[p[0] for p in pending],
        {p[0]:p[2].get('engineer_comment','') for p in pending},
        hashlib.sha256(json.dumps(dependencies,sort_keys=True).encode()).hexdigest())
    basis_path=folder/'field_basis.json'
    basis=json.loads(basis_path.read_text(encoding='utf-8')) if basis_path.exists() else None
    level,reasons=recompute_policy.classify(policy,basis,current)
    if level!='full' and not basis.get('plan',{}).get('proposal'):
        level,reasons='full',['Прежний полный расчёт не дал наборов мероприятий']
    if level=='none' and not basis['plan'].get('network'):
        level,reasons='network',['Прежний полный расчёт не дал результата сети']
    recompute={'level':level,'reasons':reasons,'basis_hour':current['hour'] if level=='full' else basis['hour']}
    active=[]  # (identity, life, context, key, execution, state, diagnosis)
    for identity,life,context,key,execution,response in pending:
        state={'fingerprint':key,'incident_id':identity,'stage':'running','started_at':datetime.now().isoformat(),'recompute':recompute}
        live_reasoning.save(execution,state)
        try:
            if level!='full':
                # Nothing new about the wells: keep the diagnosis of the last full calculation.
                diagnosis=basis['diagnosis'][identity]
                result={'answer':diagnosis['answer']}
                state.update(checks=diagnosis['checks'],adaptation=diagnosis['adaptation'],diagnosis_hour=basis['hour'])
            else:
                if response.exists():
                    result=json.loads(response.read_text(encoding='utf-8'))
                else:
                    result=live_reasoning.generate(root,context,key)
                    live_reasoning.save(response,result)
                state.update(checks=live_checks.execute(root,context,result['answer']),
                             adaptation=live_adaptation.run(root,context,key,result['answer']))
            state['hypotheses']=result['answer']
            active.append((identity,life,context,key,execution,state,result['answer']))
        except Exception as exc:
            state.update(stage='needs_attention',error=str(exc))
            live_reasoning.save(execution,state)
            statuses[identity]=state
    if not active:
        return statuses
    reuse=None if level=='full' else dict(basis['plan'],level=level,model_state=basis['model_state'])
    field=_field_plan(root,hour,active,failed=[i for i,s in statuses.items() if s.get('stage')=='needs_attention'],reuse=reuse)
    field['recompute']=recompute
    _update_basis(basis_path,basis,current,level,active,field)
    for identity,life,context,key,execution,state,_ in active:
        state.update({name:field[name] for name in ('stage','plan','model_state','recommendation','next_step','error','reason') if name in field})
        state['field_plan']={'key':field['key'],'incidents':field['incidents']}
        if license_retry.state(root).get('stage')=='waiting_license':
            state.update(license_retry.state(root))
        live_reasoning.save(execution,state)
        if state.get('recommendation',{}).get('ready') and life['stage']=='awaiting_revision_calculation':
            incident_lifecycle.complete_revision(folder/'lifecycle.json',identity,execution,{'comparison':execution},state['recommendation']['selected']['title'],'Актуальные варианты рассчитаны; ожидается решение')
        statuses[identity]=state
    return statuses


def _update_basis(path,basis,current,level,active,field):
    """Remember the last full calculation; a GAP-only recompute refreshes its network part."""
    plan=field.get('plan',{})
    if field.get('stage')=='needs_attention' or not plan.get('proposal'):return
    kept={name:plan[name] for name in ('proposal','network','capacity_check','restoration_forecast') if name in plan}
    if level=='full':
        basis=dict(current,diagnosis={i[0]:{'answer':i[6],'checks':i[5]['checks'],'adaptation':i[5]['adaptation']} for i in active},
                   plan=kept,model_state=field.get('model_state'))
    elif level=='network':
        basis=dict(basis,controls=current['controls'],water_m3d=current['water_m3d'],plan=kept)
    else:
        return
    live_reasoning.save(path,basis)


def _field_plan(root,hour,active,failed,reuse=None):
    """One compensation plan for all incidents that are open at this hour."""
    identities=[item[0] for item in active]
    key=hashlib.sha256(json.dumps(sorted(item[3] for item in active)).encode()).hexdigest()
    field={'key':key,'incidents':identities,'hour':hour}
    if failed:
        field.update(stage='needs_attention',recommendation={'ready':False,'reason':'Диагностика не завершена: '+', '.join(failed)},
                     reason='Общий план компенсации не строится, пока не завершена диагностика всех открытых инцидентов: '+', '.join(failed))
        return field
    # All snapshots share the measurements of this hour; they differ only in incident and comment.
    context=dict(active[0][2])
    context.pop('incident',None)
    context['incidents']=[item[2]['incident'] for item in active]
    context['engineer_comment']=' | '.join(f"{item[0]}: {item[2]['engineer_comment']}" for item in active if item[2].get('engineer_comment'))
    answer={'assessment':' '.join(item[6].get('assessment','') for item in active),
            'hypotheses':[h for item in active for h in item[6]['hypotheses']]}
    checks=[row for item in active for row in item[5]['checks']]
    adaptation=list({fit['well_id']:fit for item in active for fit in item[5]['adaptation']}.values())
    try:
        model_state=reuse['model_state'] if reuse else live_adaptation.prepare_lifts(root,context,adaptation)
        plan=live_planning.prepare(root,context,key,answer,checks,model_state,reuse=reuse)
        previous=(reuse or {}).get('restoration_forecast',{})
        if reuse and reuse['level']=='none' and previous.get('network_result') and 'network' in plan:
            plan['restoration_forecast']=restoration_planning.forecast(context,plan,previous['measure'],previous['well_id'],previous['network_result'])
        elif model_state.get('ready') and 'network' in plan:
            plan['restoration_forecast']=restoration_planning.prepare(root,context,key,plan,model_state)
        recommendation=proposal_selection.select(context,plan)
        field.update(stage=plan['stage'],plan=plan,model_state=model_state,recommendation=recommendation,
                     next_step='Наборы мероприятий требуют расчёта на актуальной ИМА; исполнение не разрешено')
        if recommendation.get('ready'):
            field.update(stage='awaiting_human_decision',next_step='Утвердить лучший допустимый вариант либо вернуть с комментарием')
    except Exception as exc:
        field.update(stage='needs_attention',error=str(exc),recommendation={'ready':False,'reason':str(exc)})
    live_reasoning.save(root/'data'/'live'/'field_plans'/f'{key}.json',field)
    return field
