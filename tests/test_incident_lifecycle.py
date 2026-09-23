import tempfile
import unittest
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from src.incident_lifecycle import complete_revision, ensure_incident, load, record_decision


class IncidentLifecycleTests(unittest.TestCase):
    def test_two_incidents_survive_concurrent_creation(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
            path=Path(folder)/"lifecycle.json"
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures=[pool.submit(ensure_incident,path,incident,"Проверяется")
                         for incident in ("INC-001","INC-002")]
                for future in futures:future.result()
            self.assertEqual(set(load(path)["incidents"]),{"INC-001","INC-002"})

    def test_existing_incident_does_not_rewrite_registry(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
            path=Path(folder)/"lifecycle.json"
            first=ensure_incident(path,"INC-001","Проверяется")
            modified=path.stat().st_mtime_ns
            second=ensure_incident(path,"INC-001","Другая подпись")
            self.assertEqual(first,second)
            self.assertEqual(path.stat().st_mtime_ns,modified)

    def test_return_for_revision_creates_new_version_and_keeps_old_result(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
            path=Path(folder)/"lifecycle.json"
            ensure_incident(path,"INC-002","Остановка W22")
            record_decision(path,"INC-002","На доработке","Не менять W13","balanced","Баланс +0.88 т")
            incident=load(path)["incidents"]["INC-002"]
            self.assertEqual(len(incident["versions"]),2)
            self.assertEqual(incident["versions"][0]["gap_result"],"Баланс +0.88 т")
            self.assertEqual(incident["versions"][1]["human_comment"],"Не менять W13")
            self.assertEqual(incident["stage"],"awaiting_revision_calculation")

    def test_completed_revision_returns_to_human_decision(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
            root=Path(folder); path=root/"lifecycle.json"
            ensure_incident(path,"INC-002","Остановка W22")
            record_decision(path,"INC-002","На доработке","Не менять W13","balanced","Баланс +0.88 т")
            complete_revision(path,"INC-002",root/"strategies.json",
                              {"balanced":root/"gap.json"},"balanced","Баланс +0.20 т")
            incident=load(path)["incidents"]["INC-002"]
            self.assertEqual(incident["stage"],"awaiting_human_decision")
            self.assertEqual(incident["versions"][-1]["strategy"],"balanced")


if __name__ == "__main__": unittest.main()
