"""How much to recompute for open incidents when a new hour of data arrives.

full    — new event: diagnosis (LLM, PROSPER) and measure sets (LLM) + GAP;
network — network conditions changed: GAP for the previous measure sets only;
none    — nothing essential changed: code updates the deficit and balance only.
The comparison is always with the basis of the last full calculation.
"""
import json
import pandas as pd
from src import live_monitor

CONTROL_EVENT='Изменение управляющего режима'


def load(root):
    """No policy file means no reuse: every hour is a full calculation."""
    path=root/'config'/'recompute_policy.json'
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else None


def signature(separator,telemetry,hour,incidents,comments,dependencies):
    """Cheap description of the current state, compared between hours."""
    known=telemetry[telemetry.hour<=hour].sort_values('hour')
    last=known.groupby('well_id').last() if not known.empty else pd.DataFrame()
    events=live_monitor.hypotheses(telemetry,hour)
    current=separator[separator.hour==hour].iloc[0]
    def values(column):
        if column not in last:return {}
        return {well:float(v) for well,v in last[column].items() if pd.notna(v)}
    return {'hour':hour,'incidents':sorted(incidents),'comments':comments,'dependencies':dependencies,
            'events':sorted({f'{r.well_id}|{r.hypothesis}' for r in events.itertuples() if r.well_id!='—'}),
            'controls':values('frequency_hz'),'pressures':values('sensor_pressure_bar'),
            'oil_tpd':float(current.separator_oil_tpd),
            'water_m3d':None if pd.isna(current.get('separator_water_m3d')) else float(current.separator_water_m3d)}


def classify(policy,basis,current):
    """Return (level, reasons) for the current signature against the last full basis."""
    if policy is None:return 'full',['Политика пересчёта не задана: полный расчёт каждый час']
    if not basis:return 'full',['Первый расчёт по этому набору инцидентов']
    reasons=[]
    if basis['incidents']!=current['incidents']:reasons.append('Изменился состав открытых инцидентов')
    if any(basis['comments'].get(i)!=c for i,c in current['comments'].items() if i in basis['comments']):
        reasons.append('Инженер вернул предложение с комментарием')
    if basis['dependencies']!=current['dependencies']:reasons.append('Изменились модели, реестр или конфигурация')
    new=sorted(set(current['events'])-set(basis['events']))
    # A measured control change has a known cause: it changes the network, not the diagnosis.
    unexplained=[e for e in new if not e.endswith('|'+CONTROL_EVENT)]
    if unexplained:reasons.append('Новые признаки телеметрии: '+', '.join(e.replace('|',' — ') for e in unexplained))
    moved=[w for w,p in current['pressures'].items() if w in basis['pressures'] and abs(p-basis['pressures'][w])>policy['pressure_tolerance_bar']]
    if moved:reasons.append(f"Давление изменилось больше {policy['pressure_tolerance_bar']:g} бар с последнего полного расчёта: "+', '.join(moved))
    if basis['oil_tpd'] and abs(current['oil_tpd']-basis['oil_tpd'])/basis['oil_tpd']*100>policy['oil_change_full_pct']:
        reasons.append(f"Нефть сепаратора изменилась больше {policy['oil_change_full_pct']:g} % без объяснения")
    if reasons:return 'full',reasons
    changed=sorted({w for w,c in current['controls'].items() if basis['controls'].get(w)!=c}|{e.split('|')[0] for e in new})
    if changed:reasons.append('Изменились режимы скважин: '+', '.join(changed))
    if current['water_m3d'] is not None and basis['water_m3d'] is not None and abs(current['water_m3d']-basis['water_m3d'])>policy['water_tolerance_m3d']:
        reasons.append(f"Вода сепаратора изменилась больше {policy['water_tolerance_m3d']:g} м³/сут")
    if reasons:return 'network',reasons
    return 'none',['Существенных изменений нет: пересчитаны только недобор и баланс по прежнему расчёту']
