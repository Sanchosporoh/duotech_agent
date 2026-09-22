"""Calculate three network states for the agreed educational pump wash."""
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.live_reasoning import save
from src.restoration_forecast import horizon


def main():
    source=json.loads((ROOT/'data/live/integration/fitted_all_opportunities_result.json').read_text(encoding='utf-8'))
    request=source['network']['request']
    lift=request['lift_tables']
    if len(lift)!=1:raise ValueError('Проверка требует одной диагностируемой скважины')
    well=lift[0]['well_id']
    selected=request['alternatives'][0]['selected_wells']
    frequency=next(float(c['frequency_hz']) for c in request['current_controls'] if c['well_id']==well)
    request['opportunities'][well]={'control':'esp_frequency','direction':'decrease',
        'maximum_change':max(0,frequency-request['control_policy']['esp_absolute_min_hz'])}
    stopped=[dict(c) for c in request['current_controls'] if c['well_id']!=well]+[{'well_id':well,'frequency_hz':0}]
    request['alternatives']=[
        {'title':'degraded','selected_wells':selected},
        {'title':'stopped','selected_wells':selected,'current_controls':stopped},
        {'title':'restored','selected_wells':selected+[well] if well not in selected else selected,'lift_tables':[]},
    ]
    folder=ROOT/'data/live/restoration/acid_wash_integration_02'
    output=folder/'network.json'
    save(folder/'request.json',request)
    if not output.exists():
        subprocess.run([sys.executable,str(ROOT/'tools/run_live_gap.py'),'--request',str(folder/'request.json'),'--output',str(output)],cwd=ROOT,check=True)
    network=json.loads(output.read_text(encoding='utf-8'))
    measure=json.loads((ROOT/'config/restoration_measures.json').read_text(encoding='utf-8'))['measures'][0]
    alternatives=network['alternatives']
    valid=all(a.get('status')=='conditional_calculated' and a.get('water_limit_met') and a.get('fbhp_limit_met') for a in alternatives)
    if valid:
        rates={a['title']:float(a['optimised']['oil_sm3d'])*.908 for a in alternatives}
        need=source['need']
        # Recover the plan from the same observed snapshot; no future fact is used.
        import pandas as pd
        separator=pd.read_csv(ROOT/'data/live/separator.csv')
        plan=float(separator[separator.hour==6].iloc[0].plan_oil_tpd)
        result=horizon(measure,need['remaining_hours'],rates,plan,need['net_deficit_t'])
    else:
        result={'ready':False,'reason':'Не все фазы дали допустимый результат GAP','approved_for_execution':False}
    result.update(measure=measure,well_id=well,network_result=str(output),
                  unresolved=['Доступность бригады и стоимость не заданы','Успех промывки не гарантирован','Остаточная невязка текущей сети с сепаратором не согласована'])
    save(folder/'forecast.json',result)
    print(json.dumps(result,ensure_ascii=True,indent=2))


if __name__=='__main__':main()
