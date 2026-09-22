from __future__ import annotations
import csv, json
from dataclasses import asdict, dataclass
from datetime import datetime
from itertools import combinations
from pathlib import Path
from uuid import uuid4

@dataclass(frozen=True)
class Opportunity:
    opportunity_id: str; well_id: str; action: str
    oil_gain_tpd: float; cost_mln_rub: float; team_hours: float

def read_csv(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as f: return list(csv.DictReader(f))

def check_quality(rows, cfg):
    required={"timestamp","asset_id","plan_oil_tph","actual_oil_tph","status"}
    if not rows: return {"ok":False,"state":"waiting_for_data","issues":["Файл факта пуст"]}
    missing=sorted(required-set(rows[0]))
    if missing: return {"ok":False,"state":"needs_attention","issues":["Нет колонок: "+", ".join(missing)]}
    issues=[]; parsed=[]; seen=set()
    for n,r in enumerate(rows,2):
        try: ts=datetime.fromisoformat(r["timestamp"]); plan=float(r["plan_oil_tph"]); fact=float(r["actual_oil_tph"])
        except (ValueError,TypeError): issues.append(f"Строка {n}: неверный формат"); continue
        key=(ts,r["asset_id"])
        if key in seen: issues.append(f"Строка {n}: повтор часа")
        seen.add(key)
        if plan<=0 or fact<0: issues.append(f"Строка {n}: базовая физическая проверка не пройдена")
        parsed.append({**r,"ts":ts,"plan":plan,"fact":fact})
    if issues or not parsed: return {"ok":False,"state":"needs_attention","issues":issues}
    parsed.sort(key=lambda x:x["ts"])
    if parsed[-1]["status"] not in {"confirmed","preliminary"}: return {"ok":False,"state":"waiting_for_data","issues":["Последний факт отсутствует"]}
    gaps=[(b["ts"]-a["ts"]).total_seconds()/3600 for a,b in zip(parsed,parsed[1:])]
    if any(x>cfg["maximum_fact_age_hours"] for x in gaps): return {"ok":False,"state":"waiting_for_data","issues":["В почасовом ряду есть разрыв"]}
    return {"ok":True,"state":"data_ready","issues":[],"rows":parsed}

def detect_deviation(rows,cfg):
    recent=rows[-cfg["confirmation_hours"]:]
    values=[round((x["fact"]-x["plan"])/x["plan"]*100,2) for x in recent]
    return {"triggered":len(recent)==cfg["confirmation_hours"] and all(x<=cfg["deviation_limit_pct"] for x in values),"recent_deviation_pct":values}

def load_opportunities(rows):
    return [Opportunity(r["opportunity_id"],r["well_id"],r["action"],float(r["oil_gain_tpd"]),float(r["cost_mln_rub"]),float(r["team_hours"])) for r in rows]

def check_physical_rules(telemetry,rules):
    findings=[]
    for row in telemetry:
        for rule in rules:
            parameter=rule["parameter"]
            if parameter not in row or row[parameter]=="": continue
            try: value=float(row[parameter]); minimum=float(rule["minimum"]); maximum=float(rule["maximum"])
            except ValueError: findings.append({"severity":"error","well_id":row.get("well_id"),"parameter":parameter,"message":"значение не является числом"}); continue
            if not minimum<=value<=maximum:
                findings.append({"severity":rule["severity"],"well_id":row.get("well_id"),"timestamp":row.get("timestamp"),"parameter":parameter,"value":value,"allowed_range":f"{minimum}..{maximum} {rule['unit']}"})
    return {"ok":not any(x["severity"]=="error" for x in findings),"findings":findings,"checked_values":len(telemetry)*len(rules)}

def load_global_constraints(rows):
    active={r["unit"]:float(r["value"]) for r in rows if r["active"].lower()=="true"}
    return {"budget_mln_rub":active["mln_rub"],"available_team_hours":active["team_hours"],"maximum_actions":int(active["count"])}

def optimize(items,limits):
    variants=[]
    for size in range(1,min(len(items),limits["maximum_actions"])+1):
        for group in combinations(items,size):
            cost=sum(x.cost_mln_rub for x in group); hours=sum(x.team_hours for x in group)
            reasons=[]
            if cost>limits["budget_mln_rub"]: reasons.append("превышен бюджет")
            if hours>limits["available_team_hours"]: reasons.append("не хватает времени бригады")
            gain=round(sum(x.oil_gain_tpd for x in group)-max(0,len(group)-1)*0.5,2)
            variants.append({"ids":[x.opportunity_id for x in group],"cost_mln_rub":cost,"team_hours":hours,"forecast_gain_tpd":gain,"allowed":not reasons,"rejection_reasons":reasons})
    allowed=[x for x in variants if x["allowed"]]
    return {"variants":variants,"best_variant":max(allowed,key=lambda x:x["forecast_gain_tpd"],default=None)}

def execute(project, run_hypotheses=False):
    project=Path(project); cfg=json.loads((project/"config/settings.json").read_text(encoding="utf-8"))
    run_id=datetime.now().strftime("%Y%m%d-%H%M%S")+"-"+uuid4().hex[:6]; folder=project/"runs"/run_id; folder.mkdir(parents=True)
    quality=check_quality(read_csv(project/"data/production.csv"),cfg); steps={"data_quality":{k:v for k,v in quality.items() if k!="rows"}}
    if not quality["ok"]: result={"run_id":run_id,"status":quality["state"],"steps":steps}
    else:
        telemetry=read_csv(project/"data/well_telemetry.csv"); rules=read_csv(project/"data/physical_rules.csv")
        steps["physical_checks"]=check_physical_rules(telemetry,rules)
        if not steps["physical_checks"]["ok"]:
            result={"run_id":run_id,"status":"needs_attention","steps":steps}
            (folder/"result.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
            return result,folder
        steps["deviation"]=detect_deviation(quality["rows"],cfg)
        if not steps["deviation"]["triggered"]: result={"run_id":run_id,"status":"monitoring_completed","steps":steps}
        else:
            if run_hypotheses:
                try:
                    from .hypotheses import formulate_hypotheses
                    events=read_csv(project/"data/events.csv")
                    steps["hypotheses"]=formulate_hypotheses(quality["rows"],steps["deviation"],cfg["llm"],project,telemetry,events,rules)
                    from .hypothesis_checks import verify_hypotheses
                    steps["hypothesis_checks"]=verify_hypotheses(steps["hypotheses"]["hypotheses"],telemetry)
                    supported=[item for item in steps["hypothesis_checks"] if item["status"]=="supported"]
                    if supported:
                        selected_id=supported[0]["hypothesis_id"]
                        hypothesis=next(item for item in steps["hypotheses"]["hypotheses"] if item["hypothesis_id"]==selected_id)
                        from .actions import create_local_calculation_task
                        steps["external_action"]=create_local_calculation_task(project/cfg["action"]["local_file"],run_id,cfg["asset_id"],quality["rows"][-1]["timestamp"],hypothesis)
                except Exception as error:
                    steps["hypotheses"]={"error":str(error),"state":"needs_attention"}
            items=load_opportunities(read_csv(project/"data/opportunities.csv")); limits=load_global_constraints(read_csv(project/"data/global_constraints.csv")); steps["opportunity_register"]=[asdict(x) for x in items]; steps["global_constraints"]=limits; steps["optimization"]=optimize(items,limits)
            best=steps["optimization"]["best_variant"]
            latest=quality["rows"][-1]
            if best:
                current_tpd=round(latest["fact"]*24,2); plan_tpd=round(latest["plan"]*24,2)
                forecast_tpd=round(current_tpd+best["forecast_gain_tpd"],2)
                shortfall=max(plan_tpd-current_tpd,0)
                steps["forecast_effect"]={"current_oil_tpd":current_tpd,"plan_oil_tpd":plan_tpd,"selected_actions":best["ids"],"calculated_gain_tpd":best["forecast_gain_tpd"],"forecast_oil_tpd":forecast_tpd,"remaining_shortfall_tpd":round(max(plan_tpd-forecast_tpd,0),2),"shortfall_recovery_pct":round(best["forecast_gain_tpd"]/shortfall*100,1) if shortfall else 0}
            result={"run_id":run_id,"status":"approval_required" if steps["optimization"]["best_variant"] else "needs_attention","steps":steps}
    (folder/"result.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    return result,folder
