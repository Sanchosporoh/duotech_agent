from __future__ import annotations
import json
from pathlib import Path
from .codex_cli import ask_codex

HYPOTHESIS_SCHEMA={
    "type":"object",
    "properties":{
        "summary":{"type":"string"},
        "hypotheses":{"type":"array","items":{
            "type":"object",
            "properties":{
                "hypothesis_id":{"type":"string"},
                "hypothesis_type":{"type":"string","enum":["equipment_degradation","inflow_reduction","measurement_issue","gathering_constraint","other"]},
                "cause":{"type":"string"},
                "target_wells":{"type":"array","items":{"type":"string"}},
                "selected_tool":{"type":"string","enum":["trend_analysis","proxy_model","duotech","request_missing_data"]},
                "evidence":{"type":"array","items":{"type":"string"}},
                "missing_data":{"type":"array","items":{"type":"string"}},
                "verification":{"type":"string"},
                "required_parameters":{"type":"array","items":{"type":"string"}},
                "acceptance_criterion":{"type":"string"},
                "priority":{"type":"integer","minimum":1}
            },
            "required":["hypothesis_id","hypothesis_type","cause","target_wells","selected_tool","evidence","missing_data","verification","required_parameters","acceptance_criterion","priority"],
            "additionalProperties":False
        }}
    },
    "required":["summary","hypotheses"],
    "additionalProperties":False
}

def formulate_hypotheses(production_rows,deviation,llm_settings,project:Path,telemetry=None,events=None,physical_rules=None):
    context=[{"timestamp":r["timestamp"],"plan_oil_tph":r["plan"],"actual_oil_tph":r["fact"],"status":r["status"]} for r in production_rows[-12:]]
    telemetry=telemetry or []
    timestamps=sorted({row["timestamp"] for row in telemetry})[-12:]
    latest_timestamp=timestamps[-1] if timestamps else None
    latest_rows=[row for row in telemetry if row["timestamp"]==latest_timestamp]
    # В LLM передаём подробную историю только скважин с заметным отклонением.
    # Весь фонд уже представлен выше агрегированной добычей объекта.
    abnormal_wells={
        row["well_id"] for row in latest_rows
        if row.get("well_status")=="running"
        and float(row.get("plan_oil_tph") or 0)>0
        and (float(row.get("oil_rate_tph") or 0)-float(row["plan_oil_tph"]))
            / float(row["plan_oil_tph"])*100 <= -5
    }
    telemetry_context=[
        row for row in telemetry
        if row["timestamp"] in timestamps and row.get("well_id") in abnormal_wells
    ]
    prompt=(
        "Ты помощник инженера по интегрированному моделированию. Сформируй предварительные "
        "гипотезы причин отклонения добычи. Не выдумывай телеметрию и события, которых нет во входе. "
        "Привяжи гипотезу к скважинам из входа и выбери один инструмент из разрешённого списка: "
        "trend_analysis, proxy_model, duotech, request_missing_data. Составь конкретное расчётное задание: требуемые параметры "
        "и проверяемый критерий подтверждения. Недостающие сведения явно перечисли в missing_data. "
        "Не изменяй файлы и не запускай команды. "
        "Верни только результат по заданной JSON-схеме. Вход:\n"+
        json.dumps({"production":context,"well_telemetry":telemetry_context,"events":events or [],"physical_rules":physical_rules or [],"deviation":deviation},ensure_ascii=False)
    )
    return ask_codex(prompt,HYPOTHESIS_SCHEMA,project,llm_settings.get("model"),llm_settings.get("use_local_oss_model",False),llm_settings.get("local_provider","ollama"))
