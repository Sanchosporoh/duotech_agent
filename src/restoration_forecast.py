"""Time-weighted forecast from separately calculated network phases, not an instant gain."""
def horizon(measure,remaining_hours,rates,plan_oil_tpd,accumulated_deficit_t):
    if remaining_hours<0:raise ValueError('Отрицательный горизонт')
    missing={p['well_state'] for p in measure['phases']}|{'restored'}
    if not missing.issubset(rates):return {'ready':False,'reason':'Нет расчётов сети для всех фаз'}
    left=remaining_hours
    production=0.
    timeline=[]
    for phase in measure['phases']:
        hours=min(left,phase['hours'])
        if hours<0 or phase['hours']<0:raise ValueError('Отрицательная длительность')
        if hours:
            production+=rates[phase['well_state']]*hours/24
            timeline.append(dict(phase,forecast_hours=hours,oil_tpd=rates[phase['well_state']]))
        left-=hours
    if left:
        production+=rates['restored']*left/24
        timeline.append({'name':'После ожидаемого восстановления','forecast_hours':left,'oil_tpd':rates['restored']})
    balance=production-plan_oil_tpd*remaining_hours/24-accumulated_deficit_t
    return {'ready':True,'expected_production_t':production,'expected_horizon_balance_t':balance,
            'expected_target_met':balance>=0,'timeline':timeline,'approved_for_execution':False,
            'restoration_guaranteed':False,'assumption':'Успешная промывка; фазовые режимы постоянны внутри интервала. Это прогноз, не факт.'}
