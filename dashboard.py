"""Streamlit entry point: page styles and the live monitoring view."""
from pathlib import Path
import importlib
import os
import streamlit as st

# AGENT_PROJECT_ROOT shows a separate project copy, e.g. a stub-mode demo.
ROOT = Path(os.environ.get('AGENT_PROJECT_ROOT') or Path(__file__).resolve().parent).resolve()
st.set_page_config(page_title="Мониторинг добычи", layout="wide")
st.markdown("""<style>header[data-testid="stHeader"],div[data-testid="stToolbar"],div[data-testid="stDecoration"]{display:none}.block-container{padding-top:.2rem;padding-bottom:.7rem;max-width:1700px}h1,h2,h3,h4{margin:.15rem 0 .3rem}div[data-testid="stMetric"]{background:#f4f6f8;padding:.35rem .6rem;border-radius:.45rem}div[data-testid="stVerticalBlock"]{gap:.35rem}.readable-table{overflow:auto;max-height:520px;border:1px solid #d8dee8;border-radius:.45rem}.readable-table table{width:100%;border-collapse:collapse;font-size:.86rem}.readable-table th{position:sticky;top:0;background:#edf1f7;color:#1f2937;z-index:1;text-align:left}.readable-table th,.readable-table td{padding:.45rem .55rem;border-bottom:1px solid #d8dee8;vertical-align:top;white-space:normal;overflow-wrap:anywhere;min-width:7rem}.readable-table td:last-child{min-width:20rem}</style>""", unsafe_allow_html=True)
# Reload keeps a running Streamlit server in sync with edited modules.
for module_name in ('day_case','incident_view','incident_lifecycle','measurement_overview','live_monitor','live_reasoning','live_checks','license_retry','live_adaptation','live_planning','restoration_forecast','restoration_planning','proposal_selection','live_execution','autonomous_cycle','well_trust','recompute_policy','escalation','tool_gateway','cycle_service','live_dashboard'):
    importlib.reload(importlib.import_module('src.'+module_name))
importlib.import_module('src.live_dashboard').render(ROOT)
