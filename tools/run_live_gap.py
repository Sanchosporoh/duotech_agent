"""Calculate selected measures in a current-control network, without saves or scenario IDs."""
import argparse
import json
from pathlib import Path
import sys
import math
import time
from datetime import datetime

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'tools'))
from run_gap_optimization_case import OpenServer, petex_apps, result
from src.live_reasoning import save


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--request',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    request=json.loads(args.request.read_text(encoding='utf-8'))
    minimum_fbhp=float(request.get('minimum_fbhp_bar',80.))
    if petex_apps.is_process_running('gap.exe'):
        raise RuntimeError('GAP уже открыт: расчёт не переключает чужую модель')
    model=ROOT/'runtime'/'petex_case'/'IM_2022_06'/'BEL_PROD.gap'
    config=type('C',(),{'petex_folder':Path(r'C:\Program Files\Petroleum Experts\IPM 12.5'),'need_gap_passport':1,'need_prosper_passport':0,'need_mbal_passport':0})()
    launched=petex_apps.open_petex_apps(config)
    report={'model':str(model),'model_saved':False,'request':request,'alternatives':[]}
    progress={'events':[]}
    def solve(server,mode,stage,title):
        started=time.monotonic()
        event={'stage':stage,'alternative':title,'started_at':datetime.now().isoformat(),'status':'running'}
        progress['events'].append(event)
        args.output.parent.mkdir(parents=True,exist_ok=True)
        journal=args.output.with_name('progress.json')
        save(journal,progress)
        server.do_command(f'GAP.SOLVENETWORK({mode})')
        event.update(status='completed',elapsed_seconds=time.monotonic()-started)
        save(journal,progress)
    try:
        with OpenServer() as server:
            mod='GAP.MOD[{PROD}]'
            for alternative in request['alternatives']:
                server.do_command(f'GAP.OPENFILE("{model}")')
                server.do_command('GAP.SETUNITSYS("Norwegian S.I.")')
                solve(server,0,'baseline',alternative['title'])
                baseline=result(server)
                labels={w['well_id']:w for w in baseline['wells']}
                imported=[]
                for lift in alternative.get('lift_tables',request.get('lift_tables',[])):
                    wid=lift['well_id']
                    path=Path(lift['path']).resolve()
                    if wid not in labels:raise ValueError('Объект VLP отсутствует в сети '+wid)
                    if not path.is_relative_to(ROOT/'data'/'live') or not path.is_file():
                        raise ValueError('VLP разрешены только из data/live')
                    returned=server.do_command_gap(f'GAP.VLPIMPORT(MOD[{{PROD}}].WELL[{{{wid}}}],"{path}")')
                    if float(returned)!=1:raise ValueError('GAP не подтвердил импорт VLP '+wid)
                    imported.append({'well_id':wid,'path':str(path),'import_return':returned})
                disabled=[]
                for well in baseline['wells']:
                    tag=f"{mod}.WELL[{{{well['well_id']}}}]"
                    if 'ESP' in str(well['well_type']) or 'PCP' in str(well['well_type']):
                        server.set_value(tag+'.AlqControl','FIXEDVALUE')
                for signal in alternative.get('current_controls',request['current_controls']):
                    wid=signal['well_id']
                    if wid not in labels:raise ValueError(f'Нет объекта GAP: {wid}')
                    if 'ESP' not in str(labels[wid]['well_type']):continue
                    tag=f'{mod}.WELL[{{{wid}}}]'
                    if signal['frequency_hz']==0:
                        server.do_command(tag+'.DISABLE()'); disabled.append(wid)
                    else:server.set_value(tag+'.AlqValue',signal['frequency_hz'])
                solve(server,0,'current_state',alternative['title'])
                current=result(server)
                if request.get('validation_only'):
                    report['alternatives'].append({'title':alternative['title'],'status':'model_state_validation',
                        'current':current,'baseline':baseline,'imported_lift_tables':imported,
                        'oil_residual_tpd':float(current['oil_sm3d'])*.908-request['observed_oil_tpd'],
                        'water_residual_m3d':float(current['water_m3d'])-request['maximum_water_m3d'],
                        'approved_for_execution':False})
                    continue
                server.set_value(mod+'.OptMethod',0)
                server.set_value(mod+'.MAXQWAT',request['maximum_water_m3d'])
                server.set_value(mod+'.MAXQWATBINDING',1)
                for wid,well in labels.items():
                    if wid in disabled:continue
                    if 'ESP' in str(well['well_type']) or 'PCP' in str(well['well_type']):
                        tag=f'{mod}.WELL[{{{wid}}}]'
                        # 1 mbar inward numerical margin; acceptance remains strictly >= the limit.
                        server.set_value(tag+'.MINPWF',minimum_fbhp+.001)
                        server.set_value(tag+'.MINPWFBINDING',1)
                configured=[]
                for wid in alternative['selected_wells']:
                    if wid in disabled:raise ValueError('Нельзя регулировать остановленный объект '+wid)
                    item=request['opportunities'][wid]
                    if wid not in labels:raise ValueError('Объект реестра отсутствует в GAP '+wid)
                    tag=f'{mod}.WELL[{{{wid}}}]'
                    current_control=float(server.get_value(tag+'.AlqValue'))
                    delta=float(item['maximum_change'])
                    is_esp='ESP' in str(labels[wid]['well_type'])
                    if not is_esp and 'PCP' not in str(labels[wid]['well_type']):raise ValueError('Неподдерживаемый контроль '+wid)
                    policy=request['control_policy']
                    lowest=policy['esp_absolute_min_hz'] if is_esp else policy['pcp_absolute_min']
                    highest=policy['esp_absolute_max_hz'] if is_esp else policy['pcp_absolute_max']
                    if item['direction']=='correct':
                        low=max(lowest,current_control-delta); high=min(highest,current_control+delta)
                    elif item['direction']=='decrease':
                        low=max(lowest,current_control-delta); high=current_control
                    else:
                        low=current_control; high=min(policy['esp_absolute_max_hz'] if is_esp else policy['pcp_absolute_max'],current_control+delta)
                    if high<low:raise ValueError('Текущий контроль вне допустимого диапазона '+wid)
                    server.set_value(tag+'.AlqValueMin',low);server.set_value(tag+'.AlqValueMax',high)
                    server.set_value(tag+'.AlqControl','CALCULATED')
                    configured.append({'well_id':wid,'current':current_control,'minimum':low,'maximum':high})
                solve(server,1,'optimisation',alternative['title'])
                optimum=result(server)
                if optimum['solver_status']!=0:
                    report['alternatives'].append({'title':alternative['title'],'status':'solver_not_converged',
                        'current':current,'optimised':optimum,'configured_controls':configured,
                        'approved_for_execution':False,
                        'interpretation':f"GAP не подтвердил успешное решение; статус {optimum['solver_status']}. Эффект не рассчитан"})
                    continue
                for state in (current,optimum):
                    for key in ('oil_sm3d','water_m3d'):
                        if state[key] is None or not math.isfinite(float(state[key])) or float(state[key])<0:
                            raise ValueError('Нет физического результата GAP: '+key)
                active=[w for w in optimum['wells'] if w['well_id'] not in disabled and w['oil_sm3d'] is not None and float(w['oil_sm3d'])>0]
                missing_pressure=[w['well_id'] for w in active if w['fbhp_bar'] is None]
                minimum_pressure=min((float(w['fbhp_bar']) for w in active if w['fbhp_bar'] is not None),default=None)
                report['alternatives'].append({'title':alternative['title'],'current':current,'optimised':optimum,'configured_controls':configured,
                    'status':'conditional_calculated',
                    'gain_oil_tpd':(float(optimum['oil_sm3d'])-float(current['oil_sm3d']))*.908,
                    'model_measurement_residual_tpd':float(current['oil_sm3d'])*.908-request['observed_oil_tpd'],
                    'disabled_from_zero_frequency':disabled,
                    'water_limit_met':float(optimum['water_m3d'])<=request['maximum_water_m3d']+.01,
                    'minimum_fbhp_bar':minimum_pressure,'missing_pressures':missing_pressure,
                    'fbhp_limit_met':not missing_pressure and minimum_pressure is not None and minimum_pressure>=minimum_fbhp,
                    'approved_for_execution':False,
                    'imported_lift_tables':imported,
                    'model_measurement_water_residual_m3d':float(current['water_m3d'])-request['maximum_water_m3d'],
                    'interpretation':'Предварительный расчёт с переданной VLP; баланс с сепаратором требует проверки. Не разрешение на исполнение' if imported else 'Условный расчёт без адаптации характеристик. Не разрешение на исполнение'})
    finally:petex_apps.close_petex_apps(launched or [])
    args.output.parent.mkdir(parents=True,exist_ok=True)
    save(args.output,report)
    print('Calculated',len(report['alternatives']),'alternatives; model not saved')


if __name__=='__main__':
    from src.cycle_lock import acquire
    with acquire(ROOT,'petex.lock') as locked:
        if not locked:raise RuntimeError('Другой расчёт PetEx ещё работает. Повторный запуск запрещён.')
        main()
