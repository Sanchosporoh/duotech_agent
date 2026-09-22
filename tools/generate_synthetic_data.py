"""Один раз создаёт воспроизводимый синтетический сценарий из 40 часов."""
from __future__ import annotations
import csv, random
from datetime import datetime, timedelta
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/"data"
random.seed(42)

def write(name,headers,rows):
    DATA.mkdir(exist_ok=True)
    with (DATA/name).open("w",encoding="utf-8-sig",newline="") as f:
        writer=csv.writer(f); writer.writerow(headers); writer.writerows(rows)

start=datetime(2026,9,9,23)
with (DATA/"petex_well_reference.csv").open(encoding="utf-8-sig",newline="") as f:
    petex_wells=list(csv.DictReader(f))
production=[]; telemetry=[]
for hour in range(40):
    ts=start+timedelta(hours=hour); total_plan=0; total_fact=0
    for index,model in enumerate(petex_wells,1):
        well=model["well_id"]; lift=model["artificial_lift"]
        if model["well_type"]=="Water Injector":
            telemetry.append([ts.isoformat(),"KUST-01",well,lift,0,0,0,0,"",155,0,"","","","","",42,"injecting","confirmed"])
            continue
        plan_oil=14.0 if well=="W_BEL_13" else 5+(index%4)*0.7; wc=0.25+(index%6)*0.07
        degradation=max(0,hour-23)*0.82 if well=="W_BEL_13" else 0
        oil=max(0,plan_oil-degradation+random.uniform(-0.18,0.18))
        liquid=oil/(1-wc); bhp=125-random.uniform(-1.5,1.5)-(degradation*0.7 if well=="W_BEL_13" else 0)
        is_esp=lift=="Electrical Submersible Pump"
        current=(44+index*0.8+random.uniform(-0.7,0.7)+(degradation*0.8 if well=="W_BEL_13" else 0)) if is_esp else ""
        vibration=(2+random.uniform(-0.12,0.12)+(degradation*0.1 if well=="W_BEL_13" else 0)) if is_esp else ""
        esp_frequency=50 if is_esp else ""; pcp_speed=180+index*3 if not is_esp else ""; pcp_torque=8+index*0.2 if not is_esp else ""
        telemetry.append([ts.isoformat(),"KUST-01",well,lift,round(plan_oil,2),round(oil,2),round(liquid,2),round(wc*100,1),round(bhp,1),round(18+index*0.3,1),esp_frequency,round(current,1) if current!="" else "",round(vibration,2) if vibration!="" else "",pcp_speed,round(pcp_torque,1) if pcp_torque!="" else "",round(85-index*0.5,1),round(22+index*0.2,1),0,"running","confirmed"])
        total_plan+=plan_oil; total_fact+=oil
    production.append([ts.isoformat(),"KUST-01",round(total_plan,2),round(total_fact,2),"confirmed"])

write("production.csv",["timestamp","asset_id","plan_oil_tph","actual_oil_tph","status"],production)
write("well_telemetry.csv",["timestamp","asset_id","well_id","artificial_lift","plan_oil_tph","oil_rate_tph","liquid_rate_m3h","watercut_pct","bottomhole_pressure_bar","wellhead_pressure_bar","esp_frequency_hz","esp_current_a","vibration_mm_s","pcp_speed_rpm","pcp_torque_knm","intake_pressure_bar","tubing_pressure_bar","injection_rate_m3h","well_status","data_status"],telemetry)
write("events.csv",["event_id","timestamp","asset_id","well_id","event_type","description","planned","status"],[
    ["EV-001",(start+timedelta(hours=18)).isoformat(),"KUST-01","W_BEL_12","choke_adjustment","Изменение положения штуцера",True,"completed"],
    ["EV-002",(start+timedelta(hours=31)).isoformat(),"KUST-01","W_BEL_13","alarm","Рост тока и вибрации УЭЦН",False,"active"]])
write("physical_rules.csv",["rule_id","parameter","minimum","maximum","unit","severity","comment"],[
    ["PR-001","oil_rate_tph",0,60,"t/h","error","Отрицательный дебит невозможен"],
    ["PR-002","watercut_pct",0,100,"%","error","Физический диапазон обводнённости"],
    ["PR-003","bottomhole_pressure_bar",0,400,"bar","error","Первичный диапазон, требует уточнения"],
    ["PR-004","esp_current_a",0,120,"A","warning","Предварительная граница, требует уточнения"],
    ["PR-005","vibration_mm_s",0,12,"mm/s","warning","Предварительная граница, требует уточнения"]])
write("opportunities.csv",["opportunity_id","well_id","action","oil_gain_tpd","cost_mln_rub","team_hours"],[
    ["OP-001","W_BEL_13","Диагностика и восстановление режима УЭЦН",10,1.2,8],
    ["OP-002","W_BEL_12","Оптимизация частоты УЭЦН",4,0.3,2],
    ["OP-003","W_BEL_14","Оптимизация режима ВШН",3,0.25,3],
    ["OP-004","W_BEL_27","Оптимизация частоты УЭЦН",5,0.4,3],
    ["OP-005","W_BEL_50","Смена режима ВШН",4,0.35,4],
    ["OP-006","W_BEL_55","Исследование и оптимизация режима",6,0.8,6]])
write("global_constraints.csv",["constraint_id","name","value","unit","active","comment"],[
    ["GC-001","Бюджет",3.0,"mln_rub",True,"Общий лимит программы мероприятий"],
    ["GC-002","Время бригады",12,"team_hours",True,"Доступный ресурс на период"],
    ["GC-003","Число мероприятий",2,"count",True,"Максимум одновременно выбранных мероприятий"]])

print(f"Созданы 40 часов суммарных данных и {len(telemetry)} строк по 17 скважинам")
