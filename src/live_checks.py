"""Bounded deterministic tools applied to LLM candidates, not scenario IDs."""
import json
from pathlib import Path
import pandas as pd
from src.prosper_diagnostics import diagnose_intake


def execute(root, context, answer):
    models=json.loads((root/'config'/'diagnostic_models.json').read_text(encoding='utf-8'))
    sensors=json.loads((root/'config'/'diagnostic_sensors.json').read_text(encoding='utf-8'))
    telemetry=pd.DataFrame(context['telemetry'])
    rows=[]
    def append(title,well,tool,status,evidence):
        rows.append({'Гипотеза':title,'Скважина':well,'Инструмент':tool,'Статус':status,'Результат / что требуется':evidence})
    for hypothesis in answer['hypotheses']:
        title=hypothesis['title']
        candidates=hypothesis['candidate_wells']
        if not candidates:
            append(title,'—','Групповой баланс / качество измерений','Не выполнено',
                   'Нет подключённой проверки общего оборудования или независимого замера сепаратора. '+hypothesis['verification'])
        for well in candidates:
            if telemetry.empty or 'well_id' not in telemetry:
                append(title,well,'Телеметрия','Не выполнено','Нет сигналов')
                continue
            history=telemetry[(telemetry.well_id==well)&(telemetry.hour<=context['hour'])].sort_values('hour')
            if history.empty:
                append(title,well,'Телеметрия','Не выполнено','Нет сигналов скважины')
                continue
            current=history.iloc[-1]
            if int(current.hour)!=context['hour']:
                append(title,well,'Свежесть','Не выполнено',f"Последний сигнал в {int(current.hour):02d}:00; текущего сигнала нет")
                continue
            frequency=current.get('frequency_hz')
            initial=history.iloc[0].get('frequency_hz')
            if pd.isna(frequency) or pd.isna(initial):
                append(title,well,'Управляющий режим','Недостаточно данных','Нет текущей или исходной частоты; неприменимо для некоторых типов насосов')
                continue
            append(title,well,'Управляющий режим','Признак',f'Частота: исходная {initial:g}, текущая {frequency:g} Гц; это не доказательство причины')
            if frequency==0:
                append(title,well,'Прежние кривые лифта','Не выполнено','Оборудование остановлено: рабочие кривые включённого насоса неприменимы; проверить питание и статус')
                continue
            if frequency!=initial:
                append(title,well,'Прежние кривые лифта','Не выполнено','Частота изменилась: нужен расчёт на текущем контроле')
                continue
            if well not in models or well not in sensors:
                append(title,well,'Приток / лифт','Не выполнено','Для объекта не подключены прежние кривые и положение датчика')
                continue
            model=models[well]; sensor=sensors[well]
            pressure=current.get(model['pressure_column'])
            if pd.isna(pressure):
                append(title,well,'Приток / лифт','Не выполнено','Текущее давление отсутствует')
                continue
            path=(root/model['prior_curves']).resolve()
            if not path.is_relative_to(root.resolve()):
                append(title,well,'Приток / лифт','Не выполнено','Файл кривых вне проекта запрещён')
                continue
            try:
                audit=json.loads(path.read_text(encoding='utf-8'))
                model_frequency=float(audit['parameters']['pump_frequency']['value'])
                if model_frequency!=frequency:
                    append(title,well,'Приток / лифт','Не выполнено','Текущая частота отличается от частоты рассчитанных кривых')
                    continue
                if model['pressure_unit']!='bara' or sensor['pressure_location']!='pump_intake':
                    append(title,well,'Приток / лифт','Не выполнено','Единицы или положение датчика не поддерживаются')
                    continue
                boundary=audit['lift_probe']['boundary_conditions']
                expected={'whp_bara':boundary['whp_psig']*.0689475729+1.01325,
                          'water_cut_pct':boundary['wc_pct'],
                          'gor_m3m3':boundary['gor_scf_stb']*.178107606679035}
                missing=[key for key in expected if pd.isna(current.get(key))]
                changed=[key for key,value in expected.items() if key not in missing and abs(float(current[key])-value)>max(1e-6,abs(value)*1e-6)]
                if changed:
                    append(title,well,'Совместимость условий','Не выполнено','Изменились '+', '.join(changed)+': прежние кривые не применяются; нужен новый расчёт PROSPER при текущих условиях')
                    continue
                append(title,well,'Совместимость условий','Недостаточно данных' if missing else 'Согласовано',
                       'Нет текущих значений: '+', '.join(missing) if missing else 'Буферное давление, ГФ, обводнённость и частота соответствуют условиям кривых; численная погрешность сравнения не является инженерным допуском')
                checks=diagnose_intake(audit,float(pressure),sensor['pressure_residual_tolerance_bar'])
                for name,check in checks.items():
                    evidence=check['status']
                    if 'rate_m3d' in check:
                        evidence=f"Оценка жидкости {check['rate_m3d']:.2f} м³/сут; диапазон {check['min_m3d']:.2f}–{check['max_m3d']:.2f} м³/сут"
                    append(title,well,name,'Условная оценка' if missing else 'Расчётная оценка',evidence+'; интерполяция прежних кривых, не новый запуск PROSPER. Причина не подтверждена.')
            except (ValueError,KeyError,OSError) as exc:
                append(title,well,'Приток / лифт','Не выполнено',str(exc))
    return rows
