"""Shared test stand: an isolated project copy with generated measurements."""
import shutil
import pandas as pd
from pathlib import Path
from src import incident_view

ROOT = Path(__file__).resolve().parents[1]
# Incidents of the generated training day, named by their opening time.
FIRST = 'INC-20260914-0600'
SECOND = 'INC-20260914-1500'


def make_project(root, conditions=True):
    """Build a temporary project that never reads the user's data/live state."""
    root = Path(root)
    (root/'config').mkdir(parents=True, exist_ok=True)
    (root/'data').mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT/'data/opportunity_register_structured.json', root/'data/opportunity_register_structured.json')
    for source in (ROOT/'config').glob('*.json'):
        shutil.copyfile(source, root/'config'/source.name)
    # Prior PROSPER curves referenced by the diagnostic configuration.
    for name in ('prosper_diagnostic_audit_W27.json', 'petex_baseline.csv'):
        shutil.copyfile(ROOT/'data'/name, root/'data'/name)
    incident_view.write_initial_measurements(ROOT, root/'data/live')
    if conditions:
        # Same operating conditions the engineer entered for W27 in data/live/telemetry.csv.
        path = root/'data/live/telemetry.csv'
        telemetry = pd.read_csv(path)
        selected = telemetry.well_id == 'W_BEL_27_TLBB'
        telemetry.loc[selected, ['whp_bara', 'water_cut_pct', 'gor_m3m3']] = [8.83325, 5.4, 10.674395]
        telemetry.to_csv(path, index=False)
    return root
