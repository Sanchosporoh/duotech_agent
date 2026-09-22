"""Local approval registry and delayed simulation effects. Source CSVs remain unchanged."""
from datetime import datetime
import json
import pandas as pd
from src.live_reasoning import save


def load(root):
    path=root/'data/live/approved_actions.json'
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'actions':[]}


def approval_rows(root):
    return [{'Инцидент':a['incident_id'],'Мероприятие':a['proposal']['title'],
             'Утверждено':f"{a['approved_hour']:02d}:00",'Начало эффекта':f"{a['approved_hour']+1:02d}:00",
             'Ожидаемый недобор, т':a['proposal'].get('expected_deficit_t'),
             'Дата решения':a.get('approved_at','')} for a in load(root)['actions']]


def approve(root,incident_id,hour,fingerprint,recommendation,acknowledged=False):
    if not acknowledged:raise ValueError('Подтвердите предварительный характер расчёта и режим имитации')
    if not recommendation.get('ready'):raise ValueError('Нет допустимого рассчитанного предложения')
    if not 0<=hour<23:raise ValueError('Нет оставшегося прогнозного периода')
    data=load(root)
    identity=f'{incident_id}:{fingerprint}'
    previous=next((a for a in data['actions'] if a['approval_id']==identity),None)
    if previous:return previous
    action={'approval_id':identity,'incident_id':incident_id,'approved_hour':hour,'fingerprint':fingerprint,
            'approved_at':datetime.now().isoformat(),'proposal':recommendation['selected'],'mode':'local_simulation'}
    data['actions'].append(action)
    save(root/'data/live/approved_actions.json',data)
    return action


def apply(root,separator,telemetry):
    separator=separator.copy();telemetry=telemetry.copy()
    separator['execution_effect_oil_tpd']=0.
    separator['execution_effect_water_m3d']=0.
    actions=load(root)['actions']
    for action in sorted(actions,key=lambda a:a['approved_at']):
        start=action['approved_hour']+1
        # A new field-wide proposal replaces previous future regimes, not adds them twice.
        baseline=separator[separator.hour==action['approved_hour']]
        prior_oil=float(baseline.iloc[0].execution_effect_oil_tpd) if not baseline.empty else 0.
        prior_water=float(baseline.iloc[0].execution_effect_water_m3d) if not baseline.empty else 0.
        for phase in action['proposal']['phases']:
            end=start+phase['hours']
            mask=(separator.hour>=start)&(separator.hour<end)
            separator.loc[mask,'execution_effect_oil_tpd']=prior_oil+phase['oil_delta_tpd']
            separator.loc[mask,'execution_effect_water_m3d']=prior_water+phase['water_delta_m3d']
            for well in phase['wells']:
                signal=(telemetry.well_id==well['well_id'])&(telemetry.hour>=start)&(telemetry.hour<end)
                control=well.get('control_optimised')
                if control is None:control=well.get('control_actual')
                if control is not None:
                    column='frequency_hz' if 'ESP' in str(well['well_type']) else 'pcp_speed'
                    telemetry.loc[signal,column]=control
            target=phase.get('repair_well_id')
            if target:
                signal=(telemetry.well_id==target)&(telemetry.hour>=start)&(telemetry.hour<end)
                if phase.get('well_state')=='stopped':telemetry.loc[signal,'frequency_hz']=0.
                if phase.get('well_state')=='restored':
                    # No calculated bottomhole pressure is passed off as measured intake pressure.
                    telemetry.loc[signal,'sensor_pressure_bar']=float('nan')
            start=end
    separator.separator_oil_tpd+=separator.execution_effect_oil_tpd
    if 'separator_water_m3d' in separator:separator.separator_water_m3d+=separator.execution_effect_water_m3d
    return separator,telemetry
