"""Counterfactual network phases for a pump wash, driven by the current snapshot."""
import hashlib
import json
from src.calculation_result import completed as result_completed, preserve_previous
import pandas as pd
from src.live_reasoning import save
from src.restoration_forecast import horizon
from src import license_retry, tool_gateway


def prepare(root,context,key,plan,model_state):
    tables=model_state.get('lift_tables',[])
    if len(tables)!=1 or tables[0].get('candidate',{}).get('kind')!='pump':
        return {'ready':False,'reason':'Для промывки требуется отдельная диагностическая постановка по насосу'}
    source=plan.get('capacity_check',plan)
    if 'network' not in source:return {'ready':False,'reason':'Нет расчёта компенсационных режимов'}
    request=json.loads(json.dumps(source['network']['request']))
    well=tables[0]['well_id']
    selected=list(request['opportunities'])
    frequency=next(float(c['frequency_hz']) for c in request['current_controls'] if c['well_id']==well)
    request['opportunities'][well]={'control':'esp_frequency','direction':'decrease',
        'maximum_change':max(0,frequency-request['control_policy']['esp_absolute_min_hz'])}
    stopped=[dict(c) for c in request['current_controls'] if c['well_id']!=well]+[{'well_id':well,'frequency_hz':0}]
    request['alternatives']=[
        {'title':'degraded','selected_wells':selected},
        {'title':'stopped','selected_wells':selected,'current_controls':stopped},
        {'title':'restored','selected_wells':selected+[well] if well not in selected else selected,'lift_tables':[]},
    ]
    measure=json.loads((root/'config/restoration_measures.json').read_text(encoding='utf-8'))['measures'][0]
    digest=hashlib.sha256(json.dumps({'request':request,'measure':measure,'context':context,'adapter_version':3},sort_keys=True).encode()).hexdigest()
    folder=root/'data/live/restoration'/key/digest
    output=folder/'network.json';attempt=folder/'attempt.json'
    if not result_completed(output,attempt):
        waiting=license_retry.blocked(root,attempt)
        if waiting:return dict(waiting,ready=False)
        preserve_previous(output)
        save(folder/'request.json',request);save(attempt,{'stage':'running'})
        completed=tool_gateway.run_worker(root,'run_live_gap',folder/'request.json',output)
        if completed.returncode or not output.exists():
            reason=(completed.stderr or completed.stdout)[-2000:]
            failure=license_retry.failure(root,reason)
            save(attempt,failure)
            return dict(failure,ready=False)
        license_retry.success(root)
        save(attempt,{'stage':'completed'})
    alternatives=json.loads(output.read_text(encoding='utf-8'))['alternatives']
    valid=len(alternatives)==3 and all(a.get('status')=='conditional_calculated' and a.get('water_limit_met') and a.get('fbhp_limit_met') for a in alternatives)
    if valid:
        need=plan['need']
        latest=pd.DataFrame(context['separator']).sort_values('hour').iloc[-1]
        reference=next(a['current'] for a in alternatives if a['title']=='degraded')
        rates={a['title']:float(latest.separator_oil_tpd)+(float(a['optimised']['oil_sm3d'])-float(reference['oil_sm3d']))*.908 for a in alternatives}
        result=horizon(measure,need['remaining_hours'],rates,float(latest.plan_oil_tpd),need['net_deficit_t'])
        result['basis']='Факт сепаратора + изменение относительно текущей сети; постоянство невязки между фазами — допущение прогноза'
    else:result={'ready':False,'reason':'Не все фазы дали допустимый результат GAP','approved_for_execution':False}
    result.update(measure=measure,well_id=well,network_result=str(output),
                  unresolved=['Применимость промывки к причине ухудшения требует инженерного подтверждения','Доступность бригады и стоимость не заданы','Успех промывки не гарантирован','Остаточная невязка текущей сети с сепаратором не согласована'])
    save(folder/'forecast.json',result)
    return result
