"""Реестр возможностей описывает потенциал, а не готовые режимы."""
import json
from pathlib import Path
import pandas as pd


def table(project: Path) -> pd.DataFrame:
    data=json.loads((project/"data"/"opportunity_register_structured.json").read_text(encoding="utf-8"))
    controls={"esp_frequency":"Частота ЭЦН", "pcp_speed":"Скорость ШВН"}
    directions={"increase":"Повышение отбора", "increase_after_restore":"Повышение после восстановления",
                "decrease":"Защитное регулирование / освобождение ограничения"}
    return pd.DataFrame([{
        "Скважина":item["well_id"],
        "Возможность":directions[item["direction"]],
        "Оценка потенциала нефти, т/сут":item["potential_oil_tpd"],
        "Разрешённый контроль":controls[item["control"]],
        "Предельное изменение контроля":f"до {item['maximum_change']} {item['unit']}",
        "Условия достижения":"; ".join(item["conditions"]),
        "Стоимость, млн руб":item["cost_mln_rub"],
        "Выполнение":"АСУТП" if item["remote"] else "Выезд",
        "Геологический риск":item["geological_risk"],
    } for item in data["opportunities"]])
