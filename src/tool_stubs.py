"""Deterministic placeholders for Codex, PROSPER and GAP (backend "stub").

They exist only to run and test the whole cycle without licenses.  The GAP
placeholder is a proportional proxy on the reference network rates: it keeps
the result structure, not the physics.  Every result carries tool_backend=stub.
"""
import json
from pathlib import Path
import pandas as pd
from src import live_monitor
from src.live_reasoning import save

REPO=Path(__file__).resolve().parents[1]
MARK={'tool_backend':'stub','interpretation':'Заглушка: проверка цепочки, не результат PROSPER/GAP'}
DEGRADED_LIFT_FACTOR=.5   # a transferred degraded VLP halves the well rate in the proxy
FBHP_DROP_PER_UNIT=2.     # bar per Hz (or rpm unit) of control increase in the proxy
# GAP redistributes water under MAXQWAT; the proxy cannot, so it tolerates a small excess.
WATER_TOLERANCE_M3D=1.


def _payload(prompt):
    # Both live prompts end with one line of JSON input.
    return json.loads(prompt.rstrip().rsplit('\n',1)[1])


def codex(prompt,schema):
    if 'hypotheses' in schema['properties']:return _hypotheses(_payload(prompt))
    if 'alternatives' in schema['properties']:return _measure_sets(_payload(prompt))
    raise ValueError('Заглушка Codex не знает эту схему ответа')


def _hypotheses(context):
    telemetry=pd.DataFrame(context['telemetry'])
    rows=live_monitor.hypotheses(telemetry,context['hour']) if not telemetry.empty else pd.DataFrame()
    items=[]
    for _,row in rows.iterrows():
        wells=[] if row.well_id=='—' else [row.well_id]
        items.append({'title':row.hypothesis+('' if not wells else ' · '+row.well_id),'candidate_wells':wells,
                      'engineering_rationale':'Правило по изменению телеметрии (заглушка Codex)',
                      'verification':'Проверить согласованность притока и лифта расчётом','missing_data':['Текущий замер дебита скважины']})
    fillers=[('Ошибка измерения сепаратора','Независимая проверка замера сепаратора'),
             ('Групповое ограничение системы сбора','Сравнить линейные и устьевые давления'),
             ('Снижение дебита скважины без телеметрического признака','Внеочередной замер дебита по скважинам без свежих сигналов')]
    for title,check in fillers:
        if len(items)>=4:break
        items.append({'title':title,'candidate_wells':[],'engineering_rationale':'Альтернатива при неполной телеметрии (заглушка Codex)',
                      'verification':check,'missing_data':['Независимое измерение']})
    return {'assessment':'Заглушка Codex: гипотезы построены правилом по телеметрии, причина не подтверждена.','hypotheses':items[:6]}


def _measure_sets(payload):
    options=sorted(payload['opportunities'],key=lambda o:(-o['potential_oil_tpd'],o['well_id']))
    required=payload['preliminary_need'].get('required_extra_oil_tpd',0)
    minimal=[];total=0.
    for item in options:
        if total>=required:break
        minimal.append(item['well_id']);total+=item['potential_oil_tpd']
    cheap=[o['well_id'] for o in sorted(options,key=lambda o:(o['cost_mln_rub'],o['well_id']))][:max(1,len(minimal)+1)]
    low_risk=[o['well_id'] for o in options if o.get('geological_risk')=='low'] or minimal
    sets=[('Минимальное число воздействий',minimal),('Распределённое воздействие по стоимости',cheap),('Компромисс: низкий геологический риск',low_risk)]
    alternatives=[];seen=set()
    for title,wells in sets:
        key=tuple(sorted(wells))
        if not wells or key in seen:continue
        seen.add(key)
        alternatives.append({'title':title,'rationale':'Заглушка Codex: детерминированный отбор из реестра',
                             'selected_wells':list(wells),'unresolved_constraints':['Бюджет и бригады не заданы']})
    return {'assessment':'Заглушка Codex: наборы сформированы правилом, эффект не рассчитан.','alternatives':alternatives[:3]}


def worker(script,request,output):
    data=json.loads(request.read_text(encoding='utf-8'))
    output.parent.mkdir(parents=True,exist_ok=True)
    if script=='fit_live_prosper':save(output,_fit(data))
    elif script=='export_live_vlp':output.write_text('STUB VLP TABLE: not exported by PROSPER\n',encoding='utf-8')
    elif script=='run_live_gap':save(output,_network(data))
    else:raise ValueError('Заглушка не знает расчёт '+script)


def _fit(request):
    rows=[{'kind':'unchanged','wear':0.,'productivity_index':1.,'pressure_compatible':False,'measured_residual_bar':3.},
          {'kind':'pump','wear':.5,'productivity_index':1.,'pressure_compatible':True,'measured_residual_bar':.2},
          {'kind':'inflow','wear':0.,'productivity_index':.6,'pressure_compatible':False,'measured_residual_bar':2.}]
    return dict(MARK,well_id=request['well_id'],model_saved=False,candidates=rows,
                grid_reason='Заглушка: фиксированная сетка вариантов')


def _reference_wells():
    data=json.loads((REPO/'data/gap_optimization_result_balanced.json').read_text(encoding='utf-8'))
    return {w['well_id']:w for w in data['baseline']['wells']}


def _state(wells,controls,degraded):
    rows=[]
    for wid,ref in wells.items():
        base=float(ref['control_actual'] or 0);control=controls.get(wid,base)
        scale=control/base if base else 1.
        if wid in degraded:scale*=DEGRADED_LIFT_FACTOR
        rows.append({'well_id':wid,'well_type':ref['well_type'],'oil_sm3d':float(ref['oil_sm3d'] or 0)*scale,
                     'water_m3d':float(ref['water_m3d'] or 0)*scale,'fbhp_bar':ref['fbhp_bar'],
                     'control_actual':control,'control_optimised':None})
    return {'oil_sm3d':sum(r['oil_sm3d'] for r in rows),'water_m3d':sum(r['water_m3d'] for r in rows),
            'solver_status':0,'wells':rows}


def _network(request):
    reference=_reference_wells()
    report=dict(MARK,model_saved=False,request=request,alternatives=[])
    policy=request['control_policy']
    for alternative in request['alternatives']:
        signals=alternative.get('current_controls',request['current_controls'])
        controls={s['well_id']:float(s['frequency_hz']) for s in signals if s['well_id'] in reference}
        disabled=[w for w,c in controls.items() if c==0]
        degraded={t['well_id'] for t in alternative.get('lift_tables',request.get('lift_tables',[]))}
        current=_state(reference,controls,degraded)
        optimised_controls=dict(controls);configured=[]
        for wid in alternative['selected_wells']:
            if wid in disabled:raise ValueError('Нельзя регулировать остановленный объект '+wid)
            item=request['opportunities'][wid];ref=reference[wid]
            now=controls.get(wid,float(ref['control_actual']))
            esp='ESP' in str(ref['well_type'])
            lowest=policy['esp_absolute_min_hz'] if esp else policy['pcp_absolute_min']
            highest=policy['esp_absolute_max_hz'] if esp else policy['pcp_absolute_max']
            target=max(lowest,now-item['maximum_change']) if item['direction']=='decrease' else min(highest,now+item['maximum_change'])
            optimised_controls[wid]=target
            configured.append({'well_id':wid,'current':now,'minimum':min(now,target),'maximum':max(now,target)})
        optimised=_state(reference,optimised_controls,degraded)
        for row in optimised['wells']:
            before=controls.get(row['well_id'],float(reference[row['well_id']]['control_actual'] or 0))
            change=optimised_controls.get(row['well_id'],before)-before
            if change:
                row['control_optimised']=optimised_controls[row['well_id']]
                row['fbhp_bar']=float(row['fbhp_bar'])-FBHP_DROP_PER_UNIT*change
        active=[w for w in optimised['wells'] if w['well_id'] not in disabled and w['oil_sm3d']>0 and w['fbhp_bar'] is not None]
        minimum=min((float(w['fbhp_bar']) for w in active),default=None)
        # Proxy water differs from the separator: limit the water added to the proxy state.
        allowed_water=max(request['maximum_water_m3d'],current['water_m3d'])+WATER_TOLERANCE_M3D
        report['alternatives'].append(dict(MARK,title=alternative['title'],status='conditional_calculated',
            current=current,optimised=optimised,configured_controls=configured,
            gain_oil_tpd=(optimised['oil_sm3d']-current['oil_sm3d'])*.908,
            model_measurement_residual_tpd=current['oil_sm3d']*.908-request['observed_oil_tpd'],
            model_measurement_water_residual_m3d=current['water_m3d']-request['maximum_water_m3d'],
            disabled_from_zero_frequency=disabled,water_limit_met=optimised['water_m3d']<=allowed_water,
            minimum_fbhp_bar=minimum,missing_pressures=[],fbhp_limit_met=minimum is not None and minimum>=80,
            approved_for_execution=False,imported_lift_tables=sorted(degraded)))
    return report
