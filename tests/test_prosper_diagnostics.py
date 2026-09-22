import unittest
from pathlib import Path
from src.prosper_diagnostics import load_probe, baseline_comparison, intake_pressure, diagnose_intake
from src.physical_scenario_validation import validate

ROOT = Path(__file__).resolve().parents[1]


class ProsperDiagnosticTests(unittest.TestCase):
    def test_hourly_pump_case_has_consistent_pressure_and_disagreeing_old_curves(self):
        from src.day_case import build_hourly_case
        from src.incident_view import sparse_telemetry
        audit, _ = load_probe(ROOT)
        wells, _ = build_hourly_case(ROOT)
        selected=wells[wells.well_id=='W_BEL_27_TLBB'].set_index('hour')
        self.assertLess(selected.loc[6,'actual_oil_tpd'],selected.loc[0,'actual_oil_tpd'])
        self.assertGreater(selected.loc[6,'sensor_pressure_bara'],selected.loc[0,'sensor_pressure_bara'])
        signals=sparse_telemetry(wells)
        observed=signals[(signals.well_id=='W_BEL_27_TLBB') & (signals.hour==6)].iloc[0]
        checks=diagnose_intake(audit,observed.sensor_pressure_bar,1.5)
        values=list(checks.values())
        self.assertGreater(values[0]['min_m3d'],values[1]['max_m3d'])

    def test_consistent_scenarios_pass_and_corruption_is_blocked(self):
        audit, _ = load_probe(ROOT)
        report = validate(audit, 1.5)
        self.assertTrue(report['ready'], report['issues'])
        audit['physical_scenarios']['cases'][0]['intake_pressure_psig']+=100
        self.assertFalse(validate(audit,1.5)['ready'])
    def test_intake_selection_and_baseline(self):
        audit, _ = load_probe(ROOT)
        frame, comparison = baseline_comparison(ROOT, audit)
        self.assertEqual(len(frame), 5)
        self.assertAlmostEqual(comparison['calculated_bar'], 104.39, places=1)
        self.assertFalse(comparison['cause_confirmed'])
        self.assertEqual(comparison['tolerance_bar'], 1.5)
        self.assertTrue(comparison['within_tolerance'])

    def test_no_jump_means_no_pressure_selection(self):
        with self.assertRaises(ValueError):
            intake_pressure({'profile': [{'depth_ft': 100, 'pressure_psig': 10}]}, 100)

    def test_probe_is_not_diagnosis(self):
        audit, frame = load_probe(ROOT)
        self.assertFalse(audit['diagnosis_performed'])
        self.assertFalse(audit['model_saved'])
        self.assertEqual(len(frame), 5)
        self.assertAlmostEqual(frame.iloc[0]['Дебит жидкости, м³/сут'], 36.4, places=1)

    def test_pump_pressure_jump_is_preserved(self):
        audit, _ = load_probe(ROOT)
        reference = audit['lift_probe']['gauge_reference']
        self.assertLess(abs(reference['depth_ft'] - reference['pump_depth_ft']), 1)
        neighbours = audit['lift_probe']['points'][0]['gauge_neighbours']
        pressures = [point['pressure_psig'] for point in neighbours]
        self.assertGreater(max(pressures) - min(pressures), 1000)


if __name__ == '__main__':
    unittest.main()
