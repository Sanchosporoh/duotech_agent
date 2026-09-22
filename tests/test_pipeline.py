import unittest
from unittest.mock import patch
from pathlib import Path
import tempfile
from src.pipeline import Opportunity, check_physical_rules, check_quality, detect_deviation, optimize
from src.codex_cli import find_codex_executable
from src.hypothesis_checks import verify_hypotheses
from src.actions import create_local_calculation_task

CFG={"maximum_fact_age_hours":2,"confirmation_hours":3,"deviation_limit_pct":-10}

class PipelineTests(unittest.TestCase):
    def test_missing_fact_stops_pipeline(self):
        rows=[{"timestamp":"2026-09-11T10:00:00","asset_id":"K1","plan_oil_tph":"100","actual_oil_tph":"90","status":"missing"}]
        self.assertEqual(check_quality(rows,CFG)["state"],"waiting_for_data")

    def test_three_bad_hours_trigger(self):
        rows=[{"plan":100,"fact":89},{"plan":100,"fact":88},{"plan":100,"fact":87}]
        self.assertTrue(detect_deviation(rows,CFG)["triggered"])

    def test_global_constraints_reject_combination(self):
        items=[Opportunity("1","W1","A",8,2,8),Opportunity("2","W2","B",7,2,8)]
        result=optimize(items,{"maximum_actions":2,"budget_mln_rub":3,"available_team_hours":12})
        pair=next(x for x in result["variants"] if len(x["ids"])==2)
        self.assertFalse(pair["allowed"])

    def test_codex_executable_can_be_found_without_path(self):
        with patch("src.codex_cli.shutil.which", return_value=None):
            self.assertTrue(Path(find_codex_executable()).name.lower() == "codex.exe")

    def test_physical_rule_finds_impossible_value(self):
        telemetry=[{"well_id":"W1","timestamp":"t","oil_rate_tph":"-1"}]
        rules=[{"parameter":"oil_rate_tph","minimum":"0","maximum":"60","unit":"t/h","severity":"error"}]
        self.assertFalse(check_physical_rules(telemetry,rules)["ok"])

    def test_equipment_hypothesis_is_supported(self):
        telemetry=[]
        for hour in range(12):
            telemetry.append({"timestamp":f"{hour:02}","well_id":"W1","oil_rate_tph":str(30 if hour<6 else 20),"esp_current_a":str(40 if hour<6 else 48),"vibration_mm_s":str(2 if hour<6 else 3),"bottomhole_pressure_bar":"120"})
        hypothesis={"hypothesis_id":"H1","hypothesis_type":"equipment_degradation","cause":"Ухудшение УЭЦН","target_wells":["W1"],"acceptance_criterion":"Падение дебита и рост нагрузки"}
        self.assertEqual(verify_hypotheses([hypothesis],telemetry)[0]["status"],"supported")

    def test_local_action_does_not_create_duplicate(self):
        hypothesis={"hypothesis_id":"H1","cause":"Проверить УЭЦН","target_wells":["W1"],"selected_tool":"trend_analysis"}
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"tasks.csv"
            first=create_local_calculation_task(path,"RUN1","K1","2026-09-13T10:00:00",hypothesis)
            second=create_local_calculation_task(path,"RUN2","K1","2026-09-13T10:00:00",hypothesis)
            self.assertTrue(first["created"]); self.assertFalse(second["created"])

if __name__ == "__main__": unittest.main()
