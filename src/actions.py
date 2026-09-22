from __future__ import annotations
import csv, hashlib
from datetime import datetime
from pathlib import Path

FIELDS=["task_id","idempotency_key","created_at","run_id","asset_id","data_timestamp","hypothesis_id","well_ids","selected_tool","title","status"]

def create_local_calculation_task(path,run_id,asset_id,data_timestamp,hypothesis):
    """Создаёт одну задачу и не дублирует её при повторном прогоне на тех же данных."""
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    raw_key=f"{asset_id}|{data_timestamp}|{hypothesis['hypothesis_id']}"
    key=hashlib.sha256(raw_key.encode("utf-8")).hexdigest()[:16]
    existing=[]
    if path.exists():
        with path.open(encoding="utf-8-sig",newline="") as f: existing=list(csv.DictReader(f))
    duplicate=next((row for row in existing if row["idempotency_key"]==key),None)
    if duplicate: return {"created":False,"reason":"duplicate_prevented","record":duplicate}
    record={"task_id":"TASK-"+key[:8].upper(),"idempotency_key":key,"created_at":datetime.now().isoformat(timespec="seconds"),"run_id":run_id,"asset_id":asset_id,"data_timestamp":data_timestamp,"hypothesis_id":hypothesis["hypothesis_id"],"well_ids":";".join(hypothesis.get("target_wells",[])),"selected_tool":hypothesis.get("selected_tool","trend_analysis"),"title":hypothesis["cause"],"status":"new"}
    with path.open("a",encoding="utf-8-sig",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=FIELDS)
        if not existing: writer.writeheader()
        writer.writerow(record)
    return {"created":True,"reason":"task_created","record":record}
