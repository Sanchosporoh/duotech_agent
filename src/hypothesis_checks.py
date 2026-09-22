from __future__ import annotations
from collections import defaultdict
from statistics import mean

NUMERIC_FIELDS=["oil_rate_tph","liquid_rate_m3h","watercut_pct","bottomhole_pressure_bar","wellhead_pressure_bar","esp_frequency_hz","esp_current_a","vibration_mm_s","intake_pressure_bar","tubing_pressure_bar"]

def build_well_trends(telemetry,window=6):
    by_well=defaultdict(list)
    for row in telemetry: by_well[row["well_id"]].append(row)
    trends={}
    for well,rows in by_well.items():
        rows.sort(key=lambda x:x["timestamp"])
        if len(rows)<window*2: continue
        before=rows[-window*2:-window]; after=rows[-window:]
        metrics={}
        for field in NUMERIC_FIELDS:
            try: old=mean(float(x[field]) for x in before); new=mean(float(x[field]) for x in after)
            except (KeyError,ValueError): continue
            metrics[field]={"before":round(old,2),"after":round(new,2),"change":round(new-old,2),"change_pct":round((new-old)/old*100,2) if old else None}
        trends[well]=metrics
    return trends

def verify_hypotheses(hypotheses,telemetry):
    trends=build_well_trends(telemetry); results=[]
    for hypothesis in hypotheses:
        wells=hypothesis.get("target_wells",[]); available={w:trends[w] for w in wells if w in trends}
        if not available:
            status="insufficient_data"; reasons=["Нет достаточной истории по указанным скважинам"]
        else:
            kind=hypothesis["hypothesis_type"]; support=False; reasons=[]
            for well,metrics in available.items():
                oil=metrics.get("oil_rate_tph",{}).get("change_pct")
                current=metrics.get("esp_current_a",{}).get("change_pct")
                vibration=metrics.get("vibration_mm_s",{}).get("change_pct")
                bhp=metrics.get("bottomhole_pressure_bar",{}).get("change_pct")
                if oil is not None and oil<=-10: reasons.append(f"{well}: дебит нефти изменился на {oil}%")
                if kind=="equipment_degradation" and oil is not None and oil<=-10 and ((current or 0)>=5 or (vibration or 0)>=10): support=True
                elif kind=="inflow_reduction" and oil is not None and oil<=-10 and (bhp or 0)<=-3: support=True
                elif kind=="measurement_issue": support=False
                elif kind=="gathering_constraint": support=False
            status="supported" if support else "not_supported_by_current_data"
            if not reasons: reasons=["Расчётные признаки подтверждения не обнаружены"]
        results.append({"hypothesis_id":hypothesis["hypothesis_id"],"hypothesis_type":hypothesis["hypothesis_type"],"cause":hypothesis["cause"],"target_wells":wells,"status":status,"calculated_trends":available,"reasons":reasons,"acceptance_criterion":hypothesis["acceptance_criterion"]})
    return results
