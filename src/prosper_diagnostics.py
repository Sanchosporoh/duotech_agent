"""Presentation of completed lift calculations, without claiming a diagnosis."""
import json
from pathlib import Path
import pandas as pd
import numpy as np


def intake_pressure(point, pump_depth_ft, depth_tolerance_ft=1.0):
    """Select the lower side of a resolved pump jump, never the best-fitting pressure."""
    profile = point.get('profile', [])
    jumps = []
    for upper, lower in zip(profile, profile[1:]):
        if (abs(upper['depth_ft'] - lower['depth_ft']) <= .01
                and abs(lower['depth_ft'] - pump_depth_ft) <= depth_tolerance_ft
                and upper['pressure_psig'] > lower['pressure_psig']):
            jumps.append(lower)
    if len(jumps) != 1:
        raise ValueError('Не удалось однозначно выделить скачок давления насоса; выбор точки запрещён')
    return jumps[0]


def baseline_comparison(project: Path, audit):
    sensors = json.loads((project / 'config' / 'diagnostic_sensors.json').read_text(encoding='utf-8'))
    sensor = sensors['W_BEL_27_TLBB']
    if sensor['pressure_location'] != 'pump_intake':
        raise ValueError('Положение датчика не подтверждено как приём насоса')
    reference = audit['lift_probe']['gauge_reference']
    tolerance = sensor['depth_match_tolerance_ft']
    if abs(reference['depth_ft'] - reference['pump_depth_ft']) > tolerance:
        raise ValueError('Датчик не на глубине насоса: необходимо отдельное приведение давления')
    rows = []
    for point in audit['lift_probe']['points']:
        intake = intake_pressure(point, reference['pump_depth_ft'], tolerance)
        rows.append({
            'Дебит жидкости, м³/сут': point['liquid_rate_stbd'] * .158987294928,
            'Давление приёма, бар изб.': intake['pressure_psig'] * .0689475729,
        })
    calculated = rows[0]['Давление приёма, бар изб.']
    measured = reference['measured_pressure_psig'] * .0689475729
    tolerance_bar = sensor['pressure_residual_tolerance_bar']
    residual = measured - calculated
    return pd.DataFrame(rows), {'measured_bar': measured, 'calculated_bar': calculated,
                               'residual_bar': residual,
                               'tolerance_bar': tolerance_bar,
                               'within_tolerance': abs(residual) <= tolerance_bar,
                               'cause_confirmed': False}


def load_probe(project: Path):
    path = project / "data" / "prosper_diagnostic_audit_W27.json"
    if not path.exists():
        return None, pd.DataFrame()
    audit = json.loads(path.read_text(encoding="utf-8"))
    rows = []
    for point in audit.get("lift_probe", {}).get("points", []):
        rows.append({
            "Дебит жидкости, м³/сут": point["liquid_rate_stbd"] * 0.158987294928,
            "Доля исходного дебита": point["rate_fraction"],
            "Глубина конца расчёта, м": point["bottom_depth_ft"] * 0.3048,
            "Давление конца расчёта, бар изб.": point["bottom_pressure_psig"] * 0.0689475729,
        })
    return audit, pd.DataFrame(rows)


def diagnose_intake(audit, observed_pressure_bara, tolerance_bar):
    """Compare prior inflow/lift at intake, using only old model and observed pressure."""
    pump_depth=float(audit['parameters']['pump_depth']['value'])
    pi=float(audit['parameters']['productivity_index']['value'])
    reservoir=float(audit['parameters']['reservoir_pressure']['value'])
    if str(audit['parameters']['ipr_method']['value'])!='0':
        raise ValueError('Диагностическая интерполяция поддерживает только текущую IPR PI Entry')
    nodes=[]
    for point in audit['lift_probe']['points']:
        intake=intake_pressure(point,pump_depth)['pressure_psig']
        q=point['liquid_rate_stbd']
        lower_drop=point['bottom_pressure_psig']-intake
        nodes.append((q,intake,reservoir-q/pi-lower_drop))
    nodes.sort()
    observed=(observed_pressure_bara-1.01325)/.0689475729
    result={}
    for name,index in (('Прежний лифт',1),('Прежний приток',2)):
        q=np.array([n[0] for n in nodes]); p=np.array([n[index] for n in nodes])
        if not (np.all(np.diff(p)>0) or np.all(np.diff(p)<0)):
            raise ValueError('Кривая немонотонна: однозначный дебит не определяется')
        order=np.argsort(p); p=p[order]; q=q[order]
        band=tolerance_bar/.0689475729
        if observed-band<p.min() or observed+band>p.max():
            result[name]={'status':'За пределами рассчитанной кривой; экстраполяция запрещена'}
            continue
        rates=np.interp([observed-band,observed,observed+band],p,q)*.158987294928
        result[name]={'status':'В рассчитанном диапазоне','rate_m3d':float(rates[1]),'min_m3d':float(rates.min()),'max_m3d':float(rates.max())}
    return result
