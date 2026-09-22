"""Compare all computed options against one measured baseline; residual deficit is allowed."""
import hashlib
import json
import math
from pathlib import Path
import pandas as pd


def select(context,plan):
    if not plan.get('need',{}).get('ready'):return {'ready':False,'reason':'Нет суточного баланса'}
    last=pd.DataFrame(context['separator']).sort_values('hour').iloc[-1]
    remaining=plan['need']['remaining_hours'];deficit=plan['need']['net_deficit_t']
    candidates=[]
    def add(title,phases,cost=None,unresolved=None):
        if not phases or any(not math.isfinite(p['oil_tpd']) for p in phases):return
        balance=sum(p['oil_tpd']*p['hours']/24 for p in phases)-float(last.plan_oil_tpd)*remaining/24-deficit
        candidate={'title':title,'phases':phases,'expected_balance_t':balance,'expected_deficit_t':max(0.,-balance),
            'cost_mln_rub':cost,'unresolved':unresolved or [],'approved_for_execution':False}
        candidate['proposal_id']=hashlib.sha256(json.dumps(candidate,sort_keys=True).encode()).hexdigest()
        candidates.append(candidate)
    for source in [plan,plan.get('capacity_check',{})]:
        for alternative in source.get('network',{}).get('alternatives',[]):
            if alternative.get('status')!='conditional_calculated' or not (alternative.get('water_limit_met') and alternative.get('fbhp_limit_met')):continue
            current=alternative['current'];optimum=alternative['optimised']
            delta=(float(optimum['oil_sm3d'])-float(current['oil_sm3d']))*.908
            title=alternative['title'] if source is plan else 'Регулирование доступных скважин без промывки'
            add(title,[{'name':'Новые режимы','hours':remaining,
                'oil_tpd':float(last.separator_oil_tpd)+delta,'oil_delta_tpd':delta,
                'water_delta_m3d':float(optimum['water_m3d'])-float(current['water_m3d']),
                'wells':optimum['wells']}])
    wash=plan.get('restoration_forecast',{})
    if wash.get('ready'):
        network=json.loads(Path(wash['network_result']).read_text(encoding='utf-8'))
        states={a['title']:a for a in network['alternatives']}
        reference=states['degraded']['current']
        left=remaining;phases=[]
        timeline=wash['measure']['phases']+[{'name':'После ожидаемого восстановления','hours':remaining,'well_state':'restored'}]
        for phase in timeline:
            hours=min(left,phase['hours'])
            if not hours:continue
            state=states[phase['well_state']]['optimised']
            delta=(float(state['oil_sm3d'])-float(reference['oil_sm3d']))*.908
            phases.append({'name':phase['name'],'hours':hours,'oil_tpd':float(last.separator_oil_tpd)+delta,
                'oil_delta_tpd':delta,'water_delta_m3d':float(state['water_m3d'])-float(reference['water_m3d']),
                'wells':state['wells'],'well_state':phase['well_state'],'repair_well_id':wash['well_id']})
            left-=hours
        add(wash['measure']['title']+' + компенсационные режимы',phases,unresolved=wash.get('unresolved'))
    if not candidates:return {'ready':False,'reason':'Нет рассчитанного варианта, прошедшего ограничения'}
    # Economic preference is applied only when both compared costs are known.
    best=min(candidates,key=lambda c:(c['expected_deficit_t'],sum(len(p['wells']) for p in c['phases'])))
    return {'ready':True,'selected':best,'candidates':candidates,
        'basis':'Факт сепаратора + изменение добычи по ИМА относительно текущей сети. Одинаковая основа для всех вариантов; невязка модели не считается дополнительной добычей.',
        'limitations':['Прогноз предполагает сохранение текущих условий между фазами','Баланс модели с измерениями ещё не согласован','Стоимость и сравнение рисков не завершены; выбор выполнен по ожидаемому недобору']}
