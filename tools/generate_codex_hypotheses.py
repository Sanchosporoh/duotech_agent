from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.incident_codex import generate, save

if __name__ == "__main__":
    ids = sys.argv[1:] or ["INC-001", "INC-002"]
    for incident_id in ids:
        print(f"Codex: {incident_id}", flush=True)
        print(save(ROOT, incident_id, generate(ROOT, incident_id)), flush=True)
