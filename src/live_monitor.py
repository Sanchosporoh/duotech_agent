"""Monitoring logic consumes measurements, never scenario labels or incident numbers."""
import pandas as pd
import numpy as np


def screen_wells(telemetry,hour,tolerance=1.5):
    rows=[]
    for well,history in telemetry[telemetry.hour<=hour].sort_values('hour').groupby('well_id'):
        first,current=history.iloc[0],history.iloc[-1]
        age=hour-int(current.hour)
        delta=current.get('sensor_pressure_bar')-first.get('sensor_pressure_bar')
        frequency=current.get('frequency_hz')
        reasons=[]
        if age:reasons.append(f'Последнее измерение {age} ч назад — текущего состояния не знаем')
        elif pd.notna(frequency) and frequency==0:reasons.append('Частота 0 Гц — сигнал остановки')
        else:
            if pd.notna(delta) and abs(delta)>tolerance:reasons.append(f'Давление изменилось на {delta:+.2f} бар; допуск ±{tolerance:g} бар')
            if pd.notna(frequency) and pd.notna(first.get('frequency_hz')) and frequency!=first.frequency_hz:reasons.append(f'Частота: {first.frequency_hz:g} → {frequency:g} Гц')
        if not reasons:reasons.append('В доступных сигналах нет явной аномалии; снижение дебита не исключено')
        if pd.isna(current.get('sensor_pressure_bar')):reasons.append('Нет давления на датчике')
        rows.append({'Скважина':well,'Последний замер':f'{int(current.hour):02d}:00','Частота, Гц':frequency,
            'Изменение давления, бар':delta,'Почему рассматриваем / чего не знаем':'; '.join(reasons)})
    return pd.DataFrame(rows)


def hypotheses(telemetry, hour, pressure_tolerance_bar=1.5):
    available=telemetry[telemetry.hour<=hour].sort_values('hour')
    rows=[]
    for well, history in available.groupby('well_id'):
        if len(history)<2:
            continue
        baseline, current=history.iloc[0],history.iloc[-1]
        if int(current.hour)<hour:
            continue  # stale values do not create a new equipment event
        frequency=current.get('frequency_hz')
        previous_frequency=baseline.get('frequency_hz')
        pressure=current.get('sensor_pressure_bar')
        previous_pressure=baseline.get('sensor_pressure_bar')
        delta=pressure-previous_pressure if pd.notna(pressure) and pd.notna(previous_pressure) else None
        changed_conditions=[key for key in ['whp_bara','water_cut_pct','gor_m3m3']
                            if pd.notna(current.get(key)) and pd.notna(baseline.get(key)) and current[key]!=baseline[key]]
        if pd.notna(frequency) and frequency==0 and pd.notna(previous_frequency) and previous_frequency>0:
            variants=['Остановка оборудования или потеря питания']
        elif delta is not None and abs(delta)>pressure_tolerance_bar:
            variants=['Изменение лифта','Изменение притока','Изменение газа/воды или ошибка давления']
        elif pd.notna(frequency) and pd.notna(previous_frequency) and frequency!=previous_frequency:
            variants=['Изменение управляющего режима']
        elif changed_conditions:
            variants=['Изменение условий: '+', '.join(changed_conditions)]
        else:
            continue
        for variant in variants:
            rows.append({'well_id':well,'hypothesis':variant,'pressure_delta_bar':delta,
                         'frequency_hz':frequency,'measurement_hour':int(current.hour),
                         'status':'Требует проверки; причина не подтверждена'})
    if not rows:
        rows=[{'well_id':'—','hypothesis':'Причина не локализована: проверить измерение сепаратора и собрать телеметрию',
               'pressure_delta_bar':None,'frequency_hz':None,'measurement_hour':hour,'status':'Недостаточно данных'}]
    return pd.DataFrame(rows)


def validate_inputs(separator, telemetry):
    errors=[]
    for label,frame,required in [('Сепаратор',separator,['hour','plan_oil_tpd','separator_oil_tpd','separator_water_m3d']),('Телеметрия',telemetry,['hour','well_id'])]:
        missing=[name for name in required if name not in frame]
        if missing:errors.append(f'{label}: отсутствуют столбцы '+', '.join(missing))
    if errors:return errors
    for label,frame,keys in [('Сепаратор',separator,['hour']),('Телеметрия',telemetry,['hour','well_id'])]:
        if frame[keys].isna().any().any() or frame.duplicated(keys).any():
            errors.append(f'{label}: пустые или повторяющиеся ключи измерения')
        hours=pd.to_numeric(frame.hour,errors='coerce')
        if not hours.between(0,23).all():
            errors.append(f'{label}: час должен быть целым от 0 до 23')
        elif (hours % 1 != 0).any():
            errors.append(f'{label}: час должен быть целым')
        elif not pd.api.types.is_numeric_dtype(frame.hour):
            errors.append(f'{label}: час должен быть числом, а не текстом')
    for column in ['plan_oil_tpd','separator_oil_tpd','separator_water_m3d']:
        values=pd.to_numeric(separator[column],errors='coerce')
        if (values.dropna()<0).any(): errors.append(f'Сепаратор: отрицательное значение {column}')
        if (separator[column].notna() & values.isna()).any(): errors.append(f'Сепаратор: нечисловое значение {column}')
        if (~np.isfinite(values.dropna())).any(): errors.append(f'Сепаратор: бесконечное значение {column}')
        if not pd.api.types.is_numeric_dtype(separator[column]) and values.notna().any():
            errors.append(f'Сепаратор: столбец {column} должен содержать числа')
    plan=pd.to_numeric(separator.plan_oil_tpd,errors='coerce')
    if plan.isna().any() or (plan<=0).any():
        errors.append('План должен быть положительным и заполненным')
    for column,minimum,maximum in [('sensor_pressure_bar',0,None),('frequency_hz',0,None),('whp_bara',0,None),('water_cut_pct',0,100),('gor_m3m3',0,None)]:
        if column not in telemetry: continue
        values=pd.to_numeric(telemetry[column],errors='coerce')
        invalid=telemetry[column].notna() & (values.isna() | ~np.isfinite(values) | (values<minimum))
        if maximum is not None: invalid |= values>maximum
        if invalid.any(): errors.append(f'Телеметрия: недопустимое значение {column}')
        if not pd.api.types.is_numeric_dtype(telemetry[column]) and values.notna().any():
            errors.append(f'Телеметрия: столбец {column} должен содержать числа')
    return errors
