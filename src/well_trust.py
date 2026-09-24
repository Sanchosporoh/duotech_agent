"""Trust in each well = model KPI × data KPI; the agent regulates trusted wells first."""
import json
import pandas as pd


def load(root):
    path=root/'config'/'well_trust.json'
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else None


def compute(root,telemetry,hour):
    """Per well: model KPI (external process, config), data KPI (age of the last signal), trust and level."""
    policy=load(root)
    if policy is None or telemetry.empty:return {}
    known=telemetry[telemetry.hour<=hour]
    result={}
    for well,history in known.groupby('well_id'):
        age=hour-int(history.hour.max())
        limit=policy['data_max_age_hours']
        data=1. if age<=limit else .5 if age<=2*limit else 0.
        model=float(policy['wells'].get(well,policy['default_model_kpi']))
        trust=round(model*data,3)
        level='high' if trust>=policy['thresholds']['high'] else 'medium' if trust>=policy['thresholds']['low'] else 'low'
        result[well]={'model_kpi':model,'data_kpi':data,'data_age_hours':age,'trust':trust,'level':level}
    return result


def table(trust):
    labels={'high':'высокое','medium':'среднее','low':'низкое'}
    return pd.DataFrame([{'Скважина':w,'KPI модели':v['model_kpi'],'Возраст замера, ч':v['data_age_hours'],
                          'KPI данных':v['data_kpi'],'Доверие':v['trust'],'Уровень':labels[v['level']]} for w,v in sorted(trust.items())])
