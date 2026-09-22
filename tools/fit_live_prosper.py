"""Competing physical fits, without using generator parameters or separator-based wear assignment."""
import argparse
import json
import math
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'petex_passport_ima'))
sys.path.insert(0,str(ROOT))
from open_server import OpenServer
import petex_apps
from prosper_passport import CORR_MAP
from src.prosper_diagnostics import intake_pressure
from src.live_reasoning import save


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--request',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    request=json.loads(args.request.read_text(encoding='utf-8'))
    model=(ROOT/request['working_model']).resolve()
    if not model.is_relative_to((ROOT/'runtime').resolve()):raise ValueError('Только рабочая модель в runtime')
    if petex_apps.is_process_running('prosper.exe'):raise RuntimeError('PROSPER уже открыт; чужая рабочая модель не переключается')
    config=type('C',(),{'petex_folder':Path(r'C:\Program Files\Petroleum Experts\IPM 12.5'),'need_prosper_passport':1,'need_gap_passport':0,'need_mbal_passport':0})()
    launched=petex_apps.open_petex_apps(config)
    report={'well_id':request['well_id'],'model_saved':False,'candidates':[],
            'interpretation':'Сопоставление с давлением; несколько вариантов допустимы. Не подтверждение причины и не адаптированная сеть GAP.'}
    try:
        with OpenServer() as server:
            server.do_command(f'PROSPER.OPENFILE("{model}")')
            server.do_command('PROSPER.SETUNITSYS("Oilfield")')
            wear=float(server.get_value('PROSPER.SIN.ESP.Wear'))
            pi=float(server.get_value('PROSPER.SIN.IPR.Single.Pindex'))
            depth=float(server.get_value('PROSPER.SIN.ESP.Depth'))
            correlation=server.get_value('PROSPER.ANL.SYS.TubingLabel'); method=CORR_MAP[correlation]
            server.set_value('PROSPER.ANL.SYS.Sens.SensDB.Clear',1)
            server.set_value('PROSPER.ANL.TCC.CorrLabel[$]',0)
            server.set_value(f'PROSPER.ANL.TCC.CorrLabel[{{{correlation}}}]',1)
            server.set_value('PROSPER.ANL.TCC.RateType',0)
            values={'Pres':(request['whp_bara']-1.01325)/.0689475729,'WC':request['water_cut_pct'],'GOR':request['gor_m3m3']/.178107606679035}
            for section in ('SYS','TCC'):
                for name,value in values.items():server.set_value(f'PROSPER.ANL.{section}.{name}',value)
            server.set_value('PROSPER.SIN.ESP.Frequency',request['frequency_hz'])
            candidates=[('unchanged',wear,pi)]
            candidates += [('pump',wear+(.95-wear)*fraction,pi) for fraction in [.25,.5,.75,1]]
            candidates += [('inflow',wear,pi*scale) for scale in [.8,.6,.4,.2]]
            report['grid_reason']='Четыре точки ухудшения каждой характеристики и исходная точка; это начальная сетка поиска, не лимит времени расчёта и не значения из генератора'
            for kind,new_wear,new_pi in candidates:
                row={'kind':kind,'wear':new_wear,'productivity_index':new_pi}
                try:
                    server.set_value('PROSPER.SIN.ESP.Wear',new_wear)
                    server.set_value('PROSPER.SIN.IPR.Single.Pindex',new_pi)
                    server.set_value('PROSPER.ANL.SYS.RateMethod',0)
                    server.do_command('PROSPER.ANL.SYS.CALC')
                    rate=float(server.get_value('PROSPER.OUT.SYS.Results[0].Sol.LiqRate'))
                    if not math.isfinite(rate) or not 0<rate<1e20:raise ValueError('Нет рабочей точки')
                    server.set_value('PROSPER.ANL.SYS.RateMethod',1)
                    for i in range(20):server.set_value(f'PROSPER.ANL.SYS.Rates[{i}]',rate*(.7+.6*i/19))
                    server.do_command('PROSPER.ANL.SYS.CALC')
                    rate=float(server.get_value('PROSPER.OUT.SYS.Results[0].Sol.LiqRate'))
                    pressure=float(server.get_value('PROSPER.OUT.SYS.Results[0].Sol.PIP'))
                    if not all(math.isfinite(v) and abs(v)<1e20 for v in (rate,pressure)) or rate<=0:raise ValueError('Нет физического решения')
                    server.set_value('PROSPER.ANL.TCC.Rate',rate);server.do_command('PROSPER.ANL.TCC.CALC')
                    ds=server.get_value_array(f'PROSPER.OUT.TCC.Results[{method}].MSD[$]')
                    ps=server.get_value_array(f'PROSPER.OUT.TCC.Results[{method}].Pres[$]')
                    count=int(server.get_value(f'PROSPER.OUT.TCC.Results[{method}].MSD.count'))
                    profile=[{'depth_ft':float(d),'pressure_psig':float(p)} for d,p in zip(ds[:count],ps[:count])]
                    intake=intake_pressure({'profile':profile},depth)['pressure_psig']
                    numerical_error=(pressure-intake)*.0689475729
                    measured_error=pressure*.0689475729+1.01325-request['sensor_pressure_bar']
                    row.update(liquid_m3d=rate*.158987294928,intake_bara=pressure*.0689475729+1.01325,
                               measured_residual_bar=measured_error,sys_tcc_residual_bar=numerical_error,
                               pressure_compatible=abs(measured_error)<=request['tolerance_bar'] and abs(numerical_error)<=request['tolerance_bar'])
                except Exception as exc:row.update(error=str(exc),pressure_compatible=False)
                report['candidates'].append(row)
    finally:petex_apps.close_petex_apps(launched or [])
    args.output.parent.mkdir(parents=True,exist_ok=True)
    save(args.output,report)
    print('PROSPER fits completed:',len(report['candidates']))


if __name__=='__main__':
    from src.cycle_lock import acquire
    with acquire(ROOT,'petex.lock') as locked:
        if not locked:raise RuntimeError('Другой расчёт PetEx ещё работает. Повторный запуск запрещён.')
        main()
