"""Smoke test the live GAP adapter with observed data, not an incident scenario."""
import json
from pathlib import Path
import sys
import argparse
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.live_planning import calculate


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--run-key',default='adapter_smoke_test_06')
    args=parser.parse_args()
    folder=ROOT/'data'/'live'
    separator=pd.read_csv(folder/'separator.csv')
    telemetry=pd.read_csv(folder/'telemetry.csv')
    hour=6
    context={'hour':hour,'separator':json.loads(separator[separator.hour<=hour].to_json(orient='records')),
             'telemetry':json.loads(telemetry[telemetry.hour<=hour].to_json(orient='records'))}
    register=json.loads((ROOT/'data'/'opportunity_register_structured.json').read_text(encoding='utf-8'))['opportunities']
    plan={'proposal':{'alternatives':[
        {'title':'Проверка адаптера: один доступный объект','selected_wells':['W_BEL_12_TLBB']},
        {'title':'Проверка адаптера: доступные контроли и защитные регулирования','selected_wells':[i['well_id'] for i in register if i['direction']!='increase_after_restore']}]}}
    answer=calculate(ROOT,context,args.run_key,plan,register)
    if answer.get('network_error'):raise RuntimeError(answer['network_error'])
    alternatives=answer['network']['alternatives']
    print('GAP adapter returned results:',len(alternatives),'; this is not an approval or proof of feasibility')
    print([{'title':r['title'],'status':r.get('status'),'gain_oil_tpd':r.get('gain_oil_tpd'),
            'water_limit_met':r.get('water_limit_met'),'fbhp_limit_met':r.get('fbhp_limit_met')} for r in alternatives])


if __name__=='__main__':main()
