"""Integration check: actual observations -> Codex selection -> GAP with exported VLP."""
import json
import hashlib
from pathlib import Path
import sys
import pandas as pd
import argparse

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.live_planning import prepare, calculate, forecast_need
from src.live_reasoning import save


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--all-opportunities',action='store_true')
    args=parser.parse_args()
    folder=ROOT/'data'/'live'
    separator=pd.read_csv(folder/'separator.csv');telemetry=pd.read_csv(folder/'telemetry.csv')
    context={'hour':6,'separator':json.loads(separator[separator.hour<=6].to_json(orient='records')),
             'telemetry':json.loads(telemetry[telemetry.hour<=6].to_json(orient='records'))}
    fixture=folder/'adaptation'/'license_restored_fit_01'/'W_BEL_27_TLBB'
    fit=json.loads((fixture/'result.json').read_text(encoding='utf-8'))
    candidate=next(c for c in fit['candidates'] if c['pressure_compatible'])
    table=fixture/'fitted.tpd'
    model_state={'ready':True,'lift_tables':[{'well_id':fit['well_id'],'path':str(table.resolve()),
                 'sha256':hashlib.sha256(table.read_bytes()).hexdigest(),'candidate':candidate}],
                 'reason':'Предварительная диагностическая характеристика; баланс не утверждён'}
    # This verifies planning with a completed diagnostic result, not hypothesis generation.
    answer={'hypotheses':[{'title':'Ухудшение насоса совместимо с давлением; причина не подтверждена',
                          'candidate_wells':[fit['well_id']]}]}
    if args.all_opportunities:
        register=json.loads((ROOT/'data'/'opportunity_register_structured.json').read_text(encoding='utf-8'))['opportunities']
        eligible=[i for i in register if i['direction']!='increase_after_restore']
        plan={'need':forecast_need(context),'input':{'model_state':model_state},'proposal':{'alternatives':[{'title':'Проверка верхней границы доступных регулирований','selected_wells':[i['well_id'] for i in eligible]}]}}
        result=calculate(ROOT,context,'fitted_all_opportunities_01',plan,eligible)
        destination='fitted_all_opportunities_result.json'
    else:
        result=prepare(ROOT,context,'fitted_planning_integration_01',answer,fit['candidates'],model_state)
        destination='fitted_planning_result.json'
    save(folder/'integration'/destination,result)
    print(result['stage'])
    if result.get('network_error'):print(result['network_error'])
    for alternative in result.get('network',{}).get('alternatives',[]):
        print(json.dumps({k:alternative.get(k) for k in ['title','status','gain_oil_tpd','water_limit_met','fbhp_limit_met','conditional_target_met']},ensure_ascii=True))


if __name__=='__main__':main()
