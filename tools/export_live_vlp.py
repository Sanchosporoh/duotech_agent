"""Export a fitted working PROSPER lift table; never save the source model."""
import argparse
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'petex_passport_ima'))
from open_server import OpenServer
import petex_apps


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--request',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    request=json.loads(args.request.read_text(encoding='utf-8'))
    model=(ROOT/request['working_model']).resolve()
    if not model.is_relative_to((ROOT/'runtime').resolve()):raise ValueError('Только рабочая копия модели')
    destination=args.output.resolve()
    if not destination.is_relative_to(ROOT/'data'/'live'):raise ValueError('Выход только в data/live')
    destination.parent.mkdir(parents=True,exist_ok=True)
    if petex_apps.is_process_running('prosper.exe'):raise RuntimeError('PROSPER уже открыт; чужая модель не переключается')
    config=type('C',(),{'petex_folder':Path(r'C:\Program Files\Petroleum Experts\IPM 12.5'),'need_prosper_passport':1,'need_gap_passport':0,'need_mbal_passport':0})()
    launched=petex_apps.open_petex_apps(config)
    try:
        with OpenServer() as server:
            server.do_command(f'PROSPER.OPENFILE("{model}")')
            server.do_command('PROSPER.SETUNITSYS("Oilfield")')
            server.set_value('PROSPER.SIN.ESP.Wear',request['candidate']['wear'])
            server.set_value('PROSPER.SIN.IPR.Single.Pindex',request['candidate']['productivity_index'])
            server.set_value('PROSPER.SIN.ESP.Frequency',request['frequency_hz'])
            # Preserve the model's existing pressure/frequency table grid, not its results.
            for name,value in {'Pres':(request['whp_bara']-1.01325)/.0689475729,'WC':request['water_cut_pct'],'GOR':request['gor_m3m3']/.178107606679035}.items():
                server.set_value('PROSPER.ANL.VLP.'+name,value)
            server.do_command('PROSPER.ANL.VLP.CALC')
            count=int(server.get_value('PROSPER.OUT.VLP.Results.COUNT'))
            if count<=0:raise ValueError('PROSPER не сформировал кривые VLP')
            server.set_value('PROSPER.ANL.VLP.EXP.File',str(destination))
            server.set_value('PROSPER.ANL.VLP.EXP.ExtType','tpd')
            # PROSPER exports through the Windows clipboard; a busy clipboard is transient.
            # The export only rewrites the output file, so repeating it is safe (the calculation is not repeated).
            for attempt in range(5):
                try:
                    server.do_command('PROSPER.ANL.VLP.EXPORTBYEXT');break
                except Exception as error:
                    if 'Clipboard' not in str(error) or attempt==4:raise
                    time.sleep(3*(attempt+1))
    finally:petex_apps.close_petex_apps(launched or [])
    if not destination.exists() or destination.stat().st_size==0:raise ValueError('Файл TPD не создан')
    print('VLP exported; model not saved:',destination)


if __name__=='__main__':
    from src.cycle_lock import acquire
    with acquire(ROOT,'petex.lock') as locked:
        if not locked:raise RuntimeError('Другой расчёт PetEx ещё работает. Повторный запуск запрещён.')
        main()
