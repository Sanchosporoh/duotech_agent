"""Читает исходные параметры W27 через OpenServer без сохранения модели."""
import json
from datetime import datetime
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"petex_passport_ima"))
from open_server import OpenServer
import petex_apps

FIELDS={
    "ipr_method":"PROSPER.SIN.IPR.Single.IprMethod",
    "reservoir_pressure":"PROSPER.SIN.IPR.Single.Pres",
    "productivity_index":"PROSPER.SIN.IPR.Single.Pindex",
    "water_cut":"PROSPER.SIN.IPR.Single.Wc",
    "gor":"PROSPER.SIN.IPR.Single.totgor",
    "pump_frequency":"PROSPER.SIN.ESP.Frequency",
    "pump_wear":"PROSPER.SIN.ESP.Wear",
    "pump_depth":"PROSPER.SIN.ESP.Depth",
    "last_test_rate":"PROSPER.ANL.VMT.Data[0].Rate",
    "last_test_whp":"PROSPER.ANL.VMT.Data[0].THpres",
    "last_test_gauge_pressure":"PROSPER.ANL.VMT.Data[0].Gpres",
    "last_test_gauge_depth":"PROSPER.ANL.VMT.Data[0].Gdepth",
    "lift_correlation":"PROSPER.ANL.SYS.TubingLabel",
    "saved_tcc_whp":"PROSPER.ANL.TCC.Pres",
}

def main():
    if petex_apps.is_process_running("prosper.exe"):
        raise RuntimeError("PROSPER уже открыт. Аудит не переключает чужую рабочую модель: закройте её перед запуском.")
    cfg=type("Config",(),{"petex_folder":Path(r"C:\Program Files\Petroleum Experts\IPM 12.5"),
        "need_prosper_passport":1,"need_gap_passport":0,"need_mbal_passport":0})()
    launched=petex_apps.open_petex_apps(cfg)
    model=ROOT/"runtime"/"petex_case"/"IM_2022_06"/"W_BEL_27.Out"
    report={"model":str(model),"model_saved":False,"diagnosis_performed":False,"parameters":{}}
    try:
        with OpenServer() as server:
            server.do_command(f'PROSPER.OPENFILE("{model}")')
            server.do_command('PROSPER.SETUNITSYS("Oilfield")')
            for name,expr in FIELDS.items():
                item={"expression":expr}
                try:
                    item["value"]=server.get_value(expr)
                    try: item["unit"]=server.get_value(expr+".Unitname")
                    except Exception: item["unit"]=None
                except Exception as exc: item["error"]=str(exc)
                report["parameters"][name]=item
            tests=[]
            for index in range(int(server.get_value("PROSPER.ANL.VMT.Data.count"))):
                row={"index":index}
                for key in ("Date","Rate","THpres","WC","GOR","Freq","Wear","Gpres","Gdepth"):
                    try: row[key]=server.get_value(f"PROSPER.ANL.VMT.Data[{index}].{key}")
                    except Exception: row[key]=None
                tests.append(row)
            def date_key(row):
                try: return datetime.strptime(row["Date"].replace("/","."),"%d.%m.%Y")
                except Exception: return datetime.min
            dated=[row for row in tests if date_key(row)!=datetime.min]
            report["tests"]=tests
            latest=max(dated,key=date_key) if dated else None
            report["latest_test_by_date"]=latest
            report["lift_probe"]={"purpose":"Пробный расчёт чувствительности лифта при неизменном насосе; не диагностика инцидента", "points":[]}
            if latest:
                def number(key):
                    value=float(latest[key])
                    if abs(value)>=1e20: raise ValueError(f"Нет исходного параметра {key}")
                    return value
                try:
                    pressure=number("THpres"); rate=number("Rate")
                    wc=number("WC"); gor=number("GOR")
                    correlation=server.get_value("PROSPER.ANL.SYS.TubingLabel")
                    from prosper_passport import CORR_MAP
                    method=CORR_MAP[correlation]
                    server.set_value("PROSPER.ANL.TCC.CorrLabel[$]",0)
                    server.set_value(f"PROSPER.ANL.TCC.CorrLabel[{{{correlation}}}]",1)
                    server.set_value("PROSPER.ANL.TCC.Pres",pressure)
                    server.set_value("PROSPER.ANL.TCC.WC",wc)
                    server.set_value("PROSPER.ANL.TCC.GOR",gor)
                    report["lift_probe"]["boundary_conditions"]={"test_date":latest["Date"],"test_index":latest["index"],"whp_psig":pressure,"wc_pct":wc,"gor_scf_stb":gor,"pump_state":"Текущие Frequency/Wear модели, без доадаптации"}
                    for fraction in (1.0,0.75,0.5,1.1,0.25):
                        server.set_value("PROSPER.ANL.TCC.Rate",rate*fraction)
                        server.do_command("PROSPER.ANL.TCC.CALC")
                        n=int(server.get_value(f"PROSPER.OUT.TCC.Results[{method}].MSD.count"))
                        depths=server.get_value_array(f"PROSPER.OUT.TCC.Results[{method}].MSD[$]")
                        pressures=server.get_value_array(f"PROSPER.OUT.TCC.Results[{method}].Pres[$]")
                        if n<=0 or n>min(len(depths),len(pressures)): raise ValueError("Некорректный профиль TCC")
                        profile=[{"depth_ft":float(d),"pressure_psig":float(p)} for d,p in zip(depths[:n],pressures[:n])]
                        gauge_depth=number("Gdepth")
                        closest=sorted(range(n),key=lambda i:abs(profile[i]["depth_ft"]-gauge_depth))[:6]
                        gauge_neighbours=[dict(index=i,**profile[i]) for i in sorted(closest)]
                        report["lift_probe"]["points"].append({"rate_fraction":fraction,"liquid_rate_stbd":rate*fraction,"bottom_depth_ft":float(depths[n-1]),"bottom_pressure_psig":float(pressures[n-1]),"profile":profile,"gauge_neighbours":gauge_neighbours})
                    report["lift_probe"]["gauge_reference"]={"depth_ft":number("Gdepth"),"measured_pressure_psig":number("Gpres"),"pump_depth_ft":float(report["parameters"]["pump_depth"]["value"]),"comparison_status":"Требуется определить сторону датчика относительно насоса; автоматическая интерполяция через насос запрещена"}
                    # Generate hidden scenario truth from the joint inflow/lift solver.
                    server.set_value("PROSPER.ANL.SYS.Pres",pressure)
                    server.set_value("PROSPER.ANL.SYS.WC",wc)
                    server.set_value("PROSPER.ANL.SYS.GOR",gor)
                    server.set_value("PROSPER.ANL.SYS.RateMethod",0)
                    server.set_value("PROSPER.ANL.SYS.Sens.SensDB.Clear",1)
                    server.set_value("PROSPER.ANL.SYS.Sens.Gen.Number",50)
                    report['system_settings']={}
                    for expr in ('PROSPER.ANL.SYS.Sens.Gen.Number','PROSPER.ANL.SYS.ILHAND','PROSPER.ANL.SYS.SolutionNode','PROSPER.ANL.SYS.TubingLabel','PROSPER.OUT.SYS.Results.count','PROSPER.ANL.SYS.Pres','PROSPER.ANL.SYS.WC','PROSPER.ANL.SYS.GOR','PROSPER.ANL.TCC.RateType','PROSPER.ANL.VMT.RateType'):
                        try: report['system_settings'][expr]=server.get_value(expr)
                        except Exception as exc: report['system_settings'][expr]={'error':str(exc)}
                    wear=float(report['parameters']['pump_wear']['value'])
                    pi=float(report['parameters']['productivity_index']['value'])
                    cases=[]
                    for label,new_wear,new_pi in (("baseline",wear,pi),("pump_mild",wear+.08,pi),("pump_severe",wear+.2,pi),("pump_failure",.9,pi),("inflow_mild",wear,pi*.8),("inflow_severe",wear,pi*.5),("baseline_repeat",wear,pi)):
                        server.set_value("PROSPER.SIN.ESP.Wear",new_wear)
                        server.set_value("PROSPER.SIN.IPR.Single.Pindex",new_pi)
                        server.set_value("PROSPER.ANL.SYS.RateMethod",0)
                        server.do_command("PROSPER.ANL.SYS.CALC")
                        first_rate=float(server.get_value('PROSPER.OUT.SYS.Results[0].Sol.LiqRate'))
                        server.set_value("PROSPER.ANL.SYS.RateMethod",1)
                        for index in range(20):
                            server.set_value(f"PROSPER.ANL.SYS.Rates[{index}]",first_rate*(.7+.6*index/19))
                        server.do_command("PROSPER.ANL.SYS.CALC")
                        solution={key:float(server.get_value_array(f'PROSPER.OUT.SYS.Results[0].Sol.{expr}')[0]) for key,expr in (("liquid_rate_stbd","LiqRate"),("bottom_pressure_psig","BHP"),("intake_pressure_psig","PIP"))}
                        if any(abs(v)>=1e20 for v in solution.values()) or solution['liquid_rate_stbd']<=0:
                            raise ValueError(f"Нет физического решения SYS для {label}")
                        cases.append(dict(case=label,wear=new_wear,productivity_index=new_pi,**solution))
                        cases[-1]['first_automatic_rate_stbd']=first_rate
                        server.set_value("PROSPER.ANL.TCC.Rate",solution['liquid_rate_stbd'])
                        server.do_command("PROSPER.ANL.TCC.CALC")
                        nd=int(server.get_value(f"PROSPER.OUT.TCC.Results[{method}].MSD.count"))
                        ds=server.get_value_array(f"PROSPER.OUT.TCC.Results[{method}].MSD[$]")
                        ps=server.get_value_array(f"PROSPER.OUT.TCC.Results[{method}].Pres[$]")
                        cases[-1]['lift_profile']=[{'depth_ft':float(d),'pressure_psig':float(p)} for d,p in zip(ds[:nd],ps[:nd])]
                    report['physical_scenarios']={'solver':'PROSPER.ANL.SYS.CALC','fixed_conditions':report['lift_probe']['boundary_conditions'],'cases':cases,'purpose':'Скрытая истина генератора: агент не получает заданные Wear/PI или индивидуальный дебит'}
                except Exception as exc:
                    report["lift_probe"]["error"]=str(exc)
    finally:
        petex_apps.close_petex_apps(launched or [])
    target=ROOT/"data"/"prosper_diagnostic_audit_W27.json"
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(target)

if __name__=="__main__": main()
