"""Reject inconsistent solver cases before they become monitoring telemetry."""
from src.prosper_diagnostics import intake_pressure


def validate(audit, pressure_tolerance_bar):
    cases = audit.get('physical_scenarios', {}).get('cases', [])
    if not cases:
        return {'ready': False, 'issues': ['Нет совместных расчётов притока и лифта']}
    pump_depth = float(audit['parameters']['pump_depth']['value'])
    issues = []
    comparisons = []
    baseline = cases[0]
    for case in cases:
        try:
            tcc = intake_pressure({'profile': case['lift_profile']}, pump_depth)['pressure_psig']
            residual = (case['intake_pressure_psig'] - tcc) * .0689475729
            comparisons.append({'case': case['case'], 'sys_tcc_residual_bar': residual})
            if abs(residual) > pressure_tolerance_bar:
                issues.append(f"{case['case']}: SYS и TCC расходятся на {residual:+.2f} бар")
            if case['case'].startswith('inflow') and case['liquid_rate_stbd'] > baseline['liquid_rate_stbd']:
                issues.append(f"{case['case']}: снижение PI привело к росту дебита; нужна проверка ветви решения")
        except (ValueError, KeyError) as exc:
            issues.append(f"{case.get('case')}: {exc}")
    return {'ready': not issues, 'issues': issues, 'comparisons': comparisons}
